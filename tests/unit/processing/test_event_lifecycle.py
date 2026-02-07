from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.processing.event_lifecycle import EventLifecycleManager
from src.storage.models import Event, EventLifecycle

pytestmark = pytest.mark.unit


def _build_event(
    *,
    lifecycle_status: str = EventLifecycle.EMERGING.value,
    unique_source_count: int = 1,
) -> Event:
    now = datetime.now(tz=UTC)
    return Event(
        canonical_summary="Event summary",
        source_count=unique_source_count,
        unique_source_count=unique_source_count,
        lifecycle_status=lifecycle_status,
        first_seen_at=now,
        last_mention_at=now,
    )


def test_on_event_mention_promotes_emerging_to_confirmed(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=3, lifecycle_status=EventLifecycle.EMERGING.value)

    changed = manager.on_event_mention(event)

    assert changed is True
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at is not None


def test_on_event_mention_revives_fading_event(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=4, lifecycle_status=EventLifecycle.FADING.value)

    changed = manager.on_event_mention(event)

    assert changed is True
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value


@pytest.mark.asyncio
async def test_run_decay_check_returns_transition_counts(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    mock_db_session.execute.side_effect = [
        SimpleNamespace(all=lambda: [("e1",), ("e2",)]),
        SimpleNamespace(all=lambda: [("e3",)]),
    ]

    result = await manager.run_decay_check()

    assert result["task"] == "check_event_lifecycles"
    assert result["confirmed_to_fading"] == 2
    assert result["fading_to_archived"] == 1
