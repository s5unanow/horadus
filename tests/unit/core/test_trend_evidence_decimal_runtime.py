from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.trend_engine import EvidenceFactors, TrendEngine, prob_to_logodds
from src.storage.models import Trend

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_apply_evidence_persists_decimal_runtime_values() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    @asynccontextmanager
    async def _begin_nested():
        yield

    session.begin_nested = MagicMock(side_effect=lambda: _begin_nested())
    now = datetime.now(UTC)
    trend = MagicMock(spec=Trend)
    trend.id = uuid4()
    trend.name = "Test Trend"
    trend.definition = {"baseline_probability": 0.1}
    trend.current_log_odds = trend.baseline_log_odds = prob_to_logodds(0.1)
    trend.updated_at = trend.last_decayed_at = now
    trend.active_state_version_id = uuid4()
    trend.active_definition_hash = None
    trend.active_scoring_math_version = None
    trend.active_scoring_parameter_set = None
    precheck_result = MagicMock()
    precheck_result.scalar_one_or_none.return_value = None
    locked_result = MagicMock()
    locked_result.one_or_none.return_value = MagicMock(
        _mapping={
            "current_log_odds": trend.current_log_odds,
            "baseline_log_odds": trend.baseline_log_odds,
            "last_decayed_at": now,
            "decay_half_life_days": 30,
        }
    )
    update_result = MagicMock()
    update_result.scalar_one_or_none.return_value = 1.2
    session.execute = AsyncMock(
        side_effect=[MagicMock(), precheck_result, locked_result, update_result, MagicMock()]
    )
    factors = EvidenceFactors(
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

    await TrendEngine(session).apply_evidence(
        trend=trend,
        delta=0.1,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="test",
        factors=factors,
        reasoning="Test reasoning",
    )

    evidence_record = session.add.call_args.args[0]
    assert isinstance(evidence_record.base_weight, Decimal)
    assert isinstance(evidence_record.delta_log_odds, Decimal)
    assert isinstance(trend.current_log_odds, Decimal)
