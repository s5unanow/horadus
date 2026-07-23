from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.core.trend_seed as trend_seed

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_ensure_seeded_trend_state_activates_missing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(flush=AsyncMock())
    trend = MagicMock(active_state_version_id=None)
    activate = AsyncMock()
    monkeypatch.setattr(trend_seed, "activate_trend_state", activate)

    await trend_seed.ensure_seeded_trend_state(session, trend, "example.yaml")

    session.flush.assert_awaited_once_with()
    activate.assert_awaited_once_with(
        session=session,
        trend=trend,
        activation_kind="create",
        actor="system",
        context="seed_trends:example.yaml",
        details={"source_file": "example.yaml"},
    )


@pytest.mark.asyncio
async def test_ensure_seeded_trend_state_preserves_existing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(flush=AsyncMock())
    trend = MagicMock(active_state_version_id=uuid4())
    activate = AsyncMock()
    monkeypatch.setattr(trend_seed, "activate_trend_state", activate)

    await trend_seed.ensure_seeded_trend_state(session, trend, "example.yaml")

    session.flush.assert_not_awaited()
    activate.assert_not_awaited()
