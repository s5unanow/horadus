from __future__ import annotations

from uuid import uuid4

import pytest

from src.storage.event_state import (
    EventActivityState,
    EventEpistemicState,
    activity_state_from_legacy,
    epistemic_state_from_legacy,
    event_state_snapshot,
    legacy_lifecycle_status_for_states,
)
from src.storage.models import Event

pytestmark = pytest.mark.unit


def test_event_state_helpers_cover_closed_and_dormant_compatibility() -> None:
    assert (
        legacy_lifecycle_status_for_states(
            epistemic_state=EventEpistemicState.CONFIRMED.value,
            activity_state=EventActivityState.CLOSED.value,
        )
        == "archived"
    )
    assert (
        legacy_lifecycle_status_for_states(
            epistemic_state=EventEpistemicState.CONFIRMED.value,
            activity_state=EventActivityState.DORMANT.value,
        )
        == "fading"
    )
    assert (
        activity_state_from_legacy(lifecycle_status="archived") == EventActivityState.CLOSED.value
    )
    assert (
        epistemic_state_from_legacy(lifecycle_status="archived", has_contradictions=True)
        == EventEpistemicState.CONFIRMED.value
    )


def test_event_state_snapshot_uses_explicit_split_state_when_present() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="State snapshot",
        lifecycle_status="confirmed",
        epistemic_state=EventEpistemicState.CONTESTED.value,
        activity_state=EventActivityState.ACTIVE.value,
    )

    assert event_state_snapshot(event) == {
        "epistemic_state": "contested",
        "activity_state": "active",
        "lifecycle_status": "confirmed",
    }
