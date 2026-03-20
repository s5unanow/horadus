from __future__ import annotations

from uuid import uuid4

import pytest

from src.storage.event_state import (
    FALLBACK_CORROBORATION_MODE,
    EventActivityState,
    EventEpistemicState,
    activity_state_from_legacy,
    epistemic_state_from_legacy,
    event_state_snapshot,
    legacy_lifecycle_status_for_states,
    resolved_corroboration_mode,
    resolved_corroboration_score,
    resolved_independent_evidence_count,
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


def test_corroboration_helpers_prefer_persisted_independent_values() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Corroboration snapshot",
        unique_source_count=5,
        independent_evidence_count=2,
        corroboration_score=1.35,
        corroboration_mode="provenance_aware",
    )

    assert resolved_independent_evidence_count(event) == 2
    assert resolved_corroboration_score(event) == pytest.approx(1.35)
    assert resolved_corroboration_mode(event) == "provenance_aware"


def test_corroboration_helpers_fall_back_to_legacy_counts() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Fallback corroboration snapshot",
        source_count=3,
        unique_source_count=2,
        independent_evidence_count=0,
        corroboration_score=0.0,
    )

    assert resolved_independent_evidence_count(event) == 2
    assert resolved_corroboration_score(event) == pytest.approx(2.0)
    assert resolved_corroboration_mode(event) == FALLBACK_CORROBORATION_MODE


def test_corroboration_helpers_cover_source_count_and_invalid_score_paths() -> None:
    source_only_event = Event(
        id=uuid4(),
        canonical_summary="Source-count fallback",
        source_count=3,
        unique_source_count=0,
        independent_evidence_count=0,
    )
    invalid_score_event = Event(
        id=uuid4(),
        canonical_summary="Invalid score fallback",
        unique_source_count=2,
        corroboration_score="bad",
    )

    assert resolved_independent_evidence_count(source_only_event) == 3
    assert resolved_corroboration_score(invalid_score_event) == pytest.approx(2.0)
