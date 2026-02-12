"""
Calibration dashboard and trend visibility helpers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.calibration import (
    build_calibration_buckets,
    calculate_brier_score,
    normalize_utc,
)
from src.core.config import settings
from src.core.drift_alert_notifier import DriftAlertWebhookNotifier
from src.core.observability import record_calibration_drift_alert
from src.core.risk import get_risk_level
from src.core.trend_engine import logodds_to_prob
from src.storage.models import (
    EventItem,
    OutcomeType,
    RawItem,
    Source,
    Trend,
    TrendEvidence,
    TrendOutcome,
    TrendSnapshot,
)

logger = structlog.get_logger(__name__)


@dataclass
class CalibrationBucketSummary:
    """Reliability summary for one probability bucket."""

    bucket_start: float
    bucket_end: float
    prediction_count: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


@dataclass
class BrierTimeseriesPoint:
    """Mean Brier score over a fixed period."""

    period_start: datetime
    period_end: datetime
    mean_brier_score: float
    sample_size: int


@dataclass
class TrendMovement:
    """Compact trend movement summary."""

    trend_id: UUID
    trend_name: str
    current_probability: float
    weekly_change: float
    risk_level: str
    top_movers_7d: list[str]
    movement_chart: str


@dataclass
class CalibrationDriftAlert:
    """Calibration drift alert emitted when thresholds are breached."""

    alert_type: str
    severity: str
    metric_name: str
    metric_value: float
    threshold: float
    sample_size: int
    message: str


@dataclass
class TrendCoverageSummary:
    """Coverage stats for one trend in the dashboard window."""

    trend_id: UUID
    trend_name: str
    total_predictions: int
    resolved_predictions: int
    resolved_ratio: float


@dataclass
class CalibrationCoverageSummary:
    """Coverage guardrail summary for calibration windows."""

    min_resolved_per_trend: int
    min_resolved_ratio: float
    total_predictions: int
    resolved_predictions: int
    unresolved_predictions: int
    overall_resolved_ratio: float
    trends_with_predictions: int
    trends_meeting_min: int
    trends_below_min: int
    low_sample_trends: list[TrendCoverageSummary]
    coverage_sufficient: bool


@dataclass
class ReliabilityDiagnosticRow:
    """Advisory reliability row for source or source-tier diagnostics."""

    key: str
    label: str
    sample_size: int
    mean_predicted_probability: float
    observed_rate: float
    mean_brier_score: float
    calibration_gap: float
    confidence: str
    eligible: bool
    advisory_note: str


@dataclass
class ReliabilityDiagnosticsSummary:
    """Advisory diagnostics summary for one aggregation dimension."""

    dimension: str
    advisory_only: bool
    min_sample_size: int
    eligible_rows: int
    sparse_rows: int
    rows: list[ReliabilityDiagnosticRow]


@dataclass
class _ReliabilityAccumulator:
    """Internal aggregation state for diagnostics."""

    label: str
    outcome_ids: set[UUID] = field(default_factory=set)
    predicted_sum: float = 0.0
    actual_sum: float = 0.0
    brier_sum: float = 0.0


def _empty_reliability_summary(dimension: str) -> ReliabilityDiagnosticsSummary:
    return ReliabilityDiagnosticsSummary(
        dimension=dimension,
        advisory_only=True,
        min_sample_size=max(1, settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND),
        eligible_rows=0,
        sparse_rows=0,
        rows=[],
    )


@dataclass
class CalibrationDashboardReport:
    """Dashboard payload for calibration and movement visibility."""

    generated_at: datetime
    period_start: datetime
    period_end: datetime
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float | None
    calibration_curve: list[CalibrationBucketSummary]
    brier_score_over_time: list[BrierTimeseriesPoint]
    reliability_notes: list[str]
    trend_movements: list[TrendMovement]
    coverage: CalibrationCoverageSummary
    drift_alerts: list[CalibrationDriftAlert] = field(default_factory=list)
    source_reliability: ReliabilityDiagnosticsSummary = field(
        default_factory=lambda: _empty_reliability_summary("source")
    )
    source_tier_reliability: ReliabilityDiagnosticsSummary = field(
        default_factory=lambda: _empty_reliability_summary("source_tier")
    )


class CalibrationDashboardService:
    """Build dashboard views for calibration and trend movement."""

    def __init__(
        self,
        session: AsyncSession,
        drift_alert_notifier: DriftAlertWebhookNotifier | None = None,
    ):
        self.session = session
        self.drift_alert_notifier = (
            drift_alert_notifier
            if drift_alert_notifier is not None
            else DriftAlertWebhookNotifier.from_settings()
        )

    async def build_dashboard(
        self,
        *,
        trend_id: UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> CalibrationDashboardReport:
        period_end = normalize_utc(end_date) if end_date is not None else datetime.now(tz=UTC)
        period_start = (
            normalize_utc(start_date) if start_date is not None else period_end - timedelta(days=90)
        )

        outcomes = await self._load_outcomes(
            trend_id=trend_id,
            period_start=period_start,
            period_end=period_end,
        )
        scored_outcomes = self._scored_outcomes(outcomes)
        total_by_trend = self._count_predictions_by_trend(outcomes)
        resolved_by_trend = self._count_predictions_by_trend(scored_outcomes)
        trend_name_by_id = await self._load_trend_names(tuple(total_by_trend.keys()))
        coverage = self._build_coverage_summary(
            total_by_trend=total_by_trend,
            resolved_by_trend=resolved_by_trend,
            trend_name_by_id=trend_name_by_id,
        )
        (
            source_reliability,
            source_tier_reliability,
        ) = await self._build_source_reliability_diagnostics(scored_outcomes=scored_outcomes)
        calibration_curve = [
            CalibrationBucketSummary(
                bucket_start=bucket.bucket_start,
                bucket_end=bucket.bucket_end,
                prediction_count=bucket.prediction_count,
                actual_rate=bucket.actual_rate,
                expected_rate=bucket.expected_rate,
                calibration_error=bucket.calibration_error,
            )
            for bucket in build_calibration_buckets(scored_outcomes)
        ]
        brier_series = self._build_brier_timeseries(scored_outcomes, period_end=period_end)
        brier_values = [point.mean_brier_score for point in brier_series]
        mean_brier = sum(brier_values) / len(brier_values) if brier_values else None
        drift_alerts = self._build_drift_alerts(
            calibration_curve=calibration_curve,
            mean_brier_score=mean_brier,
            resolved_predictions=len(scored_outcomes),
            coverage=coverage,
        )
        generated_at = datetime.now(tz=UTC)
        await self._emit_drift_notifications(
            trend_id=trend_id,
            drift_alerts=drift_alerts,
            generated_at=generated_at,
        )

        movements = await self._load_trend_movements(
            trend_id=trend_id,
            period_end=period_end,
        )

        return CalibrationDashboardReport(
            generated_at=generated_at,
            period_start=period_start,
            period_end=period_end,
            total_predictions=len(outcomes),
            resolved_predictions=len(scored_outcomes),
            mean_brier_score=mean_brier,
            calibration_curve=calibration_curve,
            brier_score_over_time=brier_series,
            reliability_notes=self._build_reliability_notes(calibration_curve),
            trend_movements=movements,
            coverage=coverage,
            drift_alerts=drift_alerts,
            source_reliability=source_reliability,
            source_tier_reliability=source_tier_reliability,
        )

    def _build_drift_alerts(
        self,
        *,
        calibration_curve: list[CalibrationBucketSummary],
        mean_brier_score: float | None,
        resolved_predictions: int,
        coverage: CalibrationCoverageSummary,
    ) -> list[CalibrationDriftAlert]:
        alerts = self._build_coverage_alerts(coverage)
        if resolved_predictions < settings.CALIBRATION_DRIFT_MIN_RESOLVED_OUTCOMES:
            return alerts

        if mean_brier_score is not None:
            severity, threshold = self._severity_and_threshold(
                value=mean_brier_score,
                warn_threshold=settings.CALIBRATION_DRIFT_BRIER_WARN_THRESHOLD,
                critical_threshold=settings.CALIBRATION_DRIFT_BRIER_CRITICAL_THRESHOLD,
            )
            if severity is not None and threshold is not None:
                alerts.append(
                    CalibrationDriftAlert(
                        alert_type="mean_brier_drift",
                        severity=severity,
                        metric_name="mean_brier_score",
                        metric_value=round(mean_brier_score, 6),
                        threshold=threshold,
                        sample_size=resolved_predictions,
                        message=(
                            "Mean Brier score exceeded calibration drift threshold "
                            f"({mean_brier_score:.3f} >= {threshold:.3f})."
                        ),
                    )
                )

        if calibration_curve:
            worst_bucket = max(calibration_curve, key=lambda bucket: bucket.calibration_error)
            severity, threshold = self._severity_and_threshold(
                value=worst_bucket.calibration_error,
                warn_threshold=settings.CALIBRATION_DRIFT_BUCKET_ERROR_WARN_THRESHOLD,
                critical_threshold=settings.CALIBRATION_DRIFT_BUCKET_ERROR_CRITICAL_THRESHOLD,
            )
            if severity is not None and threshold is not None:
                alerts.append(
                    CalibrationDriftAlert(
                        alert_type="bucket_error_drift",
                        severity=severity,
                        metric_name="max_bucket_calibration_error",
                        metric_value=round(worst_bucket.calibration_error, 6),
                        threshold=threshold,
                        sample_size=worst_bucket.prediction_count,
                        message=(
                            "Calibration bucket error exceeded threshold for "
                            f"{worst_bucket.bucket_start:.0%}-{worst_bucket.bucket_end:.0%} "
                            f"({worst_bucket.calibration_error:.3f} >= {threshold:.3f})."
                        ),
                    )
                )

        return alerts

    def _build_coverage_alerts(
        self,
        coverage: CalibrationCoverageSummary,
    ) -> list[CalibrationDriftAlert]:
        alerts: list[CalibrationDriftAlert] = []
        if coverage.total_predictions == 0:
            alerts.append(
                CalibrationDriftAlert(
                    alert_type="low_sample_coverage",
                    severity="warning",
                    metric_name="resolved_predictions_total",
                    metric_value=0.0,
                    threshold=float(settings.CALIBRATION_DRIFT_MIN_RESOLVED_OUTCOMES),
                    sample_size=0,
                    message="No calibration predictions found in the dashboard window.",
                )
            )
            return alerts

        if coverage.overall_resolved_ratio < settings.CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO:
            alerts.append(
                CalibrationDriftAlert(
                    alert_type="low_sample_coverage",
                    severity="warning",
                    metric_name="overall_resolved_ratio",
                    metric_value=coverage.overall_resolved_ratio,
                    threshold=settings.CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO,
                    sample_size=coverage.total_predictions,
                    message=(
                        "Calibration resolved ratio is below guardrail "
                        f"({coverage.overall_resolved_ratio:.2f} < "
                        f"{settings.CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO:.2f})."
                    ),
                )
            )

        if coverage.trends_below_min > 0:
            trend_names = ", ".join(row.trend_name for row in coverage.low_sample_trends[:5])
            alerts.append(
                CalibrationDriftAlert(
                    alert_type="low_sample_coverage",
                    severity="warning",
                    metric_name="trends_below_min_resolved",
                    metric_value=float(coverage.trends_below_min),
                    threshold=float(settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND),
                    sample_size=coverage.trends_with_predictions,
                    message=(
                        f"Some trends are below minimum resolved-outcome coverage: {trend_names}."
                    ),
                )
            )
        return alerts

    @staticmethod
    def _severity_and_threshold(
        *,
        value: float,
        warn_threshold: float,
        critical_threshold: float,
    ) -> tuple[str | None, float | None]:
        if value >= critical_threshold:
            return "critical", critical_threshold
        if value >= warn_threshold:
            return "warning", warn_threshold
        return None, None

    async def _emit_drift_notifications(
        self,
        *,
        trend_id: UUID | None,
        drift_alerts: list[CalibrationDriftAlert],
        generated_at: datetime,
    ) -> None:
        if not drift_alerts:
            return

        trend_scope = str(trend_id) if trend_id is not None else "all_trends"
        for alert in drift_alerts:
            record_calibration_drift_alert(
                alert_type=alert.alert_type,
                severity=alert.severity,
            )
            logger.warning(
                "Calibration drift alert",
                trend_scope=trend_scope,
                alert_type=alert.alert_type,
                severity=alert.severity,
                metric_name=alert.metric_name,
                metric_value=alert.metric_value,
                threshold=alert.threshold,
                sample_size=alert.sample_size,
                message=alert.message,
            )
        try:
            await self.drift_alert_notifier.notify(
                trend_scope=trend_scope,
                generated_at=generated_at,
                alerts=[asdict(alert) for alert in drift_alerts],
            )
        except Exception as exc:  # pragma: no cover - defensive safety net
            logger.warning(
                "Calibration drift webhook notifier failed unexpectedly",
                trend_scope=trend_scope,
                error=str(exc),
            )

    async def _load_outcomes(
        self,
        *,
        trend_id: UUID | None,
        period_start: datetime,
        period_end: datetime,
    ) -> list[TrendOutcome]:
        query = (
            select(TrendOutcome)
            .where(TrendOutcome.prediction_date >= period_start)
            .where(TrendOutcome.prediction_date <= period_end)
            .order_by(TrendOutcome.prediction_date.asc())
        )
        if trend_id is not None:
            query = query.where(TrendOutcome.trend_id == trend_id)
        return list((await self.session.scalars(query)).all())

    async def _load_trend_names(
        self,
        trend_ids: tuple[UUID, ...],
    ) -> dict[UUID, str]:
        if not trend_ids:
            return {}
        rows = (
            await self.session.execute(select(Trend.id, Trend.name).where(Trend.id.in_(trend_ids)))
        ).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _count_predictions_by_trend(outcomes: list[TrendOutcome]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        for outcome in outcomes:
            counts[outcome.trend_id] = counts.get(outcome.trend_id, 0) + 1
        return counts

    def _build_coverage_summary(
        self,
        *,
        total_by_trend: dict[UUID, int],
        resolved_by_trend: dict[UUID, int],
        trend_name_by_id: dict[UUID, str],
    ) -> CalibrationCoverageSummary:
        per_trend: list[TrendCoverageSummary] = []
        for trend_id, total_predictions in total_by_trend.items():
            resolved_predictions = resolved_by_trend.get(trend_id, 0)
            ratio = resolved_predictions / total_predictions if total_predictions > 0 else 0.0
            per_trend.append(
                TrendCoverageSummary(
                    trend_id=trend_id,
                    trend_name=trend_name_by_id.get(trend_id, str(trend_id)),
                    total_predictions=total_predictions,
                    resolved_predictions=resolved_predictions,
                    resolved_ratio=round(ratio, 6),
                )
            )

        low_sample_trends = sorted(
            [
                row
                for row in per_trend
                if row.resolved_predictions < settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND
            ],
            key=lambda row: (row.resolved_predictions, row.trend_name),
        )

        total_predictions = sum(total_by_trend.values())
        resolved_predictions = sum(resolved_by_trend.values())
        unresolved_predictions = max(0, total_predictions - resolved_predictions)
        overall_resolved_ratio = (
            round(resolved_predictions / total_predictions, 6) if total_predictions > 0 else 0.0
        )
        trends_with_predictions = len(total_by_trend)
        trends_below_min = len(low_sample_trends)
        trends_meeting_min = max(0, trends_with_predictions - trends_below_min)
        coverage_sufficient = (
            trends_with_predictions > 0
            and trends_below_min == 0
            and overall_resolved_ratio >= settings.CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO
        )

        return CalibrationCoverageSummary(
            min_resolved_per_trend=settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND,
            min_resolved_ratio=settings.CALIBRATION_COVERAGE_MIN_RESOLVED_RATIO,
            total_predictions=total_predictions,
            resolved_predictions=resolved_predictions,
            unresolved_predictions=unresolved_predictions,
            overall_resolved_ratio=overall_resolved_ratio,
            trends_with_predictions=trends_with_predictions,
            trends_meeting_min=trends_meeting_min,
            trends_below_min=trends_below_min,
            low_sample_trends=low_sample_trends,
            coverage_sufficient=coverage_sufficient,
        )

    async def _build_source_reliability_diagnostics(
        self,
        *,
        scored_outcomes: list[TrendOutcome],
    ) -> tuple[ReliabilityDiagnosticsSummary, ReliabilityDiagnosticsSummary]:
        min_sample_size = max(1, settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND)
        outcome_metrics: dict[UUID, tuple[float, float, float]] = {}

        for outcome in scored_outcomes:
            if outcome.outcome is None:
                continue
            try:
                outcome_type = OutcomeType(outcome.outcome)
            except ValueError:
                continue

            actual = self._actual_outcome_value(outcome_type)
            if actual is None:
                continue

            predicted_probability = float(outcome.predicted_probability)
            brier_score = (
                float(outcome.brier_score)
                if outcome.brier_score is not None
                else calculate_brier_score(predicted_probability, outcome_type)
            )
            if brier_score is None:
                continue

            outcome_metrics[outcome.id] = (
                predicted_probability,
                actual,
                brier_score,
            )

        if not outcome_metrics:
            return (
                _empty_reliability_summary("source"),
                _empty_reliability_summary("source_tier"),
            )

        pair_query = (
            select(
                TrendOutcome.id,
                Source.id,
                Source.name,
                Source.source_tier,
            )
            .select_from(TrendOutcome)
            .join(
                TrendEvidence,
                (TrendEvidence.trend_id == TrendOutcome.trend_id)
                & (TrendEvidence.created_at <= TrendOutcome.prediction_date),
            )
            .join(EventItem, EventItem.event_id == TrendEvidence.event_id)
            .join(RawItem, RawItem.id == EventItem.item_id)
            .join(Source, Source.id == RawItem.source_id)
            .where(TrendOutcome.id.in_(tuple(outcome_metrics.keys())))
            .distinct()
        )
        rows = (await self.session.execute(pair_query)).all()

        source_pairs: list[tuple[str, str, UUID]] = []
        tier_pairs: list[tuple[str, str, UUID]] = []

        for outcome_id, source_id, source_name, source_tier in rows:
            source_pairs.append((str(source_id), source_name, outcome_id))
            tier_label = source_tier or "unknown"
            tier_pairs.append((tier_label, tier_label, outcome_id))

        source_reliability = self._build_reliability_summary_from_pairs(
            dimension="source",
            min_sample_size=min_sample_size,
            pairs=source_pairs,
            outcome_metrics=outcome_metrics,
        )
        source_tier_reliability = self._build_reliability_summary_from_pairs(
            dimension="source_tier",
            min_sample_size=min_sample_size,
            pairs=tier_pairs,
            outcome_metrics=outcome_metrics,
        )
        return source_reliability, source_tier_reliability

    def _build_reliability_summary_from_pairs(
        self,
        *,
        dimension: str,
        min_sample_size: int,
        pairs: list[tuple[str, str, UUID]],
        outcome_metrics: dict[UUID, tuple[float, float, float]],
    ) -> ReliabilityDiagnosticsSummary:
        accumulators: dict[str, _ReliabilityAccumulator] = {}

        for key, label, outcome_id in pairs:
            metrics = outcome_metrics.get(outcome_id)
            if metrics is None:
                continue
            accumulator = accumulators.setdefault(key, _ReliabilityAccumulator(label=label))
            if outcome_id in accumulator.outcome_ids:
                continue

            predicted_probability, actual_rate, brier_score = metrics
            accumulator.outcome_ids.add(outcome_id)
            accumulator.predicted_sum += predicted_probability
            accumulator.actual_sum += actual_rate
            accumulator.brier_sum += brier_score

        rows: list[ReliabilityDiagnosticRow] = []
        for key, accumulator in accumulators.items():
            sample_size = len(accumulator.outcome_ids)
            if sample_size == 0:
                continue

            mean_predicted_probability = accumulator.predicted_sum / sample_size
            observed_rate = accumulator.actual_sum / sample_size
            mean_brier_score = accumulator.brier_sum / sample_size
            calibration_gap = abs(observed_rate - mean_predicted_probability)
            eligible = sample_size >= min_sample_size
            rows.append(
                ReliabilityDiagnosticRow(
                    key=key,
                    label=accumulator.label,
                    sample_size=sample_size,
                    mean_predicted_probability=round(mean_predicted_probability, 6),
                    observed_rate=round(observed_rate, 6),
                    mean_brier_score=round(mean_brier_score, 6),
                    calibration_gap=round(calibration_gap, 6),
                    confidence=self._confidence_band(
                        sample_size=sample_size,
                        min_sample_size=min_sample_size,
                    ),
                    eligible=eligible,
                    advisory_note=self._advisory_note(
                        sample_size=sample_size,
                        min_sample_size=min_sample_size,
                    ),
                )
            )

        rows.sort(key=lambda row: (row.sample_size, row.calibration_gap), reverse=True)
        eligible_rows = sum(1 for row in rows if row.eligible)
        sparse_rows = len(rows) - eligible_rows
        return ReliabilityDiagnosticsSummary(
            dimension=dimension,
            advisory_only=True,
            min_sample_size=min_sample_size,
            eligible_rows=eligible_rows,
            sparse_rows=sparse_rows,
            rows=rows,
        )

    @staticmethod
    def _actual_outcome_value(outcome_type: OutcomeType) -> float | None:
        if outcome_type == OutcomeType.OCCURRED:
            return 1.0
        if outcome_type == OutcomeType.DID_NOT_OCCUR:
            return 0.0
        if outcome_type == OutcomeType.PARTIAL:
            return 0.5
        return None

    @staticmethod
    def _confidence_band(
        *,
        sample_size: int,
        min_sample_size: int,
    ) -> str:
        if sample_size < min_sample_size:
            return "insufficient"
        if sample_size >= min_sample_size * 3:
            return "high"
        if sample_size >= min_sample_size * 2:
            return "medium"
        return "low"

    @staticmethod
    def _advisory_note(
        *,
        sample_size: int,
        min_sample_size: int,
    ) -> str:
        if sample_size < min_sample_size:
            return (
                "Sparse sample. Advisory-only diagnostic; do not mutate source weighting from "
                "this row without additional outcomes."
            )
        return (
            "Advisory-only diagnostic. Requires analyst review before any source-weighting changes."
        )

    def _scored_outcomes(self, outcomes: list[TrendOutcome]) -> list[TrendOutcome]:
        scored: list[TrendOutcome] = []
        for outcome in outcomes:
            if outcome.outcome is None:
                continue
            try:
                outcome_type = OutcomeType(outcome.outcome)
            except ValueError:
                continue
            if (
                calculate_brier_score(float(outcome.predicted_probability), outcome_type)
                is not None
            ):
                scored.append(outcome)
        return scored

    def _build_brier_timeseries(
        self,
        outcomes: list[TrendOutcome],
        *,
        period_end: datetime,
    ) -> list[BrierTimeseriesPoint]:
        grouped: dict[datetime, list[float]] = {}
        for outcome in outcomes:
            if outcome.outcome is None:
                continue
            try:
                outcome_type = OutcomeType(outcome.outcome)
            except ValueError:
                continue

            score = (
                float(outcome.brier_score)
                if outcome.brier_score is not None
                else calculate_brier_score(float(outcome.predicted_probability), outcome_type)
            )
            if score is None:
                continue

            prediction_date = normalize_utc(outcome.prediction_date)
            day_start = datetime(
                year=prediction_date.year,
                month=prediction_date.month,
                day=prediction_date.day,
                tzinfo=UTC,
            )
            week_start = day_start - timedelta(days=day_start.weekday())
            grouped.setdefault(week_start, []).append(score)

        points: list[BrierTimeseriesPoint] = []
        for week_start in sorted(grouped.keys()):
            values = grouped[week_start]
            if not values:
                continue
            week_end = min(week_start + timedelta(days=7), period_end)
            points.append(
                BrierTimeseriesPoint(
                    period_start=week_start,
                    period_end=week_end,
                    mean_brier_score=sum(values) / len(values),
                    sample_size=len(values),
                )
            )
        return points

    def _build_reliability_notes(
        self,
        buckets: list[CalibrationBucketSummary],
    ) -> list[str]:
        notes: list[str] = []
        for bucket in buckets:
            notes.append(
                "When we predicted "
                f"{bucket.bucket_start:.0%}-{bucket.bucket_end:.0%}, "
                f"it happened {bucket.actual_rate:.0%} of the time "
                f"(n={bucket.prediction_count})."
            )
        return notes

    async def _load_trend_movements(
        self,
        *,
        trend_id: UUID | None,
        period_end: datetime,
    ) -> list[TrendMovement]:
        trends_query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        if trend_id is not None:
            trends_query = trends_query.where(Trend.id == trend_id)
        trends = list((await self.session.scalars(trends_query)).all())

        trend_movements: list[TrendMovement] = []
        for trend in trends:
            current_probability = logodds_to_prob(float(trend.current_log_odds))
            weekly_change = await self._calculate_weekly_change(
                trend_id=trend.id,
                current_probability=current_probability,
                as_of=period_end,
            )
            top_movers = await self._load_top_movers(
                trend_id=trend.id,
                as_of=period_end,
            )
            chart = await self._build_movement_chart(
                trend_id=trend.id,
                current_probability=current_probability,
                as_of=period_end,
            )
            trend_movements.append(
                TrendMovement(
                    trend_id=trend.id,
                    trend_name=trend.name,
                    current_probability=current_probability,
                    weekly_change=weekly_change,
                    risk_level=get_risk_level(current_probability).value,
                    top_movers_7d=top_movers,
                    movement_chart=chart,
                )
            )
        return trend_movements

    async def _calculate_weekly_change(
        self,
        *,
        trend_id: UUID,
        current_probability: float,
        as_of: datetime,
    ) -> float:
        week_ago = as_of - timedelta(days=7)
        past_log_odds = await self.session.scalar(
            select(TrendSnapshot.log_odds)
            .where(TrendSnapshot.trend_id == trend_id)
            .where(TrendSnapshot.timestamp <= week_ago)
            .order_by(TrendSnapshot.timestamp.desc())
            .limit(1)
        )
        if past_log_odds is None:
            return 0.0
        past_probability = logodds_to_prob(float(past_log_odds))
        return current_probability - past_probability

    async def _load_top_movers(
        self,
        *,
        trend_id: UUID,
        as_of: datetime,
        limit: int = 3,
    ) -> list[str]:
        since = as_of - timedelta(days=7)
        query = (
            select(TrendEvidence)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= since)
            .where(TrendEvidence.created_at <= as_of)
            .order_by(func.abs(TrendEvidence.delta_log_odds).desc())
            .limit(limit)
        )
        evidence_rows = list((await self.session.scalars(query)).all())
        labels = [row.reasoning.strip() for row in evidence_rows if row.reasoning]
        if labels:
            return labels
        return [row.signal_type for row in evidence_rows]

    async def _build_movement_chart(
        self,
        *,
        trend_id: UUID,
        current_probability: float,
        as_of: datetime,
        max_points: int = 12,
    ) -> str:
        since = as_of - timedelta(days=28)
        query = (
            select(TrendSnapshot.log_odds)
            .where(TrendSnapshot.trend_id == trend_id)
            .where(TrendSnapshot.timestamp >= since)
            .where(TrendSnapshot.timestamp <= as_of)
            .order_by(TrendSnapshot.timestamp.asc())
            .limit(max_points)
        )
        snapshot_log_odds = list((await self.session.scalars(query)).all())
        probabilities = [logodds_to_prob(float(log_odds)) for log_odds in snapshot_log_odds]
        if not probabilities or abs(probabilities[-1] - current_probability) > 1e-9:
            probabilities.append(current_probability)
        return self._render_ascii_sparkline(probabilities[-max_points:])

    def _render_ascii_sparkline(self, values: list[float]) -> str:
        if not values:
            return ""
        if len(values) == 1:
            return "-"

        low = min(values)
        high = max(values)
        if abs(high - low) < 1e-9:
            return "-" * len(values)

        levels = "._-~=+*#%@"
        span = high - low
        chars: list[str] = []
        for value in values:
            ratio = (value - low) / span
            index = min(int(ratio * (len(levels) - 1)), len(levels) - 1)
            chars.append(levels[index])
        return "".join(chars)
