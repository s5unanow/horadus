from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.processing.event_clusterer import EventClusterer
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event

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
