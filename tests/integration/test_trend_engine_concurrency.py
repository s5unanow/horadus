from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from src.core.trend_engine import EvidenceFactors, TrendEngine
from src.storage.database import async_session_maker
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.integration


def _sample_factors() -> EvidenceFactors:
    return EvidenceFactors(
        base_weight=0.04,
        severity=0.8,
        confidence=0.9,
        credibility=0.9,
        corroboration=0.67,
        novelty=1.0,
        evidence_age_days=0.0,
        temporal_decay_multiplier=1.0,
        direction_multiplier=1.0,
        raw_delta=0.1,
        clamped_delta=0.1,
    )


async def _create_trend_and_events(
    *, current_log_odds: float, updated_at: datetime
) -> tuple[UUID, UUID, UUID]:
    async with async_session_maker() as session:
        trend = Trend(
            name=f"Concurrency Trend {uuid4()}",
            description="Integration trend for concurrency checks",
            definition={"id": f"concurrency-{uuid4()}"},
            baseline_log_odds=0.0,
            current_log_odds=current_log_odds,
            indicators={},
            decay_half_life_days=30,
            is_active=True,
            updated_at=updated_at,
        )
        event_one = Event(canonical_summary=f"Concurrency event A {uuid4()}")
        event_two = Event(canonical_summary=f"Concurrency event B {uuid4()}")
        session.add_all([trend, event_one, event_two])
        await session.flush()
        trend_id = trend.id
        event_one_id = event_one.id
        event_two_id = event_two.id
        await session.commit()
    return trend_id, event_one_id, event_two_id


async def _apply_evidence_task(
    *,
    trend_id: UUID,
    event_id: UUID,
    signal_type: str,
    delta: float,
    ready_queue: asyncio.Queue[None],
    start_event: asyncio.Event,
) -> None:
    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
        if trend is None:
            msg = f"Trend '{trend_id}' not found for evidence task"
            raise RuntimeError(msg)
        engine = TrendEngine(session=session)
        ready_queue.put_nowait(None)
        await start_event.wait()
        await engine.apply_evidence(
            trend=trend,
            delta=delta,
            event_id=event_id,
            signal_type=signal_type,
            factors=_sample_factors(),
            reasoning="concurrency integration test",
        )
        await session.commit()


@pytest.mark.asyncio
async def test_apply_evidence_uses_atomic_delta_under_concurrency() -> None:
    trend_id, event_one_id, event_two_id = await _create_trend_and_events(
        current_log_odds=0.0,
        updated_at=datetime.now(tz=UTC) - timedelta(days=1),
    )
    start_event = asyncio.Event()
    ready_queue: asyncio.Queue[None] = asyncio.Queue()

    tasks = [
        asyncio.create_task(
            _apply_evidence_task(
                trend_id=trend_id,
                event_id=event_one_id,
                signal_type="signal_a",
                delta=0.2,
                ready_queue=ready_queue,
                start_event=start_event,
            )
        ),
        asyncio.create_task(
            _apply_evidence_task(
                trend_id=trend_id,
                event_id=event_two_id,
                signal_type="signal_b",
                delta=0.2,
                ready_queue=ready_queue,
                start_event=start_event,
            )
        ),
    ]

    await ready_queue.get()
    await ready_queue.get()
    start_event.set()
    await asyncio.gather(*tasks)

    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
        evidence_count = await session.scalar(
            select(func.count()).where(TrendEvidence.trend_id == trend_id)
        )

    assert trend is not None
    assert float(trend.current_log_odds) == pytest.approx(0.4, rel=1e-6)
    assert int(evidence_count or 0) == 2


@pytest.mark.asyncio
async def test_decay_does_not_overwrite_concurrent_manual_delta() -> None:
    trend_id, _event_one_id, _event_two_id = await _create_trend_and_events(
        current_log_odds=1.0,
        updated_at=datetime.now(tz=UTC) - timedelta(days=30),
    )
    start_event = asyncio.Event()

    async def _manual_override_task() -> None:
        async with async_session_maker() as session:
            trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
            if trend is None:
                msg = f"Trend '{trend_id}' not found for manual override task"
                raise RuntimeError(msg)
            engine = TrendEngine(session=session)
            await start_event.wait()
            await engine.apply_log_odds_delta(
                trend_id=trend_id,
                trend_name=trend.name,
                delta=0.2,
                reason="integration_manual_override",
                fallback_current_log_odds=float(trend.current_log_odds),
            )
            await session.commit()

    async def _decay_task() -> None:
        async with async_session_maker() as session:
            trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
            if trend is None:
                msg = f"Trend '{trend_id}' not found for decay task"
                raise RuntimeError(msg)
            engine = TrendEngine(session=session)
            await start_event.wait()
            await asyncio.sleep(0.1)
            await engine.apply_decay(trend=trend, as_of=datetime.now(tz=UTC))
            await session.commit()

    manual_task = asyncio.create_task(_manual_override_task())
    decay_task = asyncio.create_task(_decay_task())
    await asyncio.sleep(0.05)
    start_event.set()
    await asyncio.gather(manual_task, decay_task)

    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))

    assert trend is not None
    assert float(trend.current_log_odds) == pytest.approx(1.2, rel=1e-6)
