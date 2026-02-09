"""
Calibration dashboard and trend visibility helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from src.core.observability import record_calibration_drift_alert
from src.core.risk import get_risk_level
from src.core.trend_engine import logodds_to_prob
from src.storage.models import OutcomeType, Trend, TrendEvidence, TrendOutcome, TrendSnapshot

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
    drift_alerts: list[CalibrationDriftAlert] = field(default_factory=list)


class CalibrationDashboardService:
    """Build dashboard views for calibration and trend movement."""

    def __init__(self, session: AsyncSession):
        self.session = session

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
        )
        self._emit_drift_notifications(
            trend_id=trend_id,
            drift_alerts=drift_alerts,
        )

        movements = await self._load_trend_movements(
            trend_id=trend_id,
            period_end=period_end,
        )

        return CalibrationDashboardReport(
            generated_at=datetime.now(tz=UTC),
            period_start=period_start,
            period_end=period_end,
            total_predictions=len(outcomes),
            resolved_predictions=len(scored_outcomes),
            mean_brier_score=mean_brier,
            calibration_curve=calibration_curve,
            brier_score_over_time=brier_series,
            reliability_notes=self._build_reliability_notes(calibration_curve),
            trend_movements=movements,
            drift_alerts=drift_alerts,
        )

    def _build_drift_alerts(
        self,
        *,
        calibration_curve: list[CalibrationBucketSummary],
        mean_brier_score: float | None,
        resolved_predictions: int,
    ) -> list[CalibrationDriftAlert]:
        if resolved_predictions < settings.CALIBRATION_DRIFT_MIN_RESOLVED_OUTCOMES:
            return []

        alerts: list[CalibrationDriftAlert] = []
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

    def _emit_drift_notifications(
        self,
        *,
        trend_id: UUID | None,
        drift_alerts: list[CalibrationDriftAlert],
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
