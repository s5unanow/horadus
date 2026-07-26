"""Serialized decay-before-delta mutation for live trend state."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.decimal_utils import Decimal
from src.storage.models import Trend
from src.storage.trend_state_models import TrendStateVersion

logger = structlog.get_logger(__name__)

DEFAULT_DECAY_HALF_LIFE_DAYS = 30


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def resolve_trend_decay_clock(trend: Trend) -> datetime:
    """Return the persisted decay clock with legacy-object fallback."""
    value = getattr(trend, "last_decayed_at", None)
    return _as_utc(value if isinstance(value, datetime) else trend.updated_at)


async def apply_locked_trend_delta(
    *,
    session: AsyncSession,
    trend_id: UUID,
    delta: float,
    reason: str,
    requested_at: datetime,
    active_state_version_id: UUID | None,
    trend_name: str | None,
    fallback_current_log_odds: float | None,
) -> tuple[float, float, datetime]:
    """Lock one trend, advance accrued decay, then apply its signed delta."""
    delta_value = Decimal(str(delta))
    locked_result = await session.execute(
        select(
            Trend.current_log_odds.label("current_log_odds"),
            Trend.baseline_log_odds.label("baseline_log_odds"),
            Trend.last_decayed_at.label("last_decayed_at"),
            Trend.decay_half_life_days.label("decay_half_life_days"),
        )
        .where(Trend.id == trend_id)
        .with_for_update()
    )
    raw_locked_row: Any = locked_result.one_or_none()
    if isawaitable(raw_locked_row):
        raw_locked_row = await raw_locked_row
    row_mapping = getattr(raw_locked_row, "_mapping", None)
    typed_mapping = row_mapping if isinstance(row_mapping, Mapping) else None
    if typed_mapping is None:
        if fallback_current_log_odds is None:
            raise ValueError(f"Trend '{trend_id}' not found for atomic log-odds update")
        previous_lo = float(fallback_current_log_odds)
        new_lo = previous_lo + float(delta_value)
        logger.warning(
            "Trend delta update returned no locked row; using in-memory fallback",
            trend_id=str(trend_id),
            trend_name=trend_name,
            delta=float(delta_value),
            reason=reason,
            update_strategy="fallback_in_memory",
        )
        return previous_lo, new_lo, requested_at

    current_lo = float(typed_mapping["current_log_odds"])
    baseline_lo = float(typed_mapping["baseline_log_odds"])
    last_decayed_at = _as_utc(typed_mapping["last_decayed_at"])
    applied_at = max(requested_at, last_decayed_at)
    half_life = typed_mapping["decay_half_life_days"] or DEFAULT_DECAY_HALF_LIFE_DAYS
    days_elapsed = (applied_at - last_decayed_at).total_seconds() / 86400.0
    decay_factor = math.pow(0.5, days_elapsed / half_life)
    previous_lo = baseline_lo + ((current_lo - baseline_lo) * decay_factor)
    new_lo = previous_lo + float(delta_value)
    result = await session.execute(
        update(Trend)
        .where(Trend.id == trend_id)
        .values(
            current_log_odds=Decimal(str(new_lo)),
            updated_at=applied_at,
            last_decayed_at=applied_at,
        )
        .returning(Trend.current_log_odds)
        .execution_options(synchronize_session=False)
    )
    raw_new_log_odds = result.scalar_one_or_none()
    if isawaitable(raw_new_log_odds):
        raw_new_log_odds = await raw_new_log_odds
    if not isinstance(raw_new_log_odds, int | float | Decimal):
        raise RuntimeError(f"Trend '{trend_id}' disappeared during locked delta update")
    new_lo = float(raw_new_log_odds)
    if isinstance(active_state_version_id, UUID):
        await session.execute(
            update(TrendStateVersion)
            .where(TrendStateVersion.id == active_state_version_id)
            .values(current_log_odds=Decimal(str(new_lo)))
            .execution_options(synchronize_session=False)
        )
    logger.debug(
        "Applied serialized trend decay and log-odds delta",
        trend_id=str(trend_id),
        trend_name=trend_name,
        delta=float(delta_value),
        reason=reason,
        update_strategy="row_lock_decay_then_delta",
        days_elapsed=days_elapsed,
        previous_log_odds=previous_lo,
        new_log_odds=new_lo,
    )
    return previous_lo, new_lo, applied_at
