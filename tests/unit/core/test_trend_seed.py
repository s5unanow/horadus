from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.core.trend_seed as trend_seed
from src.core.trend_engine import prob_to_logodds
from src.storage.trend_state_models import TrendDefinitionVersion

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
        definition_version=None,
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


@pytest.mark.asyncio
async def test_sync_seeded_trend_rebases_material_yaml_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(flush=AsyncMock())
    original_state_id = uuid4()
    trend = MagicMock(
        id=uuid4(),
        active_state_version_id=original_state_id,
        definition={"id": "example", "name": "Example", "baseline_probability": 0.1},
        baseline_log_odds=-2.197225,
        current_log_odds=-1.5,
        indicators={},
        decay_half_life_days=30,
    )
    activate = AsyncMock()
    monkeypatch.setattr(trend_seed, "activate_trend_state", activate)
    changed_definition = {
        "id": "example",
        "name": "Example",
        "baseline_probability": 0.2,
        "decay_half_life_days": 45,
        "indicators": {"signal": {"weight": 0.04, "direction": "escalatory"}},
    }

    await trend_seed.sync_seeded_trend(session, trend, changed_definition, "example.yaml")

    activate.assert_awaited_once_with(
        session=session,
        trend=trend,
        activation_kind="rebase",
        actor="system",
        context="seed_trends:example.yaml",
        details={"source_file": "example.yaml"},
        definition_version=activate.call_args.kwargs["definition_version"],
    )
    assert isinstance(activate.call_args.kwargs["definition_version"], TrendDefinitionVersion)
    assert activate.call_args.kwargs["definition_version"].definition == changed_definition
    assert trend.current_log_odds == -1.5
    assert trend.definition == changed_definition


@pytest.mark.asyncio
async def test_sync_seeded_trend_skips_unchanged_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(flush=AsyncMock())
    definition = {
        "id": "example",
        "name": "Example",
        "baseline_probability": 0.1,
        "decay_half_life_days": 30,
        "indicators": {},
    }
    trend = MagicMock(
        active_state_version_id=uuid4(),
        definition=definition,
        baseline_log_odds=round(prob_to_logodds(0.1), 6),
        indicators={},
        decay_half_life_days=30,
    )
    activate = AsyncMock()
    monkeypatch.setattr(trend_seed, "activate_trend_state", activate)

    await trend_seed.sync_seeded_trend(session, trend, definition, "example.yaml")

    session.flush.assert_not_awaited()
    activate.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_seed_definition_version_requires_persisted_trend() -> None:
    session = MagicMock(flush=AsyncMock())
    trend = MagicMock(id=None)

    with pytest.raises(ValueError, match="Trend id is required"):
        await trend_seed._create_seed_definition_version(session, trend, "example.yaml")

    session.add.assert_not_called()
    session.flush.assert_not_awaited()
