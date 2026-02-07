"""
Event lifecycle transition management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Event, EventLifecycle

CONFIRMATION_THRESHOLD = 3
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
        previous = event.lifecycle_status
        event.last_mention_at = mention_time

        if event.lifecycle_status == EventLifecycle.EMERGING.value:
            if event.unique_source_count >= CONFIRMATION_THRESHOLD:
                event.lifecycle_status = EventLifecycle.CONFIRMED.value
                event.confirmed_at = event.confirmed_at or mention_time
        elif event.lifecycle_status in {EventLifecycle.FADING.value, EventLifecycle.ARCHIVED.value}:
            event.lifecycle_status = EventLifecycle.CONFIRMED.value
            event.confirmed_at = event.confirmed_at or mention_time

        return previous != event.lifecycle_status

    async def run_decay_check(self, *, now: datetime | None = None) -> dict[str, Any]:
        as_of = now or datetime.now(tz=UTC)
        fading_threshold = as_of - timedelta(hours=FADING_HOURS)
        archive_threshold = as_of - timedelta(days=ARCHIVE_DAYS)

        confirmed_to_fading_result = await self.session.execute(
            update(Event)
            .where(Event.lifecycle_status == EventLifecycle.CONFIRMED.value)
            .where(Event.last_mention_at < fading_threshold)
            .values(lifecycle_status=EventLifecycle.FADING.value)
            .returning(Event.id)
        )
        fading_to_archived_result = await self.session.execute(
            update(Event)
            .where(Event.lifecycle_status == EventLifecycle.FADING.value)
            .where(Event.last_mention_at < archive_threshold)
            .values(lifecycle_status=EventLifecycle.ARCHIVED.value)
            .returning(Event.id)
        )

        confirmed_to_fading = len(list(confirmed_to_fading_result.all()))
        fading_to_archived = len(list(fading_to_archived_result.all()))
        return {
            "task": "check_event_lifecycles",
            "as_of": as_of.isoformat(),
            "confirmed_to_fading": confirmed_to_fading,
            "fading_to_archived": fading_to_archived,
        }
