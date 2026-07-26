from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.trend_engine import TrendEngine, prob_to_logodds
from src.storage.models import Trend, to_decimal

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_trend():
    trend = MagicMock(spec=Trend)
    trend.id = uuid4()
    trend.name = "Test Trend"
    trend.definition = {"baseline_probability": 0.1}
    trend.current_log_odds = prob_to_logodds(0.1)
    trend.baseline_log_odds = prob_to_logodds(0.1)
    trend.updated_at = datetime.now(UTC)
    trend.active_state_version_id = uuid4()
    trend.active_definition_hash = None
    trend.active_scoring_math_version = None
    trend.active_scoring_parameter_set = None
    return trend


def test_to_decimal_preserves_decimal_inputs() -> None:
    value = Decimal("0.125")
    assert to_decimal(value) is value


@pytest.mark.asyncio
async def test_apply_decay_uses_decimal_update_params(mock_session, mock_trend) -> None:
    engine = TrendEngine(mock_session)
    mock_trend.active_state_version_id = uuid4()
    row = MagicMock(
        _mapping={
            "current_log_odds": 0.0,
            "baseline_log_odds": prob_to_logodds(0.2),
            "last_decayed_at": datetime.now(UTC),
            "decay_half_life_days": 30,
        }
    )
    execute_result = MagicMock()
    execute_result.one_or_none.return_value = row
    mock_session.execute = AsyncMock(side_effect=[execute_result, MagicMock(), MagicMock()])

    await engine.apply_decay(mock_trend, as_of=datetime.now(UTC))

    trend_update_stmt = mock_session.execute.await_args_list[1].args[0]
    state_update_stmt = mock_session.execute.await_args_list[2].args[0]
    assert isinstance(trend_update_stmt.compile().params["current_log_odds"], Decimal)
    assert isinstance(state_update_stmt.compile().params["current_log_odds"], Decimal)
