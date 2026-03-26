"""Deterministic presentation-state helpers for trend uncertainty and momentum."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from src.core.risk import calculate_probability_band

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.trend_engine import TrendEngine
    from src.storage.models import Trend


class TrendUncertaintyLevel(StrEnum):
    """Bounded presentation labels for trend uncertainty."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True, frozen=True)
class EvidenceWindowStats:
    """Recent evidence summary used by uncertainty and momentum helpers."""

    evidence_count: int
    avg_corroboration: float
    days_since_last_evidence: int


@dataclass(slots=True, frozen=True)
class TrendUncertaintyState:
    """Explainable uncertainty state derived from recent evidence coverage."""

    score: float
    level: TrendUncertaintyLevel
    band_width: float
    evidence_count_30d: int
    avg_corroboration_30d: float
    days_since_last_evidence: int

    def to_dict(self) -> dict[str, float | int | str]:
        """Return a JSON-safe payload."""
        return {
            "score": round(self.score, 6),
            "level": self.level.value,
            "band_width": round(self.band_width, 6),
            "evidence_count_30d": self.evidence_count_30d,
            "avg_corroboration_30d": round(self.avg_corroboration_30d, 6),
            "days_since_last_evidence": self.days_since_last_evidence,
        }


@dataclass(slots=True, frozen=True)
class TrendMomentumState:
    """Recent directional movement tied to snapshot and evidence windows."""

    direction: str
    window_days: int
    delta_probability: float
    previous_window_delta: float | None
    acceleration: float | None
    evidence_count_window: int

    def to_dict(self) -> dict[str, float | int | str | None]:
        """Return a JSON-safe payload."""
        return {
            "direction": self.direction,
            "window_days": self.window_days,
            "delta_probability": round(self.delta_probability, 6),
            "previous_window_delta": (
                None if self.previous_window_delta is None else round(self.previous_window_delta, 6)
            ),
            "acceleration": None if self.acceleration is None else round(self.acceleration, 6),
            "evidence_count_window": self.evidence_count_window,
        }


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _momentum_direction(delta_probability: float) -> str:
    if delta_probability >= 0.05:
        return "rising_fast"
    if delta_probability >= 0.01:
        return "rising"
    if delta_probability <= -0.05:
        return "falling_fast"
    if delta_probability <= -0.01:
        return "falling"
    return "stable"


async def load_evidence_window_stats(
    session: AsyncSession,
    *,
    trend_id: UUID,
    state_version_id: UUID | None = None,
    lookback_days: int = 30,
    now: datetime | None = None,
) -> EvidenceWindowStats:
    """Load recent evidence coverage stats for a trend/state window."""
    from src.storage.models import TrendEvidence

    now_utc = _as_utc(now) if now is not None else datetime.now(tz=UTC)
    window_start = now_utc - timedelta(days=lookback_days)
    query = select(
        func.count(TrendEvidence.id),
        func.avg(TrendEvidence.corroboration_factor),
        func.max(TrendEvidence.created_at),
    ).where(
        TrendEvidence.trend_id == trend_id,
        TrendEvidence.created_at >= window_start,
        TrendEvidence.is_invalidated.is_(False),
    )
    if state_version_id is not None:
        query = query.where(TrendEvidence.state_version_id == state_version_id)
    row = (await session.execute(query)).one()
    evidence_count = int(row[0] or 0)
    avg_corroboration = float(row[1]) if row[1] is not None else 0.5
    most_recent = row[2]

    if most_recent is None:
        days_since_last_evidence = lookback_days
    else:
        most_recent_utc = _as_utc(most_recent)
        days_since_last_evidence = max(0, (now_utc - most_recent_utc).days)

    return EvidenceWindowStats(
        evidence_count=evidence_count,
        avg_corroboration=avg_corroboration,
        days_since_last_evidence=days_since_last_evidence,
    )


def build_uncertainty_state(
    *,
    probability: float,
    evidence_stats: EvidenceWindowStats,
) -> TrendUncertaintyState:
    """Build a bounded uncertainty payload from probability-band dispersion."""
    band_low, band_high = calculate_probability_band(
        probability=probability,
        evidence_count_30d=evidence_stats.evidence_count,
        avg_corroboration=evidence_stats.avg_corroboration,
        days_since_last_evidence=evidence_stats.days_since_last_evidence,
    )
    band_width = max(0.0, min(1.0, band_high - band_low))
    score = max(0.0, min(1.0, band_width / 0.6))
    if band_width < 0.10:
        level = TrendUncertaintyLevel.LOW
    elif band_width < 0.20:
        level = TrendUncertaintyLevel.MEDIUM
    else:
        level = TrendUncertaintyLevel.HIGH

    return TrendUncertaintyState(
        score=score,
        level=level,
        band_width=band_width,
        evidence_count_30d=evidence_stats.evidence_count,
        avg_corroboration_30d=evidence_stats.avg_corroboration,
        days_since_last_evidence=evidence_stats.days_since_last_evidence,
    )


async def build_momentum_state(
    session: AsyncSession,
    *,
    trend_engine: TrendEngine,
    trend: Trend,
    state_version_id: UUID | None = None,
    window_days: int = 7,
    now: datetime | None = None,
) -> TrendMomentumState:
    """Build recent momentum from the latest and prior snapshot windows."""
    from src.storage.models import TrendEvidence

    if trend.id is None:
        msg = "Trend id is required to build momentum state"
        raise ValueError(msg)

    now_utc = _as_utc(now) if now is not None else datetime.now(tz=UTC)
    current_probability = trend_engine.get_probability(trend)
    window_start = now_utc - timedelta(days=window_days)
    previous_window_start = now_utc - timedelta(days=window_days * 2)
    prior_probability = await trend_engine.get_probability_at(trend.id, window_start)
    previous_start_probability = await trend_engine.get_probability_at(
        trend.id, previous_window_start
    )

    if prior_probability is None:
        delta_probability = 0.0
        previous_window_delta = None
        acceleration = None
    else:
        delta_probability = current_probability - prior_probability
        if previous_start_probability is None:
            previous_window_delta = None
            acceleration = None
        else:
            previous_window_delta = prior_probability - previous_start_probability
            acceleration = delta_probability - previous_window_delta

    count_query = select(func.count(TrendEvidence.id)).where(
        TrendEvidence.trend_id == trend.id,
        TrendEvidence.created_at >= window_start,
        TrendEvidence.created_at <= now_utc,
        TrendEvidence.is_invalidated.is_(False),
    )
    if state_version_id is not None:
        count_query = count_query.where(TrendEvidence.state_version_id == state_version_id)
    evidence_count_window = int((await session.scalar(count_query)) or 0)

    return TrendMomentumState(
        direction=_momentum_direction(delta_probability),
        window_days=window_days,
        delta_probability=delta_probability,
        previous_window_delta=previous_window_delta,
        acceleration=acceleration,
        evidence_count_window=evidence_count_window,
    )


__all__ = [
    "EvidenceWindowStats",
    "TrendMomentumState",
    "TrendUncertaintyLevel",
    "TrendUncertaintyState",
    "build_momentum_state",
    "build_uncertainty_state",
    "load_evidence_window_stats",
]
