"""Helpers for canonical vs provisional event extraction state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.storage.models import Event

EXTRACTION_STATUS_NONE = "none"
EXTRACTION_STATUS_CANONICAL = "canonical"
EXTRACTION_STATUS_PROVISIONAL = "provisional"


@dataclass(frozen=True, slots=True)
class CanonicalExtractionSnapshot:
    """Snapshot of the stable event extraction fields before a provisional write."""

    event_summary: str | None
    extracted_who: list[str] | None
    extracted_what: str | None
    extracted_where: str | None
    extracted_when: datetime | None
    extracted_claims: dict[str, Any] | None
    categories: list[str] | None
    has_contradictions: bool
    contradiction_notes: str | None
    extraction_provenance: dict[str, Any]


def resolved_extraction_status(event: Event) -> str:
    """Return the normalized extraction status for an event."""
    raw_status = getattr(event, "extraction_status", None)
    if isinstance(raw_status, str):
        normalized = raw_status.strip().lower()
        if normalized in {
            EXTRACTION_STATUS_NONE,
            EXTRACTION_STATUS_CANONICAL,
            EXTRACTION_STATUS_PROVISIONAL,
        }:
            return normalized

    provisional = getattr(event, "provisional_extraction", None)
    if isinstance(provisional, dict) and provisional:
        return EXTRACTION_STATUS_PROVISIONAL
    if _has_canonical_extraction(event):
        return EXTRACTION_STATUS_CANONICAL
    return EXTRACTION_STATUS_NONE


def capture_canonical_extraction(event: Event) -> CanonicalExtractionSnapshot:
    """Capture the current durable event extraction state."""
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else None
    provenance = (
        deepcopy(event.extraction_provenance)
        if isinstance(event.extraction_provenance, dict)
        else {}
    )
    return CanonicalExtractionSnapshot(
        event_summary=event.event_summary,
        extracted_who=list(event.extracted_who) if event.extracted_who is not None else None,
        extracted_what=event.extracted_what,
        extracted_where=event.extracted_where,
        extracted_when=event.extracted_when,
        extracted_claims=deepcopy(claims) if claims is not None else None,
        categories=list(event.categories) if event.categories is not None else None,
        has_contradictions=bool(event.has_contradictions),
        contradiction_notes=event.contradiction_notes,
        extraction_provenance=provenance,
    )


def snapshot_has_canonical_extraction(snapshot: CanonicalExtractionSnapshot) -> bool:
    """Return whether a captured snapshot contains durable canonical extraction state."""
    return bool(
        _nonblank(snapshot.event_summary)
        or snapshot.extracted_who
        or _nonblank(snapshot.extracted_what)
        or _nonblank(snapshot.extracted_where)
        or snapshot.extracted_when is not None
        or bool(snapshot.extracted_claims)
        or bool(snapshot.categories)
        or bool(snapshot.has_contradictions)
        or _nonblank(snapshot.contradiction_notes)
        or (
            isinstance(snapshot.extraction_provenance, dict)
            and snapshot.extraction_provenance.get("stage") == "tier2"
            and snapshot.extraction_provenance.get("status") != "replay_pending"
        )
    )


def demote_current_extraction_to_provisional(
    event: Event,
    *,
    canonical_snapshot: CanonicalExtractionSnapshot,
    policy: dict[str, Any] | None = None,
    replay_enqueued: bool = False,
) -> None:
    """Move the just-written extraction into provisional storage and restore canonical state."""
    prior_provisional = (
        dict(event.provisional_extraction) if isinstance(event.provisional_extraction, dict) else {}
    )
    captured_at = datetime.now(tz=UTC).isoformat()
    event.provisional_extraction = {
        "status": EXTRACTION_STATUS_PROVISIONAL,
        "captured_at": captured_at,
        "summary": event.event_summary,
        "extracted_who": list(event.extracted_who or []),
        "extracted_what": event.extracted_what,
        "extracted_where": event.extracted_where,
        "extracted_when": (
            event.extracted_when.astimezone(UTC).isoformat()
            if isinstance(event.extracted_when, datetime)
            else None
        ),
        "extracted_claims": (
            deepcopy(event.extracted_claims) if isinstance(event.extracted_claims, dict) else None
        ),
        "categories": list(event.categories or []),
        "has_contradictions": bool(event.has_contradictions),
        "contradiction_notes": event.contradiction_notes,
        "provenance": (
            deepcopy(event.extraction_provenance)
            if isinstance(event.extraction_provenance, dict)
            else {}
        ),
        "replay_enqueued": bool(replay_enqueued),
        "policy": deepcopy(policy) if isinstance(policy, dict) else None,
        "superseded_provisional": _superseded_provisional_metadata(prior_provisional),
    }
    restore_canonical_extraction(event, snapshot=canonical_snapshot)
    event.extraction_status = EXTRACTION_STATUS_PROVISIONAL


def promote_canonical_extraction(
    event: Event,
    *,
    extraction_provenance: dict[str, Any],
) -> None:
    """Persist canonical extraction state and clear any prior provisional payload."""
    provenance = deepcopy(extraction_provenance)
    prior_provisional = (
        dict(event.provisional_extraction) if isinstance(event.provisional_extraction, dict) else {}
    )
    if prior_provisional:
        provenance["promotion"] = {
            "source_status": EXTRACTION_STATUS_PROVISIONAL,
            "superseded_at": datetime.now(tz=UTC).isoformat(),
            "superseded_provisional": _superseded_provisional_metadata(prior_provisional),
        }
    event.extraction_provenance = provenance
    event.extraction_status = EXTRACTION_STATUS_CANONICAL
    event.provisional_extraction = {}


def clear_all_extraction_state(event: Event) -> None:
    """Clear both canonical and provisional extraction state."""
    clear_canonical_extraction_state(event)
    event.provisional_extraction = {}
    event.extraction_status = EXTRACTION_STATUS_NONE


def clear_canonical_extraction_state(event: Event) -> None:
    """Clear canonical extraction fields while preserving provisional payload."""
    event.event_summary = None
    event.extracted_claims = None
    event.extracted_who = None
    event.extracted_what = None
    event.extracted_where = None
    event.extracted_when = None
    event.categories = []
    event.has_contradictions = False
    event.contradiction_notes = None
    event.extraction_status = (
        EXTRACTION_STATUS_PROVISIONAL
        if provisional_extraction_payload(event) is not None
        else EXTRACTION_STATUS_NONE
    )


def provisional_extraction_payload(event: Event) -> dict[str, Any] | None:
    """Return the bounded provisional payload when one exists."""
    provisional = getattr(event, "provisional_extraction", None)
    if not isinstance(provisional, dict) or not provisional:
        return None
    return deepcopy(provisional)


def restore_canonical_extraction(
    event: Event,
    *,
    snapshot: CanonicalExtractionSnapshot,
) -> None:
    """Restore canonical extraction fields from a captured snapshot."""
    event.event_summary = snapshot.event_summary
    event.extracted_who = (
        list(snapshot.extracted_who) if snapshot.extracted_who is not None else None
    )
    event.extracted_what = snapshot.extracted_what
    event.extracted_where = snapshot.extracted_where
    event.extracted_when = snapshot.extracted_when
    event.extracted_claims = (
        deepcopy(snapshot.extracted_claims) if snapshot.extracted_claims is not None else None
    )
    event.categories = list(snapshot.categories) if snapshot.categories is not None else None
    event.has_contradictions = snapshot.has_contradictions
    event.contradiction_notes = snapshot.contradiction_notes
    event.extraction_provenance = deepcopy(snapshot.extraction_provenance)


def _has_canonical_extraction(event: Event) -> bool:
    return bool(
        _nonblank(event.event_summary)
        or event.extracted_who
        or _nonblank(event.extracted_what)
        or _nonblank(event.extracted_where)
        or event.extracted_when is not None
        or (isinstance(event.extracted_claims, dict) and bool(event.extracted_claims))
        or bool(event.categories)
        or bool(event.has_contradictions)
        or _nonblank(event.contradiction_notes)
        or (
            isinstance(event.extraction_provenance, dict)
            and event.extraction_provenance.get("stage") == "tier2"
            and event.extraction_provenance.get("status") != "replay_pending"
        )
    )


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _superseded_provisional_metadata(provisional: dict[str, Any]) -> dict[str, Any] | None:
    if not provisional:
        return None
    return {
        "captured_at": provisional.get("captured_at"),
        "provenance": provisional.get("provenance"),
        "replay_enqueued": provisional.get("replay_enqueued"),
    }
