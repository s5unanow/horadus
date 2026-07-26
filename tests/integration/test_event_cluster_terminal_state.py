from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.processing.event_clusterer import EventClusterer
from src.storage.database import async_session_maker
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event

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
