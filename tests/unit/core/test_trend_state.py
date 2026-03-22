from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.core.trend_state as trend_state_module
from src.core.runtime_provenance import current_trend_scoring_contract
from src.core.trend_engine import prob_to_logodds
from src.core.trend_state import (
    activate_trend_state,
    ensure_definition_version,
    hash_definition_payload,
)
from src.storage.models import Trend
from src.storage.trend_state_models import TrendDefinitionVersion

pytestmark = pytest.mark.unit


def _build_trend(*, trend_id=None) -> Trend:
    now = datetime(2026, 3, 22, tzinfo=UTC)
    return Trend(
        id=trend_id or uuid4(),
        name="Versioned Trend",
        description="description",
        runtime_trend_id="versioned-trend",
        definition={"id": "versioned-trend", "forecast_contract": {"question": "q"}},
        baseline_log_odds=prob_to_logodds(0.2),
        current_log_odds=prob_to_logodds(0.35),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04}},
        decay_half_life_days=30,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_ensure_definition_version_prefers_active_definition_version(mock_db_session) -> None:
    trend = _build_trend()
    existing = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="a" * 64,
        definition={"id": "versioned-trend"},
    )
    trend.active_definition_version_id = existing.id
    mock_db_session.get.return_value = existing

    result = await ensure_definition_version(
        session=mock_db_session,
        trend=trend,
        actor="api",
        context="update",
    )

    assert result is existing
    mock_db_session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_definition_version_falls_back_when_active_id_row_missing(
    mock_db_session,
) -> None:
    trend = _build_trend()
    trend.active_definition_version_id = uuid4()
    existing = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="fallback" * 8,
        definition={"id": "versioned-trend"},
    )
    mock_db_session.get.return_value = None
    mock_db_session.scalar.return_value = existing

    result = await ensure_definition_version(
        session=mock_db_session,
        trend=trend,
        actor="api",
        context="update",
    )

    assert result is existing
    mock_db_session.get.assert_awaited_once()
    mock_db_session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_definition_version_reuses_latest_recorded_version(mock_db_session) -> None:
    trend = _build_trend()
    existing = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="b" * 64,
        definition={"id": "versioned-trend"},
    )
    mock_db_session.scalar.return_value = existing

    result = await ensure_definition_version(
        session=mock_db_session,
        trend=trend,
        actor="api",
        context="update",
    )

    assert result is existing
    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_definition_version_requires_trend_id_before_create(mock_db_session) -> None:
    trend = _build_trend(trend_id=None)
    trend.id = None
    mock_db_session.scalar.return_value = None

    with pytest.raises(ValueError, match="Trend id is required"):
        await ensure_definition_version(
            session=mock_db_session,
            trend=trend,
            actor="api",
            context="update",
        )


@pytest.mark.asyncio
async def test_ensure_definition_version_creates_new_row(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.scalar.return_value = None

    result = await ensure_definition_version(
        session=mock_db_session,
        trend=trend,
        actor="api",
        context="update",
    )

    assert result.trend_id == trend.id
    assert result.definition_hash == hash_definition_payload(trend.definition)
    assert result.actor == "api"
    assert result.context == "update"
    mock_db_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_trend_state_requires_trend_id(mock_db_session) -> None:
    trend = _build_trend(trend_id=None)
    trend.id = None

    with pytest.raises(ValueError, match="Trend id is required"):
        await activate_trend_state(
            session=mock_db_session,
            trend=trend,
            activation_kind="rebase",
            actor="api",
            context="update",
        )


@pytest.mark.asyncio
async def test_activate_trend_state_rebase_uses_current_log_odds(mock_db_session) -> None:
    trend = _build_trend()
    previous_state_version_id = uuid4()
    trend.active_state_version_id = previous_state_version_id
    definition_version = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="c" * 64,
        definition={"id": "versioned-trend"},
    )
    activated_at = datetime(2026, 3, 22, 9, 0, tzinfo=UTC)

    state_version = await activate_trend_state(
        session=mock_db_session,
        trend=trend,
        activation_kind="rebase",
        actor="api",
        context="update",
        definition_version=definition_version,
        activated_at=activated_at,
        details={"note": "carry-forward"},
    )

    contract = current_trend_scoring_contract()
    assert state_version.parent_state_version_id == previous_state_version_id
    assert state_version.starting_log_odds == pytest.approx(prob_to_logodds(0.35))
    assert state_version.current_log_odds == pytest.approx(prob_to_logodds(0.35))
    assert state_version.details == {"note": "carry-forward"}
    assert state_version.scoring_math_version == contract["math_version"]
    assert state_version.scoring_parameter_set == contract["parameter_set"]
    assert trend.active_definition_version_id == definition_version.id
    assert trend.active_state_version_id == state_version.id
    assert trend.current_log_odds == pytest.approx(prob_to_logodds(0.35))
    assert trend.updated_at == activated_at


@pytest.mark.asyncio
async def test_activate_trend_state_replay_resets_to_baseline(mock_db_session) -> None:
    trend = _build_trend()
    definition_version = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="d" * 64,
        definition={"id": "versioned-trend"},
    )

    state_version = await activate_trend_state(
        session=mock_db_session,
        trend=trend,
        activation_kind="replay",
        actor="api",
        context="update",
        definition_version=definition_version,
    )

    assert state_version.starting_log_odds == pytest.approx(prob_to_logodds(0.2))
    assert state_version.current_log_odds == pytest.approx(prob_to_logodds(0.2))
    assert state_version.details == {
        "isolation_strategy": "cutoff_freeze",
        "replay_required": True,
    }
    assert trend.current_log_odds == pytest.approx(prob_to_logodds(0.2))


@pytest.mark.asyncio
async def test_activate_trend_state_requests_definition_version_when_missing(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend = _build_trend()
    definition_version = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash="e" * 64,
        definition={"id": "versioned-trend"},
    )
    fake_ensure = AsyncMock(return_value=definition_version)
    monkeypatch.setattr(trend_state_module, "ensure_definition_version", fake_ensure)

    state_version = await activate_trend_state(
        session=mock_db_session,
        trend=trend,
        activation_kind="new_line",
        actor="system",
        context="config_sync",
    )

    fake_ensure.assert_awaited_once()
    assert state_version.starting_log_odds == pytest.approx(prob_to_logodds(0.2))
    assert state_version.details == {"isolation_strategy": "fresh_line"}
