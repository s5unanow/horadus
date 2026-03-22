from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

import src.api.routes._trend_write_mutations as trend_write_mutations_module
import src.api.routes.trends as trends_module
from src.core.trend_engine import prob_to_logodds
from src.storage.models import Trend, TrendDefinitionVersion

pytestmark = pytest.mark.unit


def _build_trend(*, trend_id=None, definition: dict | None = None) -> Trend:
    now = datetime.now(tz=UTC)
    return Trend(
        id=trend_id,
        name="Trend A",
        description="description",
        runtime_trend_id="trend-a",
        definition=definition
        or {"id": "trend-a", "forecast_contract": {"question": "Will it happen?"}},
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04}},
        decay_half_life_days=30,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_record_definition_version_assigns_missing_trend_id_when_forced(
    mock_db_session,
) -> None:
    trend = _build_trend(trend_id=None)

    changed = await trend_write_mutations_module.record_definition_version_if_material_change(
        mock_db_session,
        trend=trend,
        previous_definition=None,
        actor="api",
        context="create_trend",
        force=True,
    )

    assert changed is True
    assert trend.id is not None
    added_record = mock_db_session.add.call_args.args[0]
    assert isinstance(added_record, TrendDefinitionVersion)
    assert added_record.trend_id == trend.id


@pytest.mark.asyncio
async def test_record_definition_version_requires_previous_definition_when_not_forced(
    mock_db_session,
) -> None:
    with pytest.raises(ValueError, match="previous_definition is required"):
        await trend_write_mutations_module.record_definition_version_if_material_change(
            mock_db_session,
            trend=_build_trend(trend_id=uuid4()),
            previous_definition=None,
            actor="api",
            context="update_trend",
        )


@pytest.mark.asyncio
async def test_record_definition_version_skips_unchanged_definition(mock_db_session) -> None:
    definition = {"id": "trend-a", "forecast_contract": {"question": "Will it happen?"}}
    trend = _build_trend(trend_id=uuid4(), definition=definition)

    changed = await trend_write_mutations_module.record_definition_version_if_material_change(
        mock_db_session,
        trend=trend,
        previous_definition=definition,
        actor="api",
        context="update_trend",
    )

    assert changed is False
    mock_db_session.add.assert_not_called()


def test_requires_state_activation_helpers_cover_true_and_false_paths() -> None:
    assert trend_write_mutations_module.requires_state_activation({"name": "rename"}) is False
    assert trend_write_mutations_module.requires_state_activation({"definition": {"id": "trend-a"}})
    assert trends_module._requires_state_activation({"description": "only metadata"}) is False
    assert trends_module._requires_state_activation({"indicators": {"signal": {}}})


@pytest.mark.asyncio
async def test_update_trend_mutation_rejects_direct_probability_override(
    mock_db_session,
) -> None:
    trend = _build_trend(trend_id=uuid4())

    with pytest.raises(HTTPException, match="use POST /api/v1/trends/\\{id\\}/override") as exc:
        await trend_write_mutations_module.update_trend_mutation(
            session=mock_db_session,
            trend_id=trend.id,
            trend=trend,
            payload=trends_module.TrendUpdate(current_probability=0.35),
        )

    assert exc.value.status_code == 409
    assert float(trend.current_log_odds) == pytest.approx(prob_to_logodds(0.2), rel=0.001)
    mock_db_session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_trend_mutation_ignores_noop_probability_fields(
    mock_db_session,
) -> None:
    trend = _build_trend(trend_id=uuid4())
    mock_db_session.scalar.return_value = None

    result = await trend_write_mutations_module.update_trend_mutation(
        session=mock_db_session,
        trend_id=trend.id,
        trend=trend,
        payload=trends_module.TrendUpdate(
            description="updated",
            current_probability=0.2,
        ),
    )

    assert trend.description == "updated"
    assert float(trend.current_log_odds) == pytest.approx(prob_to_logodds(0.2), rel=0.001)
    assert result.trend is trend


@pytest.mark.asyncio
async def test_update_trend_mutation_ignores_null_probability_fields(
    mock_db_session,
) -> None:
    trend = _build_trend(trend_id=uuid4())
    mock_db_session.scalar.return_value = None

    result = await trend_write_mutations_module.update_trend_mutation(
        session=mock_db_session,
        trend_id=trend.id,
        trend=trend,
        payload=trends_module.TrendUpdate(
            description="updated",
            current_probability=None,
        ),
    )

    assert trend.description == "updated"
    assert float(trend.current_log_odds) == pytest.approx(prob_to_logodds(0.2), rel=0.001)
    assert result.trend is trend


@pytest.mark.asyncio
async def test_update_trend_mutation_rejects_noop_probability_field_on_replay_activation(
    mock_db_session,
) -> None:
    trend = _build_trend(trend_id=uuid4())

    with pytest.raises(HTTPException, match="use POST /api/v1/trends/\\{id\\}/override") as exc:
        await trend_write_mutations_module.update_trend_mutation(
            session=mock_db_session,
            trend_id=trend.id,
            trend=trend,
            payload=trends_module.TrendUpdate(
                baseline_probability=0.25,
                current_probability=0.2,
                activation_mode="replay",
            ),
        )

    assert exc.value.status_code == 409
