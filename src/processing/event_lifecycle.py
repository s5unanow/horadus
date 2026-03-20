"""
Event lifecycle transition management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.event_state import (
    EventActivityState,
    EventEpistemicState,
    apply_event_state_update,
    derived_epistemic_state,
    resolved_event_activity_state,
    resolved_event_epistemic_state,
    resolved_independent_evidence_count,
)
from src.storage.models import Event, EventLifecycle

FADING_HOURS = 48
ARCHIVE_DAYS = 7


class EventLifecycleManager:
    """Manage event lifecycle transitions based on source corroboration and recency."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def on_event_mention(
        self,
        event: Event,
        *,
        mentioned_at: datetime | None = None,
    ) -> bool:
        mention_time = mentioned_at or datetime.now(tz=UTC)
        previous_epistemic = resolved_event_epistemic_state(event)
        previous_activity = resolved_event_activity_state(event)
        event.last_mention_at = mention_time

        next_epistemic = previous_epistemic
        if previous_epistemic != EventEpistemicState.RETRACTED.value:
            next_epistemic = derived_epistemic_state(
                unique_source_count=resolved_independent_evidence_count(event),
                has_contradictions=bool(event.has_contradictions),
            )
        if next_epistemic in {
            EventEpistemicState.CONFIRMED.value,
            EventEpistemicState.CONTESTED.value,
        }:
            event.confirmed_at = event.confirmed_at or mention_time
        apply_event_state_update(
            event,
            epistemic_state=next_epistemic,
            activity_state=EventActivityState.ACTIVE.value,
        )

        return (
            previous_epistemic != event.epistemic_state or previous_activity != event.activity_state
        )

    async def run_decay_check(self, *, now: datetime | None = None) -> dict[str, Any]:
        as_of = now or datetime.now(tz=UTC)
        fading_threshold = as_of - timedelta(hours=FADING_HOURS)
        archive_threshold = as_of - timedelta(days=ARCHIVE_DAYS)

        confirmed_to_fading_result = await self.session.execute(
            update(Event)
            .where(Event.activity_state == EventActivityState.ACTIVE.value)
            .where(Event.last_mention_at < fading_threshold)
            .values(
                activity_state=EventActivityState.DORMANT.value,
                lifecycle_status=EventLifecycle.FADING.value,
            )
            .returning(Event.id)
        )
        fading_to_archived_result = await self.session.execute(
            update(Event)
            .where(Event.activity_state == EventActivityState.DORMANT.value)
            .where(Event.last_mention_at < archive_threshold)
            .values(
                activity_state=EventActivityState.CLOSED.value,
                lifecycle_status=EventLifecycle.ARCHIVED.value,
            )
            .returning(Event.id)
        )

        confirmed_to_fading = len(list(confirmed_to_fading_result.all()))
        fading_to_archived = len(list(fading_to_archived_result.all()))
        return {
            "task": "check_event_lifecycles",
            "as_of": as_of.isoformat(),
            "activity_active_to_dormant": confirmed_to_fading,
            "activity_dormant_to_closed": fading_to_archived,
            "confirmed_to_fading": confirmed_to_fading,
            "fading_to_archived": fading_to_archived,
        }
