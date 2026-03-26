"""
Advisory source reliability diagnostics for calibration reporting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.calibration import calculate_brier_score, normalize_utc
from src.core.config import settings
from src.core.source_credibility import effective_source_credibility
from src.storage.models import (
    Event,
    EventItem,
    OutcomeType,
    RawItem,
    Source,
    TrendEvidence,
    TrendOutcome,
)

RECENT_WINDOW_DAYS = 30
MIN_RECENT_SAMPLE_SIZE = 2
STABLE_DRIFT_THRESHOLD = 0.08
ADVISORY_BLEND_FACTOR = 0.25
MAX_ADVISORY_DELTA = 0.12


@dataclass(frozen=True)
class OutcomeReliabilityMetrics:
    """Resolved outcome metrics used by advisory reliability diagnostics."""

    predicted_probability: float
    actual_rate: float
    brier_score: float
    prediction_date: datetime | None = None


@dataclass
class ReliabilityDiagnosticRow:
    """Advisory reliability row for a diagnostic dimension."""

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
    recent_sample_size: int = 0
    baseline_sample_size: int = 0
    recent_observed_rate: float | None = None
    baseline_observed_rate: float | None = None
    drift_state: str = "insufficient_recent_data"
    configured_effective_credibility: float | None = None
    advisory_delta: float | None = None
    advisory_effective_credibility: float | None = None


@dataclass
class ReliabilityDiagnosticsSummary:
    """Advisory diagnostics summary for one aggregation dimension."""

    dimension: str
    advisory_only: bool
    min_sample_size: int
    eligible_rows: int
    sparse_rows: int
    rows: list[ReliabilityDiagnosticRow]
    recent_window_days: int = RECENT_WINDOW_DAYS


@dataclass
class ReliabilityDiagnosticsBundle:
    """All advisory reliability dimensions carried by the dashboard."""

    source_reliability: ReliabilityDiagnosticsSummary
    source_tier_reliability: ReliabilityDiagnosticsSummary
    geography_reliability: ReliabilityDiagnosticsSummary
    topic_family_reliability: ReliabilityDiagnosticsSummary


@dataclass
class _ReliabilityAccumulator:
    """Internal aggregation state for diagnostics."""

    label: str
    outcome_ids: set[UUID] = field(default_factory=set)
    predicted_sum: float = 0.0
    actual_sum: float = 0.0
    brier_sum: float = 0.0
    recent_outcome_ids: set[UUID] = field(default_factory=set)
    recent_actual_sum: float = 0.0
    baseline_outcome_ids: set[UUID] = field(default_factory=set)
    baseline_actual_sum: float = 0.0


def empty_reliability_summary(dimension: str) -> ReliabilityDiagnosticsSummary:
    """Return an empty advisory diagnostics payload."""
    return ReliabilityDiagnosticsSummary(
        dimension=dimension,
        advisory_only=True,
        min_sample_size=max(1, settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND),
        eligible_rows=0,
        sparse_rows=0,
        rows=[],
    )


def actual_outcome_value(outcome_type: OutcomeType) -> float | None:
    """Map supported outcome states onto numeric calibration outcomes."""
    if outcome_type == OutcomeType.OCCURRED:
        return 1.0
    if outcome_type == OutcomeType.DID_NOT_OCCUR:
        return 0.0
    if outcome_type == OutcomeType.PARTIAL:
        return 0.5
    return None


def confidence_band(*, sample_size: int, min_sample_size: int) -> str:
    """Map sample size onto a coarse confidence band."""
    if sample_size < min_sample_size:
        return "insufficient"
    if sample_size >= min_sample_size * 3:
        return "high"
    if sample_size >= min_sample_size * 2:
        return "medium"
    return "low"


def advisory_note(
    *,
    sample_size: int,
    min_sample_size: int,
    drift_state: str = "insufficient_recent_data",
    advisory_delta: float | None = None,
) -> str:
    """Describe how operators should interpret one advisory diagnostic row."""
    if sample_size < min_sample_size:
        return (
            "Sparse sample. Advisory-only diagnostic; do not mutate source weighting from "
            "this row without additional outcomes."
        )
    if drift_state in {"insufficient_recent_data", "no_baseline_window"}:
        return (
            "Advisory-only diagnostic. Recent-window credibility adjustment is suppressed "
            "until more outcomes accumulate."
        )
    if drift_state == "stable":
        return (
            "Advisory-only diagnostic. Recent window is stable versus baseline; keep "
            "configured credibility unchanged."
        )
    if advisory_delta is None:
        return (
            "Advisory-only diagnostic. Requires analyst review before any source-weighting changes."
        )
    direction = "increase" if advisory_delta > 0 else "decrease"
    return (
        "Advisory-only diagnostic. Recent outcomes suggest a bounded "
        f"{direction} of {abs(advisory_delta):.3f} after analyst review."
    )


def build_reliability_summary_from_pairs(
    *,
    dimension: str,
    min_sample_size: int,
    pairs: list[tuple[str, str, UUID]],
    outcome_metrics: Mapping[UUID, tuple[float, float, float] | OutcomeReliabilityMetrics],
    reference_credibility_by_key: dict[str, float] | None = None,
    recent_window_days: int = RECENT_WINDOW_DAYS,
) -> ReliabilityDiagnosticsSummary:
    """Aggregate advisory reliability rows by dimension."""
    accumulators: dict[str, _ReliabilityAccumulator] = {}
    latest_prediction_date = _latest_prediction_date(outcome_metrics)
    recent_cutoff = (
        latest_prediction_date - timedelta(days=recent_window_days)
        if latest_prediction_date is not None
        else None
    )

    for key, label, outcome_id in pairs:
        metrics = _coerce_metrics(outcome_metrics.get(outcome_id))
        if metrics is None:
            continue
        accumulator = accumulators.setdefault(key, _ReliabilityAccumulator(label=label))
        if outcome_id in accumulator.outcome_ids:
            continue

        accumulator.outcome_ids.add(outcome_id)
        accumulator.predicted_sum += metrics.predicted_probability
        accumulator.actual_sum += metrics.actual_rate
        accumulator.brier_sum += metrics.brier_score
        _update_window_totals(
            accumulator=accumulator,
            outcome_id=outcome_id,
            prediction_date=metrics.prediction_date,
            actual_rate=metrics.actual_rate,
            recent_cutoff=recent_cutoff,
        )

    rows = _build_rows(
        accumulators=accumulators,
        min_sample_size=min_sample_size,
        reference_credibility_by_key=reference_credibility_by_key or {},
    )
    eligible_rows = sum(1 for row in rows if row.eligible)
    return ReliabilityDiagnosticsSummary(
        dimension=dimension,
        advisory_only=True,
        min_sample_size=min_sample_size,
        eligible_rows=eligible_rows,
        sparse_rows=len(rows) - eligible_rows,
        rows=rows,
        recent_window_days=recent_window_days,
    )


async def build_source_reliability_diagnostics(
    *,
    session: AsyncSession,
    scored_outcomes: list[TrendOutcome],
) -> ReliabilityDiagnosticsBundle:
    """Build advisory reliability diagnostics across bounded dimensions."""
    min_sample_size = max(1, settings.CALIBRATION_COVERAGE_MIN_RESOLVED_PER_TREND)
    outcome_metrics = _build_outcome_metrics(scored_outcomes)
    if not outcome_metrics:
        return ReliabilityDiagnosticsBundle(
            source_reliability=empty_reliability_summary("source"),
            source_tier_reliability=empty_reliability_summary("source_tier"),
            geography_reliability=empty_reliability_summary("geography"),
            topic_family_reliability=empty_reliability_summary("topic_family"),
        )

    pair_query = (
        select(
            TrendOutcome.id,
            Source.id,
            Source.name,
            Source.credibility_score,
            Source.source_tier,
            Source.reporting_type,
            Event.extracted_where,
            Event.categories,
        )
        .select_from(TrendOutcome)
        .join(
            TrendEvidence,
            (TrendEvidence.trend_id == TrendOutcome.trend_id)
            & (TrendEvidence.created_at <= TrendOutcome.prediction_date),
        )
        .join(Event, Event.id == TrendEvidence.event_id)
        .join(EventItem, EventItem.event_id == TrendEvidence.event_id)
        .join(RawItem, RawItem.id == EventItem.item_id)
        .join(Source, Source.id == RawItem.source_id)
        .where(TrendOutcome.id.in_(tuple(outcome_metrics.keys())))
        .where(TrendEvidence.is_invalidated.is_(False))
        .distinct()
    )
    rows = (await session.execute(pair_query)).all()

    source_pairs: list[tuple[str, str, UUID]] = []
    tier_pairs: list[tuple[str, str, UUID]] = []
    geography_pairs: list[tuple[str, str, UUID]] = []
    topic_pairs: list[tuple[str, str, UUID]] = []
    source_reference: dict[str, list[float]] = {}

    for (
        outcome_id,
        source_id,
        source_name,
        base_credibility,
        source_tier,
        reporting_type,
        where,
        categories,
    ) in rows:
        source_key = str(source_id)
        source_label = str(source_name or source_key)
        source_pairs.append((source_key, source_label, outcome_id))
        tier_label = str(source_tier or "unknown")
        tier_pairs.append((tier_label, tier_label, outcome_id))
        source_reference.setdefault(source_key, []).append(
            effective_source_credibility(
                base_credibility=base_credibility,
                source_tier=source_tier,
                reporting_type=reporting_type,
            )
        )
        geography_label = _normalize_geography(where)
        if geography_label is not None:
            geography_pairs.append((geography_label.casefold(), geography_label, outcome_id))
        for topic_label in _normalize_topics(categories):
            topic_pairs.append((topic_label.casefold(), topic_label, outcome_id))

    source_reference_by_key = {
        key: round(sum(values) / len(values), 6)
        for key, values in source_reference.items()
        if values
    }
    return ReliabilityDiagnosticsBundle(
        source_reliability=build_reliability_summary_from_pairs(
            dimension="source",
            min_sample_size=min_sample_size,
            pairs=source_pairs,
            outcome_metrics=outcome_metrics,
            reference_credibility_by_key=source_reference_by_key,
        ),
        source_tier_reliability=build_reliability_summary_from_pairs(
            dimension="source_tier",
            min_sample_size=min_sample_size,
            pairs=tier_pairs,
            outcome_metrics=outcome_metrics,
        ),
        geography_reliability=build_reliability_summary_from_pairs(
            dimension="geography",
            min_sample_size=min_sample_size,
            pairs=geography_pairs,
            outcome_metrics=outcome_metrics,
        ),
        topic_family_reliability=build_reliability_summary_from_pairs(
            dimension="topic_family",
            min_sample_size=min_sample_size,
            pairs=topic_pairs,
            outcome_metrics=outcome_metrics,
        ),
    )


def _build_outcome_metrics(
    scored_outcomes: list[TrendOutcome],
) -> dict[UUID, OutcomeReliabilityMetrics]:
    metrics: dict[UUID, OutcomeReliabilityMetrics] = {}
    for outcome in scored_outcomes:
        if outcome.outcome is None:
            continue
        try:
            outcome_type = OutcomeType(outcome.outcome)
        except ValueError:
            continue
        actual_rate = actual_outcome_value(outcome_type)
        if actual_rate is None:
            continue
        predicted_probability = float(outcome.predicted_probability)
        brier_score = (
            float(outcome.brier_score)
            if outcome.brier_score is not None
            else calculate_brier_score(predicted_probability, outcome_type)
        )
        if brier_score is None:
            continue
        metrics[outcome.id] = OutcomeReliabilityMetrics(
            predicted_probability=predicted_probability,
            actual_rate=actual_rate,
            brier_score=brier_score,
            prediction_date=normalize_utc(outcome.prediction_date)
            if getattr(outcome, "prediction_date", None) is not None
            else None,
        )
    return metrics


def _coerce_metrics(
    metrics: tuple[float, float, float] | OutcomeReliabilityMetrics | None,
) -> OutcomeReliabilityMetrics | None:
    if metrics is None:
        return None
    if isinstance(metrics, OutcomeReliabilityMetrics):
        return metrics
    predicted_probability, actual_rate, brier_score = metrics
    return OutcomeReliabilityMetrics(
        predicted_probability=predicted_probability,
        actual_rate=actual_rate,
        brier_score=brier_score,
        prediction_date=None,
    )


def _latest_prediction_date(
    outcome_metrics: Mapping[UUID, tuple[float, float, float] | OutcomeReliabilityMetrics],
) -> datetime | None:
    dates = [
        metrics.prediction_date
        for metrics in (_coerce_metrics(value) for value in outcome_metrics.values())
        if metrics is not None and metrics.prediction_date is not None
    ]
    return max(dates) if dates else None


def _update_window_totals(
    *,
    accumulator: _ReliabilityAccumulator,
    outcome_id: UUID,
    prediction_date: datetime | None,
    actual_rate: float,
    recent_cutoff: datetime | None,
) -> None:
    if recent_cutoff is None or prediction_date is None:
        return
    if prediction_date >= recent_cutoff:
        accumulator.recent_outcome_ids.add(outcome_id)
        accumulator.recent_actual_sum += actual_rate
        return
    accumulator.baseline_outcome_ids.add(outcome_id)
    accumulator.baseline_actual_sum += actual_rate


def _build_rows(
    *,
    accumulators: dict[str, _ReliabilityAccumulator],
    min_sample_size: int,
    reference_credibility_by_key: dict[str, float],
) -> list[ReliabilityDiagnosticRow]:
    rows: list[ReliabilityDiagnosticRow] = []
    recent_min_sample_size = max(MIN_RECENT_SAMPLE_SIZE, min_sample_size // 2)

    for key, accumulator in accumulators.items():
        sample_size = len(accumulator.outcome_ids)
        mean_predicted_probability = accumulator.predicted_sum / sample_size
        observed_rate = accumulator.actual_sum / sample_size
        mean_brier_score = accumulator.brier_sum / sample_size
        calibration_gap = abs(observed_rate - mean_predicted_probability)
        recent_sample_size = len(accumulator.recent_outcome_ids)
        baseline_sample_size = len(accumulator.baseline_outcome_ids)
        recent_observed_rate = _safe_average(accumulator.recent_actual_sum, recent_sample_size)
        baseline_observed_rate = _safe_average(
            accumulator.baseline_actual_sum, baseline_sample_size
        )
        drift_state, advisory_delta = _time_varying_signal(
            min_sample_size=min_sample_size,
            recent_min_sample_size=recent_min_sample_size,
            recent_sample_size=recent_sample_size,
            baseline_sample_size=baseline_sample_size,
            recent_observed_rate=recent_observed_rate,
            baseline_observed_rate=baseline_observed_rate,
        )
        configured_effective_credibility = reference_credibility_by_key.get(key)
        advisory_effective_credibility = _advisory_effective_credibility(
            configured_effective_credibility=configured_effective_credibility,
            advisory_delta=advisory_delta,
        )
        rows.append(
            ReliabilityDiagnosticRow(
                key=key,
                label=accumulator.label,
                sample_size=sample_size,
                mean_predicted_probability=round(mean_predicted_probability, 6),
                observed_rate=round(observed_rate, 6),
                mean_brier_score=round(mean_brier_score, 6),
                calibration_gap=round(calibration_gap, 6),
                confidence=confidence_band(
                    sample_size=sample_size,
                    min_sample_size=min_sample_size,
                ),
                eligible=sample_size >= min_sample_size,
                advisory_note=advisory_note(
                    sample_size=sample_size,
                    min_sample_size=min_sample_size,
                    drift_state=drift_state,
                    advisory_delta=advisory_delta,
                ),
                recent_sample_size=recent_sample_size,
                baseline_sample_size=baseline_sample_size,
                recent_observed_rate=_rounded_optional(recent_observed_rate),
                baseline_observed_rate=_rounded_optional(baseline_observed_rate),
                drift_state=drift_state,
                configured_effective_credibility=_rounded_optional(
                    configured_effective_credibility
                ),
                advisory_delta=_rounded_optional(advisory_delta),
                advisory_effective_credibility=_rounded_optional(advisory_effective_credibility),
            )
        )

    rows.sort(
        key=lambda row: (
            row.sample_size,
            abs(row.advisory_delta or 0.0),
            row.calibration_gap,
        ),
        reverse=True,
    )
    return rows


def _time_varying_signal(
    *,
    min_sample_size: int,
    recent_min_sample_size: int,
    recent_sample_size: int,
    baseline_sample_size: int,
    recent_observed_rate: float | None,
    baseline_observed_rate: float | None,
) -> tuple[str, float | None]:
    if recent_sample_size < recent_min_sample_size:
        return "insufficient_recent_data", None
    if baseline_sample_size < min_sample_size:
        return "no_baseline_window", None
    if recent_observed_rate is None or baseline_observed_rate is None:
        return "insufficient_recent_data", None

    drift = recent_observed_rate - baseline_observed_rate
    if abs(drift) < STABLE_DRIFT_THRESHOLD:
        return "stable", 0.0

    advisory_delta = max(
        -MAX_ADVISORY_DELTA,
        min(MAX_ADVISORY_DELTA, drift * ADVISORY_BLEND_FACTOR),
    )
    if advisory_delta > 0:
        return "improving", advisory_delta
    return "degrading", advisory_delta


def _advisory_effective_credibility(
    *,
    configured_effective_credibility: float | None,
    advisory_delta: float | None,
) -> float | None:
    if configured_effective_credibility is None or advisory_delta is None:
        return None
    return max(0.0, min(1.0, configured_effective_credibility + advisory_delta))


def _normalize_geography(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return parts[-1] if parts else text


def _normalize_topics(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    topics: list[str] = []
    for raw_topic in value:
        topic = str(raw_topic).strip()
        if topic:
            topics.append(topic)
    return topics


def _safe_average(total: float, count: int) -> float | None:
    if count <= 0:
        return None
    return total / count


def _rounded_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
