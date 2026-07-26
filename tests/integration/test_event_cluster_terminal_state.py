from __future__ import annotations

from datetime import UTC, datetime

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
