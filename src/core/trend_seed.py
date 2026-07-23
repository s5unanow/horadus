"""State-version activation helpers for the standalone trend seeder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.trend_state import activate_trend_state

if TYPE_CHECKING:
    from src.storage.models import Trend


async def ensure_seeded_trend_state(session: Any, trend: Trend, source_file: str) -> None:
    """Create the initial state version when a seeded trend lacks one."""
    if trend.active_state_version_id is not None:
        return
    await session.flush()
    await activate_trend_state(
        session=session,
        trend=trend,
        activation_kind="create",
        actor="system",
        context=f"seed_trends:{source_file}",
        details={"source_file": source_file},
    )


async def persist_seeded_trend(session: Any, trend: Trend, source_file: str) -> None:
    """Add a new seeded trend and activate its initial state."""
    session.add(trend)
    await ensure_seeded_trend_state(session, trend, source_file)
