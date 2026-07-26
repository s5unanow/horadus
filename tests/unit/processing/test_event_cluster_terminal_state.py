from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.processing.event_cluster_link import (
    ClusterResult,
    create_linked_event,
    resolve_event_link_failure,
)
from src.processing.event_clusterer import EventClusterer
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, EventItem, RawItem

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_matching_query_excludes_terminal_split_states() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    result = await EventClusterer(session)._find_matching_event(
        [0.1, 0.2],
        "embedding-model",
        datetime.now(UTC),
    )

    assert result is None
    query_text = str(session.execute.await_args.args[0]).lower()
    where_clause = query_text.split("\nwhere ", maxsplit=1)[1]
    assert "events.epistemic_state !=" in where_clause
    assert "events.activity_state !=" in where_clause
    assert "events.lifecycle_status" not in where_clause


@pytest.mark.asyncio
async def test_active_split_state_remains_eligible_with_legacy_archived_projection() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Canonical split state wins",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.ACTIVE.value,
        lifecycle_status="archived",
    )
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = (event, 0.08)
    session.execute = AsyncMock(return_value=execute_result)

    result = await EventClusterer(session)._find_matching_event(
        [0.1, 0.2],
        "embedding-model",
        datetime.now(UTC),
    )

    assert result is not None
    assert result[0] is event
    assert result[1] == pytest.approx(0.92)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("epistemic_state", "activity_state"),
    [
        (EventEpistemicState.RETRACTED.value, EventActivityState.ACTIVE.value),
        (EventEpistemicState.CONFIRMED.value, EventActivityState.CLOSED.value),
    ],
)
async def test_add_event_link_rechecks_terminal_state_under_lock(
    epistemic_state: str,
    activity_state: str,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Transitioned after similarity match",
        epistemic_state=epistemic_state,
        activity_state=activity_state,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=event)

    linked = await EventClusterer(session)._add_event_link(event.id, uuid4())

    assert linked is None
    session.get.assert_awaited_once_with(
        Event,
        event.id,
        with_for_update=True,
    )
    session.refresh.assert_awaited_once_with(
        event,
        attribute_names=["epistemic_state", "activity_state"],
        with_for_update=True,
    )
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_terminal_link_rejection_creates_replacement_event() -> None:
    event = Event(id=uuid4(), canonical_summary="Closed match")
    item = RawItem(id=uuid4())
    replacement = ClusterResult(
        item_id=item.id,
        event_id=uuid4(),
        created=True,
        merged=False,
    )
    create_linked_event = AsyncMock(return_value=replacement)
    find_existing_event_id = AsyncMock()

    result = await resolve_event_link_failure(
        event=event,
        item=item,
        similarity=0.9,
        terminal=True,
        create_linked_event=create_linked_event,
        find_existing_event_id=find_existing_event_id,
    )

    assert result is replacement
    create_linked_event.assert_awaited_once_with(item)
    find_existing_event_id.assert_not_called()


@pytest.mark.asyncio
async def test_create_linked_event_resolves_concurrent_link_winner() -> None:
    item = RawItem(id=uuid4())
    losing_event = Event(id=uuid4(), canonical_summary="Losing replacement")
    winning_event = Event(
        id=uuid4(),
        canonical_summary="Winning replacement",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.ACTIVE.value,
    )
    winning_link = EventItem(event_id=winning_event.id, item_id=item.id)
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = (winning_link, winning_event)
    session.execute = AsyncMock(return_value=execute_result)
    refresh_event_provenance = AsyncMock()

    result = await create_linked_event(
        session=session,
        item=item,
        create_event=AsyncMock(return_value=losing_event),
        add_link=AsyncMock(return_value=False),
        refresh_event_provenance=refresh_event_provenance,
    )

    assert result == ClusterResult(
        item_id=item.id,
        event_id=winning_event.id,
        created=False,
        merged=True,
    )
    session.delete.assert_awaited_once_with(losing_event)
    session.flush.assert_awaited_once()
    refresh_event_provenance.assert_not_called()


@pytest.mark.asyncio
async def test_create_linked_event_fails_when_conflict_has_no_winner() -> None:
    item = RawItem(id=uuid4())
    losing_event = Event(id=uuid4(), canonical_summary="Unlinked replacement")
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(RuntimeError, match=f"Failed to link new event for item {item.id}"):
        await create_linked_event(
            session=session,
            item=item,
            create_event=AsyncMock(return_value=losing_event),
            add_link=AsyncMock(side_effect=[False, False]),
            refresh_event_provenance=AsyncMock(),
        )

    session.delete.assert_awaited_once_with(losing_event)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_linked_event_retries_when_conflict_winner_disappears() -> None:
    item = RawItem(id=uuid4())
    replacement = Event(id=uuid4(), canonical_summary="Retried replacement")
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
    refresh_event_provenance = AsyncMock()

    result = await create_linked_event(
        session=session,
        item=item,
        create_event=AsyncMock(return_value=replacement),
        add_link=AsyncMock(side_effect=[False, True]),
        refresh_event_provenance=refresh_event_provenance,
    )

    assert result == ClusterResult(
        item_id=item.id,
        event_id=replacement.id,
        created=True,
        merged=False,
    )
    session.delete.assert_not_called()
    refresh_event_provenance.assert_awaited_once_with(replacement)


@pytest.mark.asyncio
async def test_create_linked_event_preserves_terminal_link_winner() -> None:
    item = RawItem(id=uuid4())
    replacement = Event(id=uuid4(), canonical_summary="Eligible replacement")
    terminal_event = Event(
        id=uuid4(),
        canonical_summary="Terminal winner",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.CLOSED.value,
    )
    terminal_link = EventItem(event_id=terminal_event.id, item_id=item.id)
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = (terminal_link, terminal_event)
    session.execute = AsyncMock(return_value=execute_result)
    refresh_event_provenance = AsyncMock()

    result = await create_linked_event(
        session=session,
        item=item,
        create_event=AsyncMock(return_value=replacement),
        add_link=AsyncMock(return_value=False),
        refresh_event_provenance=refresh_event_provenance,
    )

    assert result == ClusterResult(
        item_id=item.id,
        event_id=terminal_event.id,
        created=False,
        merged=True,
    )
    session.delete.assert_awaited_once_with(replacement)
    refresh_event_provenance.assert_not_called()
