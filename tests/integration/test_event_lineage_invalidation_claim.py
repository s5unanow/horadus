from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.processing.event_lineage_invalidation import claim_evidence_invalidation
from src.storage.database import async_session_maker
from src.storage.models import Event, EventClaim, Trend, TrendEvidence

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_lineage_invalidation_claim_has_one_winner() -> None:
    async with async_session_maker() as session:
        trend = Trend(
            name=f"Lineage claim {uuid4()}",
            runtime_trend_id=f"lineage-claim-{uuid4()}",
            definition={},
            baseline_log_odds=-2.0,
            current_log_odds=-1.8,
            indicators={},
            decay_half_life_days=30,
        )
        event = Event(canonical_summary="Concurrent lineage invalidation")
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
        evidence = TrendEvidence(
            trend_id=trend.id,
            event_id=event.id,
            event_claim_id=claim.id,
            signal_type="signal",
            delta_log_odds=0.2,
        )
        session.add(evidence)
        await session.commit()
        evidence_id = evidence.id

    both_loaded = asyncio.Event()
    load_lock = asyncio.Lock()
    loaded_count = 0
    invalidated_at = datetime.now(tz=UTC)

    async def attempt_claim() -> bool:
        nonlocal loaded_count
        async with async_session_maker() as session:
            evidence_row = await session.get(TrendEvidence, evidence_id)
            assert evidence_row is not None
            async with load_lock:
                loaded_count += 1
                if loaded_count == 2:
                    both_loaded.set()
            await both_loaded.wait()
            claimed = await claim_evidence_invalidation(session, evidence_row, invalidated_at)
            await session.commit()
            return claimed

    results = await asyncio.gather(attempt_claim(), attempt_claim())

    assert sorted(results) == [False, True]
    async with async_session_maker() as session:
        evidence_row = await session.get(TrendEvidence, evidence_id)
        assert evidence_row is not None
        assert evidence_row.is_invalidated is True
        assert evidence_row.invalidated_at == invalidated_at
