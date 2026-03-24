from __future__ import annotations

from uuid import uuid4

from src.storage.event_summary import (
    event_summary_expression,
    refresh_event_summary_from_canonical,
    resolved_event_summary,
)
from src.storage.models import Event


def test_resolved_event_summary_prefers_event_summary_and_falls_back_to_canonical() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Primary item title",
        event_summary=" Synthesized event summary ",
    )
    assert resolved_event_summary(event) == "Synthesized event summary"

    event.event_summary = " "
    assert resolved_event_summary(event) == "Primary item title"


def test_refresh_event_summary_from_canonical_updates_only_fallback_values() -> None:
    fallback_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Old primary title",
    )
    refresh_event_summary_from_canonical(
        fallback_event,
        previous_canonical_summary="Old primary title",
    )
    assert fallback_event.event_summary == "Updated primary title"

    synthesized_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Persistent synthesized summary",
    )
    refresh_event_summary_from_canonical(
        synthesized_event,
        previous_canonical_summary="Old primary title",
    )
    assert synthesized_event.event_summary == "Persistent synthesized summary"

    preserved_tier2_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Old primary title",
        extraction_provenance={"stage": "tier2"},
    )
    refresh_event_summary_from_canonical(
        preserved_tier2_event,
        previous_canonical_summary="Old primary title",
    )
    assert preserved_tier2_event.event_summary == "Old primary title"

    replay_pending_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Stale synthesized summary",
        extraction_provenance={"stage": "tier2", "status": "replay_pending"},
    )
    refresh_event_summary_from_canonical(
        replay_pending_event,
        previous_canonical_summary="Old primary title",
    )
    assert replay_pending_event.event_summary == "Updated primary title"


def test_event_summary_expression_prefers_event_summary_with_canonical_fallback() -> None:
    expression = event_summary_expression()

    compiled = str(expression)
    assert "coalesce" in compiled.lower()
    assert "event_summary" in compiled
    assert "canonical_summary" in compiled


def test_refresh_event_summary_from_canonical_updates_provisional_fallback_values() -> None:
    provisional_fallback_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Old primary title",
        extraction_status="provisional",
    )

    refresh_event_summary_from_canonical(
        provisional_fallback_event,
        previous_canonical_summary="Old primary title",
    )

    assert provisional_fallback_event.event_summary == "Updated primary title"


def test_refresh_event_summary_from_canonical_preserves_distinct_provisional_summary() -> None:
    provisional_event = Event(
        id=uuid4(),
        canonical_summary="Updated primary title",
        event_summary="Held degraded summary",
        extraction_status="provisional",
    )

    refresh_event_summary_from_canonical(
        provisional_event,
        previous_canonical_summary="Old primary title",
    )

    assert provisional_event.event_summary == "Held degraded summary"
