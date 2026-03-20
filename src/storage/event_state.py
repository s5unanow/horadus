"""Event epistemic/activity state contracts and legacy compatibility helpers."""

from __future__ import annotations

import enum
from typing import Any

CONFIRMATION_THRESHOLD = 3


class EventEpistemicState(enum.StrEnum):
    """How well-supported or refuted an event currently is."""

    EMERGING = "emerging"
    CONFIRMED = "confirmed"
    CONTESTED = "contested"
    RETRACTED = "retracted"


class EventActivityState(enum.StrEnum):
    """How recently active the event cluster currently is."""

    ACTIVE = "active"
    DORMANT = "dormant"
    CLOSED = "closed"


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """Persist enum values rather than enum member names."""

    return [str(member.value) for member in enum_class]


def sql_string_literals(values: tuple[str, ...]) -> str:
    """Render enum values as SQL string literals."""

    return ", ".join(f"'{value}'" for value in values)


EVENT_EPISTEMIC_STATE_VALUES = tuple(enum_values(EventEpistemicState))
EVENT_ACTIVITY_STATE_VALUES = tuple(enum_values(EventActivityState))

EVENT_EPISTEMIC_STATE_SQL_VALUES = sql_string_literals(EVENT_EPISTEMIC_STATE_VALUES)
EVENT_ACTIVITY_STATE_SQL_VALUES = sql_string_literals(EVENT_ACTIVITY_STATE_VALUES)


def legacy_lifecycle_status_for_states(*, epistemic_state: str, activity_state: str) -> str:
    """Project split states onto the deprecated legacy lifecycle field."""

    if epistemic_state == EventEpistemicState.RETRACTED.value:
        return "archived"
    if activity_state == EventActivityState.CLOSED.value:
        return "archived"
    if activity_state == EventActivityState.DORMANT.value:
        return "fading"
    if epistemic_state == EventEpistemicState.EMERGING.value:
        return "emerging"
    return "confirmed"


def epistemic_state_from_legacy(*, lifecycle_status: str | None, has_contradictions: bool) -> str:
    """Backfill or resolve epistemic state when only legacy fields are populated."""

    normalized = (lifecycle_status or "").strip().lower()
    if has_contradictions:
        return EventEpistemicState.CONTESTED.value
    if normalized == EventEpistemicState.EMERGING.value:
        return EventEpistemicState.EMERGING.value
    return EventEpistemicState.CONFIRMED.value


def activity_state_from_legacy(*, lifecycle_status: str | None) -> str:
    """Backfill or resolve activity state from the legacy lifecycle field."""

    normalized = (lifecycle_status or "").strip().lower()
    if normalized == "archived":
        return EventActivityState.CLOSED.value
    if normalized == "fading":
        return EventActivityState.DORMANT.value
    return EventActivityState.ACTIVE.value


def resolved_event_epistemic_state(event: Any) -> str:
    """Return the event epistemic state with legacy fallback for in-memory objects."""

    explicit = getattr(event, "epistemic_state", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return epistemic_state_from_legacy(
        lifecycle_status=getattr(event, "lifecycle_status", None),
        has_contradictions=bool(getattr(event, "has_contradictions", False)),
    )


def resolved_event_activity_state(event: Any) -> str:
    """Return the event activity state with legacy fallback for in-memory objects."""

    explicit = getattr(event, "activity_state", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return activity_state_from_legacy(lifecycle_status=getattr(event, "lifecycle_status", None))


def derived_epistemic_state(*, unique_source_count: int | None, has_contradictions: bool) -> str:
    """Derive the non-retracted epistemic state from corroboration/contradiction signals."""

    if has_contradictions:
        return EventEpistemicState.CONTESTED.value
    if int(unique_source_count or 0) >= CONFIRMATION_THRESHOLD:
        return EventEpistemicState.CONFIRMED.value
    return EventEpistemicState.EMERGING.value


def apply_event_state_update(
    event: Any,
    *,
    epistemic_state: str | None = None,
    activity_state: str | None = None,
) -> None:
    """Apply split states and keep the deprecated lifecycle projection synchronized."""

    next_epistemic = epistemic_state or resolved_event_epistemic_state(event)
    next_activity = activity_state or resolved_event_activity_state(event)
    event.epistemic_state = next_epistemic
    event.activity_state = next_activity
    event.lifecycle_status = legacy_lifecycle_status_for_states(
        epistemic_state=next_epistemic,
        activity_state=next_activity,
    )


def event_state_snapshot(event: Any) -> dict[str, str]:
    """Serialize the current event state axes plus legacy compatibility state."""

    epistemic_state = resolved_event_epistemic_state(event)
    activity_state = resolved_event_activity_state(event)
    return {
        "epistemic_state": epistemic_state,
        "activity_state": activity_state,
        "lifecycle_status": legacy_lifecycle_status_for_states(
            epistemic_state=epistemic_state,
            activity_state=activity_state,
        ),
    }
