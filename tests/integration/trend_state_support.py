"""Shared integration setup for trends that can accept evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.trend_state import activate_trend_state

if TYPE_CHECKING:
    from src.storage.models import Trend


async def persist_trend_state(session: Any, trend: Trend, *related: object) -> None:
    """Persist a trend and related rows with an initial active state."""
    session.add_all([trend, *related])
    await session.flush()
    await activate_trend_state(
        session=session,
        trend=trend,
        activation_kind="create",
        actor="integration-test",
        context="integration-test",
    )
