"""Atomic event-link insertion with terminal-state protection."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, EventItem


async def add_event_link(
    *,
    session: AsyncSession,
    event_id: UUID,
    item_id: UUID,
) -> bool | None:
    """Add a link, returning ``None`` when the locked event is terminal."""
    event = await session.get(Event, event_id, with_for_update=True)
    if event is None:
        return False

    await session.refresh(
        event,
        attribute_names=["epistemic_state", "activity_state"],
        with_for_update=True,
    )
    if (
        event.epistemic_state == EventEpistemicState.RETRACTED.value
        or event.activity_state == EventActivityState.CLOSED.value
    ):
        return None

    link = EventItem(event_id=event_id, item_id=item_id)
    try:
        async with session.begin_nested():
            session.add(link)
            await session.flush()
        return True
    except IntegrityError:
        return False
