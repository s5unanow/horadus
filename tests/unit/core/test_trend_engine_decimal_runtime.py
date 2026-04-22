from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.trend_engine import EvidenceFactors, TrendEngine, prob_to_logodds
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
    trend.active_state_version_id = None
    trend.active_definition_hash = None
    trend.active_scoring_math_version = None
    trend.active_scoring_parameter_set = None
    return trend


@pytest.fixture
def sample_factors():
    return EvidenceFactors(
        base_weight=0.04,
        direction_multiplier=1.0,
        credibility=0.9,
        corroboration=1.0,
        novelty=1.0,
        evidence_age_days=0.0,
        temporal_decay_multiplier=1.0,
        severity=1.0,
        confidence=0.8,
        raw_delta=0.04,
        clamped_delta=0.04,
    )


def test_to_decimal_preserves_decimal_inputs() -> None:
    value = Decimal("0.125")
    assert to_decimal(value) is value


@pytest.mark.asyncio
async def test_apply_evidence_persists_decimal_runtime_values(
    mock_session, mock_trend, sample_factors
) -> None:
    engine = TrendEngine(mock_session)

    @asynccontextmanager
    async def _begin_nested():
        yield

    mock_session.begin_nested = MagicMock(side_effect=lambda: _begin_nested())
    precheck_result = MagicMock()
    precheck_result.scalar_one_or_none.return_value = None
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = 1.2
    mock_session.execute = AsyncMock(side_effect=[precheck_result, execute_result])

    await engine.apply_evidence(
        trend=mock_trend,
        delta=0.1,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="test",
        factors=sample_factors,
        reasoning="Test reasoning",
    )

    evidence_record = mock_session.add.call_args.args[0]
    assert isinstance(evidence_record.base_weight, Decimal)
    assert isinstance(evidence_record.delta_log_odds, Decimal)
    assert isinstance(mock_trend.current_log_odds, Decimal)


@pytest.mark.asyncio
async def test_apply_decay_uses_decimal_update_params(mock_session, mock_trend) -> None:
    engine = TrendEngine(mock_session)
    mock_trend.active_state_version_id = uuid4()
    row = MagicMock(
        _mapping={
            "current_log_odds": 0.0,
            "baseline_log_odds": prob_to_logodds(0.2),
            "updated_at": datetime.now(UTC),
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
