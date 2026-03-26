"""Shared helpers for report-facing trend statistics."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.trend_state_presentation import (
    build_momentum_state,
    build_uncertainty_state,
    load_evidence_window_stats,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.trend_engine import TrendEngine
    from src.storage.models import Trend


async def build_report_uncertainty_state(
    session: AsyncSession,
    *,
    trend: Trend,
    probability: float,
    now: datetime | None = None,
) -> dict[str, float | int | str]:
    """Build uncertainty payload for weekly/monthly report statistics."""
    trend_id = trend.id
    if trend_id is None:
        msg = "Trend id is required to build uncertainty state"
        raise ValueError(msg)
    evidence_stats = await load_evidence_window_stats(
        session,
        trend_id=trend_id,
        state_version_id=getattr(trend, "active_state_version_id", None),
        now=now,
    )
    return build_uncertainty_state(
        probability=probability,
        evidence_stats=evidence_stats,
    ).to_dict()


async def build_report_momentum_state(
    session: AsyncSession,
    *,
    trend: Trend,
    trend_engine: TrendEngine,
    now: datetime | None = None,
) -> dict[str, float | int | str | None]:
    """Build momentum payload for weekly/monthly report statistics."""
    momentum = await build_momentum_state(
        session,
        trend_engine=trend_engine,
        trend=trend,
        state_version_id=getattr(trend, "active_state_version_id", None),
        now=now,
    )
    return momentum.to_dict()


async def calculate_previous_period_change(
    *,
    trend_id: UUID,
    trend_engine: TrendEngine,
    period_start: datetime,
    period_end: datetime,
) -> float | None:
    """Compare the immediately preceding report window using snapshot history."""
    period_length = period_end - period_start
    previous_period_end = period_start
    previous_period_start = previous_period_end - period_length

    previous_end_probability = await trend_engine.get_probability_at(
        trend_id=trend_id,
        at=previous_period_end,
    )
    previous_start_probability = await trend_engine.get_probability_at(
        trend_id=trend_id,
        at=previous_period_start,
    )
    if previous_end_probability is None or previous_start_probability is None:
        return None
    return round(previous_end_probability - previous_start_probability, 6)


__all__ = [
    "build_report_momentum_state",
    "build_report_uncertainty_state",
    "calculate_previous_period_change",
]
