"""
Calibration helpers and services for trend outcome tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.trend_engine import logodds_to_prob
from src.storage.models import OutcomeType, RiskLevel, Trend, TrendOutcome, TrendSnapshot


@dataclass
class CalibrationBucket:
    """Calibration statistics for one probability bucket."""

    bucket_start: float
    bucket_end: float
    prediction_count: int
    occurred_count: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


@dataclass
class CalibrationReport:
    """Overall calibration report."""

    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float | None
    buckets: list[CalibrationBucket]
    overconfident: bool
    underconfident: bool


def normalize_utc(value: datetime) -> datetime:
    """Normalize datetime values to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def get_risk_level(probability: float) -> RiskLevel:
    """Map probability to risk level bands."""
    if probability < 0.10:
        return RiskLevel.LOW
    if probability < 0.25:
        return RiskLevel.GUARDED
    if probability < 0.50:
        return RiskLevel.ELEVATED
    if probability < 0.75:
        return RiskLevel.HIGH
    return RiskLevel.SEVERE


def get_probability_band(probability: float, *, half_width: float = 0.10) -> tuple[float, float]:
    """Build a simple symmetric probability band around a point estimate."""
    low = max(0.001, probability - half_width)
    high = min(0.999, probability + half_width)
    return low, high


def _actual_value(outcome: OutcomeType) -> float | None:
    if outcome == OutcomeType.OCCURRED:
        return 1.0
    if outcome == OutcomeType.DID_NOT_OCCUR:
        return 0.0
    if outcome == OutcomeType.PARTIAL:
        return 0.5
    return None


def calculate_brier_score(
    predicted_probability: float,
    outcome: OutcomeType,
) -> float | None:
    """
    Calculate Brier score for an outcome.

    Brier = (prediction - actual)^2 where actual is in [0, 1].
    """
    actual = _actual_value(outcome)
    if actual is None:
        return None
    return (predicted_probability - actual) ** 2


def build_calibration_buckets(
    outcomes: list[TrendOutcome],
    *,
    bucket_count: int = 10,
) -> list[CalibrationBucket]:
    """Group scored outcomes by probability range and compute calibration errors."""
    if bucket_count < 1:
        raise ValueError("bucket_count must be >= 1")

    bucket_width = 1.0 / bucket_count
    bucket_stats: list[dict[str, float]] = [
        {"count": 0.0, "occurred_count": 0.0, "actual_sum": 0.0} for _ in range(bucket_count)
    ]

    for outcome in outcomes:
        outcome_value = outcome.outcome
        if outcome_value is None:
            continue

        try:
            outcome_enum = OutcomeType(outcome_value)
        except ValueError:
            continue

        actual = _actual_value(outcome_enum)
        if actual is None:
            continue

        probability = min(max(float(outcome.predicted_probability), 0.0), 1.0)
        index = min(int(probability / bucket_width), bucket_count - 1)
        stats = bucket_stats[index]
        stats["count"] += 1
        if outcome_enum == OutcomeType.OCCURRED:
            stats["occurred_count"] += 1
        stats["actual_sum"] += actual

    buckets: list[CalibrationBucket] = []
    for index, stats in enumerate(bucket_stats):
        prediction_count = int(stats["count"])
        if prediction_count == 0:
            continue

        bucket_start = index * bucket_width
        bucket_end = bucket_start + bucket_width
        actual_rate = stats["actual_sum"] / prediction_count
        expected_rate = (bucket_start + bucket_end) / 2
        buckets.append(
            CalibrationBucket(
                bucket_start=bucket_start,
                bucket_end=bucket_end,
                prediction_count=prediction_count,
                occurred_count=int(stats["occurred_count"]),
                actual_rate=actual_rate,
                expected_rate=expected_rate,
                calibration_error=abs(actual_rate - expected_rate),
            )
        )

    return buckets


class CalibrationService:
    """Service for recording trend outcomes and computing calibration reports."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_outcome(
        self,
        *,
        trend_id: UUID,
        outcome: OutcomeType,
        outcome_date: datetime,
        notes: str | None = None,
        evidence: dict[str, object] | None = None,
        recorded_by: str | None = None,
    ) -> TrendOutcome:
        trend = await self.session.get(Trend, trend_id)
        if trend is None:
            raise ValueError(f"Trend '{trend_id}' not found")

        prediction_date = normalize_utc(outcome_date)
        predicted_probability = await self._get_predicted_probability(trend, prediction_date)
        probability_band_low, probability_band_high = get_probability_band(predicted_probability)
        brier_score = calculate_brier_score(predicted_probability, outcome)

        record = TrendOutcome(
            trend_id=trend_id,
            prediction_date=prediction_date,
            predicted_probability=predicted_probability,
            predicted_risk_level=get_risk_level(predicted_probability).value,
            probability_band_low=probability_band_low,
            probability_band_high=probability_band_high,
            outcome_date=prediction_date,
            outcome=outcome.value,
            outcome_notes=notes,
            outcome_evidence=evidence,
            brier_score=brier_score,
            recorded_by=recorded_by,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_calibration_report(
        self,
        *,
        trend_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> CalibrationReport:
        query = (
            select(TrendOutcome)
            .where(TrendOutcome.trend_id == trend_id)
            .order_by(TrendOutcome.prediction_date.asc())
        )
        if start_date is not None:
            query = query.where(TrendOutcome.prediction_date >= normalize_utc(start_date))
        if end_date is not None:
            query = query.where(TrendOutcome.prediction_date <= normalize_utc(end_date))

        outcomes = list((await self.session.scalars(query)).all())
        scored_outcomes: list[TrendOutcome] = []
        for outcome in outcomes:
            if outcome.outcome is None:
                continue
            try:
                outcome_enum = OutcomeType(outcome.outcome)
            except ValueError:
                continue
            if _actual_value(outcome_enum) is not None:
                scored_outcomes.append(outcome)

        buckets = build_calibration_buckets(scored_outcomes)
        brier_values = []
        for outcome in scored_outcomes:
            if outcome.brier_score is not None:
                brier_values.append(float(outcome.brier_score))
                continue
            if outcome.outcome is None:
                continue
            outcome_enum = OutcomeType(outcome.outcome)
            computed = calculate_brier_score(float(outcome.predicted_probability), outcome_enum)
            if computed is not None:
                brier_values.append(computed)

        mean_brier_score = sum(brier_values) / len(brier_values) if brier_values else None
        signed_error = 0.0
        for outcome in scored_outcomes:
            if outcome.outcome is None:
                continue
            actual = _actual_value(OutcomeType(outcome.outcome))
            if actual is None:
                continue
            signed_error += actual - float(outcome.predicted_probability)

        mean_signed_error = signed_error / len(scored_outcomes) if scored_outcomes else 0.0
        return CalibrationReport(
            total_predictions=len(outcomes),
            resolved_predictions=len(scored_outcomes),
            mean_brier_score=mean_brier_score,
            buckets=buckets,
            overconfident=mean_signed_error < -0.05,
            underconfident=mean_signed_error > 0.05,
        )

    async def _get_predicted_probability(self, trend: Trend, prediction_date: datetime) -> float:
        snapshot = await self.session.scalar(
            select(TrendSnapshot)
            .where(TrendSnapshot.trend_id == trend.id)
            .where(TrendSnapshot.timestamp <= prediction_date)
            .order_by(TrendSnapshot.timestamp.desc())
            .limit(1)
        )
        if snapshot is None:
            return logodds_to_prob(float(trend.current_log_odds))
        return logodds_to_prob(float(snapshot.log_odds))
