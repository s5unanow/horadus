from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.api.routes.events import (
    EventMergeRequest,
    EventSplitRequest,
    merge_event,
    split_event_route,
)
from src.storage.database import async_session_maker
from src.storage.event_lineage_models import EventLineage
from src.storage.models import (
    Event,
    EventClaim,
    EventItem,
    LLMReplayQueueItem,
    RawItem,
    Source,
    SourceType,
    Trend,
    TrendEvidence,
)
from src.storage.restatement_models import HumanFeedback, TrendRestatement

pytestmark = pytest.mark.integration


def _build_source(*, name: str) -> Source:
    return Source(
        type=SourceType.RSS,
        name=name,
        credibility_score=0.8,
    )


def _build_item(*, source_id: UUID, title: str, hours_ago: int) -> RawItem:
    now = datetime.now(tz=UTC)
    return RawItem(
        source_id=source_id,
        external_id=f"raw-{uuid4()}",
        title=title,
        raw_content=f"{title} content",
        url=f"https://example.com/{uuid4()}",
        content_hash=str(uuid4()).replace("-", "") + str(uuid4()).replace("-", "")[:32],
        published_at=now - timedelta(hours=hours_ago),
    )


def _build_trend(*, runtime_id: str, current_log_odds: float) -> Trend:
    return Trend(
        name=f"Trend {runtime_id}",
        description="Integration trend for event lineage repairs",
        runtime_trend_id=runtime_id,
        definition={"id": runtime_id},
        baseline_log_odds=-2.0,
        current_log_odds=current_log_odds,
        indicators={"signal_primary": {"weight": 0.04, "direction": "escalatory"}},
        decay_half_life_days=30,
        is_active=True,
    )


async def _seed_merge_repair_fixture(session):
    source = _build_source(name=f"Merge Source {uuid4()}")
    target_source = _build_source(name=f"Merge Target Source {uuid4()}")
    trend = _build_trend(runtime_id=f"merge-lineage-{uuid4()}", current_log_odds=-1.65)
    source_event = Event(
        canonical_summary="Source event",
        source_count=1,
        unique_source_count=1,
        lifecycle_status="confirmed",
        first_seen_at=datetime.now(tz=UTC) - timedelta(hours=5),
        last_mention_at=datetime.now(tz=UTC) - timedelta(hours=1),
    )
    target_event = Event(
        canonical_summary="Target event",
        source_count=1,
        unique_source_count=1,
        lifecycle_status="archived",
        activity_state="closed",
        first_seen_at=datetime.now(tz=UTC) - timedelta(hours=4),
        last_mention_at=datetime.now(tz=UTC) - timedelta(minutes=30),
    )
    session.add_all([source, target_source, trend, source_event, target_event])
    await session.flush()

    source_item = _build_item(source_id=source.id, title="Source item", hours_ago=4)
    target_item = _build_item(source_id=target_source.id, title="Target item", hours_ago=2)
    session.add_all([source_item, target_item])
    await session.flush()
    session.add_all(
        [
            EventItem(event_id=source_event.id, item_id=source_item.id),
            EventItem(event_id=target_event.id, item_id=target_item.id),
        ]
    )
    source_claim = EventClaim(
        event_id=source_event.id,
        claim_key="__event__",
        claim_text=source_event.canonical_summary,
        claim_type="fallback",
        claim_order=0,
    )
    target_claim = EventClaim(
        event_id=target_event.id,
        claim_key="__event__",
        claim_text=target_event.canonical_summary,
        claim_type="fallback",
        claim_order=0,
    )
    session.add_all([source_claim, target_claim])
    await session.flush()
    session.add_all(
        [
            TrendEvidence(
                trend_id=trend.id,
                event_id=source_event.id,
                event_claim_id=source_claim.id,
                signal_type="signal_primary",
                delta_log_odds=0.2,
                reasoning="Source evidence",
            ),
            TrendEvidence(
                trend_id=trend.id,
                event_id=target_event.id,
                event_claim_id=target_claim.id,
                signal_type="signal_primary",
                delta_log_odds=0.15,
                reasoning="Target evidence",
            ),
        ]
    )
    session.add(
        LLMReplayQueueItem(
            stage="tier2",
            event_id=source_event.id,
            status="error",
            priority=10,
            last_error="stale replay",
            details={"reason": "prior-repair"},
        )
    )
    session.add(
        HumanFeedback(
            target_type="event",
            target_id=source_event.id,
            action="mark_noise",
            created_by="analyst@horadus",
        )
    )
    await session.commit()
    return source_event, target_event, source_item, target_item, trend


async def _assert_merge_repair_outcome(
    session,
    *,
    source_event_id: UUID,
    target_event_id: UUID,
    source_item_id: UUID,
    target_item_id: UUID,
    trend_id: UUID,
) -> None:
    refreshed_source = await session.get(Event, source_event_id)
    refreshed_target = await session.get(Event, target_event_id)
    refreshed_trend = await session.get(Trend, trend_id)
    assert refreshed_source is not None
    assert refreshed_target is not None
    assert refreshed_trend is not None
    _assert_merge_repair_events(
        refreshed_source=refreshed_source,
        refreshed_target=refreshed_target,
        refreshed_trend=refreshed_trend,
    )

    await _assert_merge_repair_side_effects(
        session,
        source_event_id=source_event_id,
        target_event_id=target_event_id,
        source_item_id=source_item_id,
        target_item_id=target_item_id,
    )


def _assert_merge_repair_events(
    *,
    refreshed_source: Event,
    refreshed_target: Event,
    refreshed_trend: Trend,
) -> None:
    assert refreshed_source.source_count == 0
    assert refreshed_source.activity_state == "closed"
    assert refreshed_target.source_count == 2
    assert refreshed_target.activity_state == "active"
    assert float(refreshed_trend.current_log_odds) == pytest.approx(-2.0)


async def _assert_merge_repair_side_effects(
    session,
    *,
    source_event_id: UUID,
    target_event_id: UUID,
    source_item_id: UUID,
    target_item_id: UUID,
) -> None:
    moved_links = list(
        (
            await session.scalars(select(EventItem).where(EventItem.event_id == target_event_id))
        ).all()
    )
    assert {link.item_id for link in moved_links} == {source_item_id, target_item_id}

    evidence_rows = list((await session.scalars(select(TrendEvidence))).all())
    assert len(evidence_rows) == 2
    assert all(row.is_invalidated for row in evidence_rows)

    lineage_rows = list((await session.scalars(select(EventLineage))).all())
    assert len(lineage_rows) == 1
    assert lineage_rows[0].lineage_kind == "merge"
    assert lineage_rows[0].source_event_id == source_event_id
    assert lineage_rows[0].target_event_id == target_event_id

    replay_rows = list((await session.scalars(select(LLMReplayQueueItem))).all())
    assert len(replay_rows) == 1
    assert replay_rows[0].event_id == target_event_id
    assert replay_rows[0].stage == "tier2"

    feedback_rows = list((await session.scalars(select(HumanFeedback))).all())
    assert len(feedback_rows) == 1
    assert feedback_rows[0].target_id == target_event_id
    assert feedback_rows[0].action == "mark_noise"

    restatement_rows = list((await session.scalars(select(TrendRestatement))).all())
    assert len(restatement_rows) == 2
    assert all(row.restatement_kind == "reclassification" for row in restatement_rows)


@pytest.mark.asyncio
async def test_split_event_records_lineage_invalidates_evidence_and_queues_replay() -> None:
    async with async_session_maker() as session:
        source = _build_source(name=f"Source {uuid4()}")
        trend = _build_trend(runtime_id=f"split-lineage-{uuid4()}", current_log_odds=-1.8)
        event = Event(
            canonical_summary="Combined event before split",
            source_count=3,
            unique_source_count=3,
            lifecycle_status="confirmed",
            first_seen_at=datetime.now(tz=UTC) - timedelta(hours=6),
            last_mention_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
        session.add_all([source, trend, event])
        await session.flush()

        items = [
            _build_item(source_id=source.id, title="Item one", hours_ago=5),
            _build_item(source_id=source.id, title="Item two", hours_ago=4),
            _build_item(source_id=source.id, title="Item three", hours_ago=3),
        ]
        session.add_all(items)
        await session.flush()
        session.add_all([EventItem(event_id=event.id, item_id=item.id) for item in items])
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
            signal_type="signal_primary",
            delta_log_odds=0.2,
            reasoning="Combined evidence before split",
        )
        session.add(evidence)
        await session.commit()

        result = await split_event_route(
            event_id=event.id,
            payload=EventSplitRequest(
                item_ids=[items[0].id],
                notes="Split unrelated follow-up",
                created_by="analyst@horadus",
            ),
            session=session,
        )
        await session.commit()

        source_event = await session.get(Event, event.id)
        new_event = await session.get(Event, result.created_event_id)
        refreshed_trend = await session.get(Trend, trend.id)
        assert source_event is not None
        assert new_event is not None
        assert refreshed_trend is not None
        assert source_event.source_count == 2
        assert source_event.epistemic_state == "emerging"
        assert source_event.activity_state == "active"
        assert new_event.source_count == 1
        assert float(refreshed_trend.current_log_odds) == pytest.approx(-2.0)

        moved_link = await session.scalar(select(EventItem).where(EventItem.item_id == items[0].id))
        assert moved_link is not None
        assert moved_link.event_id == new_event.id

        evidence_rows = list(
            (
                await session.scalars(
                    select(TrendEvidence).where(TrendEvidence.event_id == event.id)
                )
            ).all()
        )
        assert len(evidence_rows) == 1
        assert evidence_rows[0].is_invalidated is True

        lineage_rows = list((await session.scalars(select(EventLineage))).all())
        assert len(lineage_rows) == 1
        assert lineage_rows[0].lineage_kind == "split"
        assert lineage_rows[0].source_event_id == event.id
        assert lineage_rows[0].target_event_id == new_event.id

        replay_rows = list(
            (
                await session.scalars(
                    select(LLMReplayQueueItem).order_by(LLMReplayQueueItem.event_id.asc())
                )
            ).all()
        )
        assert [row.event_id for row in replay_rows] == sorted([event.id, new_event.id])
        assert all(row.stage == "tier2" for row in replay_rows)

        restatement_rows = list((await session.scalars(select(TrendRestatement))).all())
        assert len(restatement_rows) == 1
        assert restatement_rows[0].restatement_kind == "reclassification"


@pytest.mark.asyncio
async def test_merge_event_records_lineage_closes_source_and_queues_target_replay() -> None:
    async with async_session_maker() as session:
        (
            source_event,
            target_event,
            source_item,
            target_item,
            trend,
        ) = await _seed_merge_repair_fixture(session)

        result = await merge_event(
            event_id=source_event.id,
            payload=EventMergeRequest(
                target_event_id=target_event.id,
                notes="Merge duplicate event",
                created_by="analyst@horadus",
            ),
            session=session,
        )
        await session.commit()

        assert result.target_event_id == target_event.id
        await _assert_merge_repair_outcome(
            session,
            source_event_id=source_event.id,
            target_event_id=target_event.id,
            source_item_id=source_item.id,
            target_item_id=target_item.id,
            trend_id=trend.id,
        )
