from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.processing.event_clusterer import EventClusterer
from src.storage.database import async_session_maker
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, EventItem, RawItem, Source
from src.storage.source_type import SourceType

pytestmark = pytest.mark.integration

EMBEDDING = [0.01] * 1536


@pytest.mark.asyncio
async def test_matching_event_excludes_closed_and_retracted_candidates() -> None:
    now = datetime.now(UTC)
    terminal_model = "terminal-state-filter"
    active_model = "active-state-filter"
    retracted = Event(
        canonical_summary="Retracted candidate",
        embedding=EMBEDDING,
        embedding_model=terminal_model,
        epistemic_state=EventEpistemicState.RETRACTED.value,
        activity_state=EventActivityState.ACTIVE.value,
        last_mention_at=now,
    )
    closed = Event(
        canonical_summary="Closed candidate",
        embedding=EMBEDDING,
        embedding_model=terminal_model,
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.CLOSED.value,
        last_mention_at=now,
    )
    active = Event(
        canonical_summary="Active candidate",
        embedding=EMBEDDING,
        embedding_model=active_model,
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.ACTIVE.value,
        last_mention_at=now,
    )
    async with async_session_maker() as session:
        session.add_all([retracted, closed, active])
        await session.flush()
        active_id = active.id
        await session.commit()

    async with async_session_maker() as session:
        clusterer = EventClusterer(session)
        terminal_match = await clusterer._find_matching_event(EMBEDDING, terminal_model, now)
        active_match = await clusterer._find_matching_event(EMBEDDING, active_model, now)

    assert terminal_match is None
    assert active_match is not None
    assert active_match[0].id == active_id


@pytest.mark.asyncio
async def test_event_link_rechecks_terminal_state_after_stale_match() -> None:
    now = datetime.now(UTC)
    event = Event(
        canonical_summary="Initially active candidate",
        embedding=EMBEDDING,
        embedding_model="stale-terminal-state",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.ACTIVE.value,
        last_mention_at=now,
    )
    async with async_session_maker() as setup_session:
        setup_session.add(event)
        await setup_session.flush()
        event_id = event.id
        await setup_session.commit()

    async with async_session_maker() as stale_session:
        clusterer = EventClusterer(stale_session)
        stale_match = await clusterer._find_matching_event(
            EMBEDDING,
            "stale-terminal-state",
            now,
        )
        assert stale_match is not None

        async with async_session_maker() as transition_session:
            transitioned = await transition_session.get(Event, event_id)
            assert transitioned is not None
            transitioned.activity_state = EventActivityState.CLOSED.value
            await transition_session.commit()

        linked = await clusterer._add_event_link(event_id, uuid4())

    assert linked is None
    assert stale_match[0].activity_state == EventActivityState.CLOSED.value


@pytest.mark.asyncio
async def test_create_linked_event_discards_concurrent_loser() -> None:
    item_title = f"Concurrent replacement {uuid4()}"
    async with async_session_maker() as setup_session:
        source = Source(type=SourceType.RSS, name=f"Source {uuid4()}")
        setup_session.add(source)
        await setup_session.flush()
        item = RawItem(
            source_id=source.id,
            external_id=str(uuid4()),
            title=item_title,
            raw_content="Concurrent clustering",
            content_hash=uuid4().hex * 2,
        )
        winner = Event(canonical_summary="Winning replacement")
        setup_session.add_all([item, winner])
        await setup_session.flush()
        item_id = item.id
        winner_id = winner.id
        setup_session.add(EventItem(event_id=winner_id, item_id=item_id))
        await setup_session.commit()

    async with async_session_maker() as cluster_session:
        persisted_item = await cluster_session.get(RawItem, item_id)
        assert persisted_item is not None
        result = await EventClusterer(cluster_session)._create_linked_event(persisted_item)
        await cluster_session.commit()

    async with async_session_maker() as verify_session:
        linked_event_id = await verify_session.scalar(
            select(EventItem.event_id).where(EventItem.item_id == item_id)
        )
        orphan_count = await verify_session.scalar(
            select(func.count()).select_from(Event).where(Event.canonical_summary == item_title)
        )

    assert result.event_id == winner_id
    assert result.created is False
    assert result.merged is True
    assert linked_event_id == winner_id
    assert orphan_count == 0


@pytest.mark.asyncio
async def test_create_linked_event_replaces_terminal_link_winner() -> None:
    item_title = f"Terminal winner replacement {uuid4()}"
    async with async_session_maker() as setup_session:
        source = Source(type=SourceType.RSS, name=f"Source {uuid4()}")
        setup_session.add(source)
        await setup_session.flush()
        item = RawItem(
            source_id=source.id,
            external_id=str(uuid4()),
            title=item_title,
            raw_content="Terminal winner must not receive new evidence",
            content_hash=uuid4().hex * 2,
        )
        terminal_winner = Event(
            canonical_summary="Terminal linked event",
            epistemic_state=EventEpistemicState.CONFIRMED.value,
            activity_state=EventActivityState.CLOSED.value,
        )
        setup_session.add_all([item, terminal_winner])
        await setup_session.flush()
        item_id = item.id
        terminal_event_id = terminal_winner.id
        setup_session.add(EventItem(event_id=terminal_event_id, item_id=item_id))
        await setup_session.commit()

    async with async_session_maker() as cluster_session:
        persisted_item = await cluster_session.get(RawItem, item_id)
        assert persisted_item is not None
        result = await EventClusterer(cluster_session)._create_linked_event(persisted_item)
        await cluster_session.commit()

    async with async_session_maker() as verify_session:
        linked_event = await verify_session.scalar(
            select(Event)
            .join(EventItem, EventItem.event_id == Event.id)
            .where(EventItem.item_id == item_id)
        )
        terminal_event = await verify_session.get(Event, terminal_event_id)

    assert result.created is True
    assert result.merged is False
    assert linked_event is not None
    assert linked_event.id == result.event_id
    assert linked_event.id != terminal_event_id
    assert linked_event.activity_state == EventActivityState.ACTIVE.value
    assert terminal_event is not None
    assert terminal_event.activity_state == EventActivityState.CLOSED.value
