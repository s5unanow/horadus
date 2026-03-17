"""Helpers for append-only trend restatements and deterministic projection checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import pow
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.trend_engine import DEFAULT_DECAY_HALF_LIFE_DAYS, TrendEngine
from src.storage.models import Trend, TrendEvidence
from src.storage.restatement_models import TrendRestatement

HISTORICAL_ARTIFACT_POLICY = "belief_at_time"
PROJECTION_DRIFT_TOLERANCE = 1e-6


@dataclass(frozen=True)
class TrendProjectionEntry:
    """One signed state change used for deterministic trend reconstruction."""

    recorded_at: datetime
    delta_log_odds: float
    entry_type: str
    source_id: UUID | None


@dataclass(frozen=True)
class TrendProjectionCheck:
    """Stored-versus-recomputed projection summary for one trend."""

    as_of: datetime
    stored_log_odds: float
    projected_log_odds: float
    drift_log_odds: float
    evidence_count: int
    restatement_count: int
    entry_count: int

    @property
    def matches_projection(self) -> bool:
        return abs(self.drift_log_odds) <= PROJECTION_DRIFT_TOLERANCE


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decay_log_odds(
    *,
    current_log_odds: float,
    baseline_log_odds: float,
    half_life_days: float,
    from_at: datetime,
    to_at: datetime,
) -> float:
    elapsed_days = (_as_utc(to_at) - _as_utc(from_at)).total_seconds() / 86400.0
    if elapsed_days <= 0:
        return current_log_odds
    decay_factor = pow(0.5, elapsed_days / max(0.1, half_life_days))
    return baseline_log_odds + ((current_log_odds - baseline_log_odds) * decay_factor)


async def apply_compensating_restatement(
    *,
    trend_engine: TrendEngine,
    trend: Trend,
    compensation_delta_log_odds: float,
    restatement_kind: str,
    source: str,
    recorded_at: datetime | None = None,
    event_id: UUID | None = None,
    event_claim_id: UUID | None = None,
    trend_evidence: TrendEvidence | None = None,
    feedback_id: UUID | None = None,
    original_evidence_delta_log_odds: float | None = None,
    notes: str | None = None,
    details: dict[str, Any] | None = None,
) -> TrendRestatement:
    """Persist one restatement row and apply its signed delta atomically."""

    if trend.id is None:
        raise ValueError("Trend must have an id before recording a restatement")

    session = getattr(trend_engine, "session", None)
    applied_at = _as_utc(recorded_at) if recorded_at is not None else datetime.now(tz=UTC)
    evidence_id = trend_evidence.id if trend_evidence is not None else None
    restatement = TrendRestatement(
        trend_id=trend.id,
        event_id=event_id if event_id is not None else getattr(trend_evidence, "event_id", None),
        event_claim_id=(
            event_claim_id
            if event_claim_id is not None
            else getattr(trend_evidence, "event_claim_id", None)
        ),
        trend_evidence_id=evidence_id,
        feedback_id=feedback_id,
        restatement_kind=restatement_kind,
        source=source,
        original_evidence_delta_log_odds=original_evidence_delta_log_odds,
        compensation_delta_log_odds=compensation_delta_log_odds,
        notes=notes,
        details=details if isinstance(details, dict) else None,
        recorded_at=applied_at,
    )
    if session is not None:
        session.add(restatement)
        await session.flush()

    if abs(compensation_delta_log_odds) > 0.0:
        previous_lo, new_lo = await trend_engine.apply_log_odds_delta(
            trend_id=trend.id,
            trend_name=trend.name,
            delta=compensation_delta_log_odds,
            reason=f"restatement:{restatement_kind}",
            updated_at=applied_at,
            fallback_current_log_odds=float(trend.current_log_odds),
        )
        if previous_lo != new_lo:
            trend.current_log_odds = new_lo
            trend.updated_at = applied_at

    return restatement


async def build_trend_projection_check(
    *,
    session: AsyncSession,
    trend: Trend,
    as_of: datetime | None = None,
) -> TrendProjectionCheck:
    """Recompute one trend from baseline plus chronological evidence/restatements."""

    if trend.id is None:
        raise ValueError("Trend must have an id before projection verification")

    evidence_rows = list(
        (
            await session.scalars(
                select(TrendEvidence)
                .where(TrendEvidence.trend_id == trend.id)
                .order_by(TrendEvidence.created_at.asc(), TrendEvidence.id.asc())
            )
        ).all()
    )
    restatement_rows = list(
        (
            await session.scalars(
                select(TrendRestatement)
                .where(TrendRestatement.trend_id == trend.id)
                .order_by(TrendRestatement.recorded_at.asc(), TrendRestatement.id.asc())
            )
        ).all()
    )

    entries = [
        TrendProjectionEntry(
            recorded_at=_as_utc(row.created_at),
            delta_log_odds=float(row.delta_log_odds),
            entry_type="evidence",
            source_id=row.id,
        )
        for row in evidence_rows
    ]
    entries.extend(
        TrendProjectionEntry(
            recorded_at=_as_utc(row.recorded_at),
            delta_log_odds=float(row.compensation_delta_log_odds),
            entry_type=row.restatement_kind,
            source_id=row.id,
        )
        for row in restatement_rows
    )
    entries.sort(key=lambda entry: (entry.recorded_at, entry.entry_type, str(entry.source_id)))

    baseline_log_odds = float(trend.baseline_log_odds)
    current_log_odds = baseline_log_odds
    half_life_days = float(trend.decay_half_life_days or DEFAULT_DECAY_HALF_LIFE_DAYS)
    last_at = _as_utc(trend.created_at)
    projected_at = _as_utc(as_of if as_of is not None else trend.updated_at)

    for entry in entries:
        current_log_odds = _decay_log_odds(
            current_log_odds=current_log_odds,
            baseline_log_odds=baseline_log_odds,
            half_life_days=half_life_days,
            from_at=last_at,
            to_at=entry.recorded_at,
        )
        current_log_odds += entry.delta_log_odds
        last_at = entry.recorded_at

    projected_log_odds = _decay_log_odds(
        current_log_odds=current_log_odds,
        baseline_log_odds=baseline_log_odds,
        half_life_days=half_life_days,
        from_at=last_at,
        to_at=projected_at,
    )
    stored_log_odds = float(trend.current_log_odds)
    return TrendProjectionCheck(
        as_of=projected_at,
        stored_log_odds=stored_log_odds,
        projected_log_odds=projected_log_odds,
        drift_log_odds=stored_log_odds - projected_log_odds,
        evidence_count=len(evidence_rows),
        restatement_count=len(restatement_rows),
        entry_count=len(entries),
    )
