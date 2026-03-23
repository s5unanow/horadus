from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.storage.event_extraction import (
    capture_canonical_extraction,
    clear_all_extraction_state,
    demote_current_extraction_to_provisional,
    promote_canonical_extraction,
    provisional_extraction_payload,
    resolved_extraction_status,
)
from src.storage.models import Event

pytestmark = pytest.mark.unit


def test_demote_current_extraction_to_provisional_restores_canonical_state() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Primary item title",
        event_summary="Stable canonical summary",
        extracted_what="Canonical extraction",
        categories=["military"],
        extracted_claims={"trend_impacts": []},
        extraction_provenance={"stage": "tier2", "active_route": {"model": "gpt-4.1-mini"}},
        extraction_status="canonical",
    )
    snapshot = capture_canonical_extraction(event)

    event.event_summary = "Degraded provisional summary"
    event.extracted_what = "Provisional extraction"
    event.categories = ["security"]
    event.extracted_claims = {"trend_impacts": [{"signal_type": "military_movement"}]}
    event.extraction_provenance = {"stage": "tier2", "active_route": {"model": "gpt-4.1-nano"}}

    demote_current_extraction_to_provisional(
        event,
        canonical_snapshot=snapshot,
        policy={"degraded_llm": True},
        replay_enqueued=True,
    )

    assert event.event_summary == "Stable canonical summary"
    assert event.extracted_what == "Canonical extraction"
    assert event.categories == ["military"]
    assert resolved_extraction_status(event) == "provisional"
    provisional = provisional_extraction_payload(event)
    assert provisional is not None
    assert provisional["summary"] == "Degraded provisional summary"
    assert provisional["categories"] == ["security"]
    assert provisional["policy"] == {"degraded_llm": True}
    assert provisional["replay_enqueued"] is True


def test_promote_canonical_extraction_clears_prior_provisional_payload() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Primary item title",
        event_summary="Promoted canonical summary",
        extracted_what="Promoted extraction",
        categories=["security"],
        provisional_extraction={
            "status": "provisional",
            "captured_at": datetime(2026, 3, 23, tzinfo=UTC).isoformat(),
            "provenance": {"stage": "tier2", "active_route": {"model": "gpt-4.1-nano"}},
            "replay_enqueued": True,
        },
        extraction_status="provisional",
    )

    promote_canonical_extraction(
        event,
        extraction_provenance={"stage": "tier2", "active_route": {"model": "gpt-4.1-mini"}},
    )

    assert resolved_extraction_status(event) == "canonical"
    assert event.provisional_extraction == {}
    assert event.extraction_provenance["promotion"]["source_status"] == "provisional"
    assert (
        event.extraction_provenance["promotion"]["superseded_provisional"]["replay_enqueued"]
        is True
    )


def test_clear_all_extraction_state_resets_canonical_and_provisional_fields() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Primary item title",
        event_summary="summary",
        extracted_who=["A"],
        extracted_what="what",
        extracted_where="where",
        extracted_when=datetime(2026, 3, 23, tzinfo=UTC),
        extracted_claims={"claims": ["c"]},
        categories=["security"],
        has_contradictions=True,
        contradiction_notes="note",
        extraction_status="provisional",
        provisional_extraction={"summary": "pending"},
    )

    clear_all_extraction_state(event)

    assert event.event_summary is None
    assert event.extracted_who is None
    assert event.extracted_claims is None
    assert event.categories == []
    assert resolved_extraction_status(event) == "none"
    assert provisional_extraction_payload(event) is None


def test_resolved_extraction_status_normalizes_explicit_values() -> None:
    event = Event(canonical_summary="Primary item title", extraction_status=" CANONICAL ")

    assert resolved_extraction_status(event) == "canonical"


def test_resolved_extraction_status_infers_provisional_or_none_without_valid_status() -> None:
    provisional_event = Event(
        canonical_summary="Primary item title",
        extraction_status="unexpected",
        provisional_extraction={"summary": "Held degraded summary"},
    )
    empty_event = Event(canonical_summary="Primary item title", extraction_status="unexpected")

    assert resolved_extraction_status(provisional_event) == "provisional"
    assert resolved_extraction_status(empty_event) == "none"
