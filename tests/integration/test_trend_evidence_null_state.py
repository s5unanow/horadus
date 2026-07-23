from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.storage.database import async_session_maker
from src.storage.models import Event, EventClaim, Trend, TrendEvidence

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_active_evidence_unique_index_treats_null_state_versions_as_equal() -> None:
    async with async_session_maker() as session:
        runtime_trend_id = f"null-state-unique-{uuid4()}"
        trend = Trend(
            name=f"Null State Uniqueness Trend {uuid4()}",
            description="Integration trend for null-state uniqueness",
            runtime_trend_id=runtime_trend_id,
            definition={"id": runtime_trend_id},
            baseline_log_odds=0.0,
            current_log_odds=0.0,
            indicators={},
            decay_half_life_days=30,
            is_active=True,
        )
        event = Event(canonical_summary=f"Null-state evidence event {uuid4()}")
        session.add_all([trend, event])
        await session.flush()
        claim = EventClaim(
            event_id=event.id,
            claim_key="__event__",
            claim_text=event.canonical_summary,
            claim_type="fallback",
            claim_order=0,
        )
        session.add(claim)
        await session.flush()
        evidence_kwargs = {
            "trend_id": trend.id,
            "event_id": event.id,
            "event_claim_id": claim.id,
            "state_version_id": None,
            "signal_type": "duplicate-null-state",
            "delta_log_odds": 0.1,
        }
        session.add(TrendEvidence(**evidence_kwargs))
        await session.flush()
        session.add(TrendEvidence(**evidence_kwargs))

        with pytest.raises(IntegrityError):
            await session.flush()
