"""Atomic event-link insertion with terminal-state protection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.event_cluster_health import apply_default_cluster_health
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, EventItem, RawItem

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ClusterResult:
    """Result of clustering one raw item."""

    item_id: UUID
    event_id: UUID
    created: bool
    merged: bool
    similarity: float | None = None


def _event_is_cluster_eligible(event: Event) -> bool:
    return (
        event.epistemic_state != EventEpistemicState.RETRACTED.value
        and event.activity_state != EventActivityState.CLOSED.value
    )


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
    if not _event_is_cluster_eligible(event):
        return None

    link = EventItem(event_id=event_id, item_id=item_id)
    try:
        async with session.begin_nested():
            session.add(link)
            await session.flush()
        return True
    except IntegrityError:
        return False


async def _locked_existing_event_link(
    *,
    session: AsyncSession,
    item_id: UUID,
) -> tuple[EventItem, Event] | None:
    query = (
        select(EventItem, Event)
        .join(Event, Event.id == EventItem.event_id)
        .where(EventItem.item_id == item_id)
        .with_for_update(of=(EventItem, Event))
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(query)).first()
    if row is None:
        return None
    return (row[0], row[1])


async def _finish_created_event(
    *,
    session: AsyncSession,
    event: Event,
    item: RawItem,
    refresh_event_provenance: Callable[[Event], Awaitable[None]],
) -> ClusterResult:
    await refresh_event_provenance(event)
    apply_default_cluster_health(event)
    await session.flush()
    return ClusterResult(item_id=item.id, event_id=event.id, created=True, merged=False)


async def create_linked_event(
    *,
    session: AsyncSession,
    item: RawItem,
    create_event: Callable[[RawItem], Awaitable[Event]],
    add_link: Callable[[UUID, UUID], Awaitable[bool | None]],
    refresh_event_provenance: Callable[[Event], Awaitable[None]],
) -> ClusterResult:
    """Create an event or resolve the winner of a concurrent link race."""
    event = await create_event(item)
    link_added = await add_link(event.id, item.id)
    if link_added is True:
        return await _finish_created_event(
            session=session,
            event=event,
            item=item,
            refresh_event_provenance=refresh_event_provenance,
        )

    locked_link = await _locked_existing_event_link(session=session, item_id=item.id)
    if locked_link is not None:
        _, existing_event = locked_link
        winner_eligible = _event_is_cluster_eligible(existing_event)
        await session.delete(event)
        await session.flush()
        logger.info(
            "Discarding unlinked event after concurrent item-link winner",
            item_id=str(item.id),
            discarded_event_id=str(event.id),
            existing_event_id=str(existing_event.id),
            winner_eligible=winner_eligible,
        )
        return ClusterResult(
            item_id=item.id,
            event_id=existing_event.id,
            created=False,
            merged=True,
        )

    retry_added = await add_link(event.id, item.id)
    if retry_added is True:
        return await _finish_created_event(
            session=session,
            event=event,
            item=item,
            refresh_event_provenance=refresh_event_provenance,
        )
    await session.delete(event)
    await session.flush()
    msg = f"Failed to link new event for item {item.id}"
    raise RuntimeError(msg)


async def resolve_event_link_failure(
    *,
    event: Event,
    item: RawItem,
    similarity: float,
    terminal: bool,
    create_linked_event: Callable[[RawItem], Awaitable[ClusterResult]],
    find_existing_event_id: Callable[[UUID], Awaitable[UUID | None]],
) -> ClusterResult:
    """Resolve a terminal rejection or an ordinary link conflict."""
    if terminal:
        return await create_linked_event(item)

    resolved_event_id = await find_existing_event_id(item.id)
    if resolved_event_id is not None and resolved_event_id != event.id:
        logger.info(
            "Item already linked to a different event; using existing linkage",
            item_id=str(item.id),
            requested_event_id=str(event.id),
            existing_event_id=str(resolved_event_id),
        )
        return ClusterResult(
            item_id=item.id,
            event_id=resolved_event_id,
            created=False,
            merged=True,
            similarity=similarity,
        )
    logger.info(
        "Skipping merge metadata update because item was already linked",
        event_id=str(event.id),
        item_id=str(item.id),
    )
    return ClusterResult(
        item_id=item.id,
        event_id=event.id,
        created=False,
        merged=True,
        similarity=similarity,
    )
