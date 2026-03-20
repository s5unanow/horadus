from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.processing.event_lifecycle import EventLifecycleManager
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, EventLifecycle

pytestmark = pytest.mark.unit


def _build_event(
    *,
    lifecycle_status: str = EventLifecycle.EMERGING.value,
    unique_source_count: int = 1,
    independent_evidence_count: int | None = None,
) -> Event:
    now = datetime.now(tz=UTC)
    return Event(
        canonical_summary="Event summary",
        source_count=unique_source_count,
        unique_source_count=unique_source_count,
        independent_evidence_count=(
            independent_evidence_count
            if independent_evidence_count is not None
            else unique_source_count
        ),
        lifecycle_status=lifecycle_status,
        first_seen_at=now,
        last_mention_at=now,
    )


def test_on_event_mention_promotes_emerging_to_confirmed(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=3, lifecycle_status=EventLifecycle.EMERGING.value)

    changed = manager.on_event_mention(event)

    assert changed is True
    assert event.epistemic_state == EventEpistemicState.CONFIRMED.value
    assert event.activity_state == EventActivityState.ACTIVE.value
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at is not None


def test_on_event_mention_revives_fading_event(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=4, lifecycle_status=EventLifecycle.FADING.value)

    changed = manager.on_event_mention(event)

    assert changed is True
    assert event.activity_state == EventActivityState.ACTIVE.value
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value


def test_on_event_mention_keeps_emerging_event_when_under_threshold(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=1, lifecycle_status=EventLifecycle.EMERGING.value)

    changed = manager.on_event_mention(event)

    assert changed is False
    assert event.epistemic_state == EventEpistemicState.EMERGING.value
    assert event.activity_state == EventActivityState.ACTIVE.value
    assert event.lifecycle_status == EventLifecycle.EMERGING.value


def test_on_event_mention_uses_independent_evidence_count_for_confirmation(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(
        unique_source_count=5,
        independent_evidence_count=2,
        lifecycle_status=EventLifecycle.EMERGING.value,
    )

    changed = manager.on_event_mention(event)

    assert changed is False
    assert event.epistemic_state == EventEpistemicState.EMERGING.value
    assert event.lifecycle_status == EventLifecycle.EMERGING.value


def test_on_event_mention_preserves_retracted_epistemic_state(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=5, lifecycle_status=EventLifecycle.ARCHIVED.value)
    event.epistemic_state = EventEpistemicState.RETRACTED.value
    event.activity_state = EventActivityState.DORMANT.value

    changed = manager.on_event_mention(event)

    assert changed is True
    assert event.epistemic_state == EventEpistemicState.RETRACTED.value
    assert event.activity_state == EventActivityState.ACTIVE.value
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value


def test_sync_event_state_promotes_without_touching_last_mention(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    event = _build_event(unique_source_count=1, lifecycle_status=EventLifecycle.EMERGING.value)
    original_last_mention = event.last_mention_at
    event.independent_evidence_count = 3

    changed = manager.sync_event_state(event)

    assert changed is True
    assert event.last_mention_at == original_last_mention
    assert event.epistemic_state == EventEpistemicState.CONFIRMED.value
    assert event.lifecycle_status == EventLifecycle.CONFIRMED.value
    assert event.confirmed_at == original_last_mention


@pytest.mark.asyncio
async def test_run_decay_check_returns_transition_counts(mock_db_session) -> None:
    manager = EventLifecycleManager(mock_db_session)
    mock_db_session.execute.side_effect = [
        SimpleNamespace(all=lambda: [("e1",), ("e2",)]),
        SimpleNamespace(all=lambda: [("e3",)]),
    ]

    result = await manager.run_decay_check()

    assert result["task"] == "check_event_lifecycles"
    assert result["activity_active_to_dormant"] == 2
    assert result["activity_dormant_to_closed"] == 1
    assert result["confirmed_to_fading"] == 2
    assert result["fading_to_archived"] == 1
