from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.trend_engine import EvidenceFactors, TrendEngine

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_apply_evidence_rejects_missing_active_state_before_query() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    trend = MagicMock(
        id=uuid4(),
        active_state_version_id=None,
    )
    factors = EvidenceFactors(
        base_weight=0.04,
        severity=0.8,
        confidence=0.95,
        credibility=0.9,
        corroboration=0.67,
        novelty=1.0,
        evidence_age_days=0.0,
        temporal_decay_multiplier=1.0,
        direction_multiplier=1.0,
        raw_delta=0.024,
        clamped_delta=0.024,
    )

    with pytest.raises(ValueError, match="has no active state version"):
        await TrendEngine(session).apply_evidence(
            trend=trend,
            delta=0.1,
            event_id=uuid4(),
            event_claim_id=uuid4(),
            signal_type="test",
            factors=factors,
            reasoning="Test reasoning",
        )

    session.execute.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
