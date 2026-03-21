"""Replay queue helpers shared by event lineage repair flows."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.event_lineage_models import EventLineage
from src.storage.models import Event, LLMReplayQueueItem

REPLAY_STAGE = "tier2"


async def enqueue_event_replay(
    *,
    session: AsyncSession,
    event_id: UUID,
    reason: str,
) -> UUID | None:
    event = await session.get(Event, event_id)
    if event is None:
        return None
    details = {
        "reason": "event_lineage_repair",
        "repair_kind": reason,
        "original_extraction_provenance": replay_source_provenance(event),
    }
    replay_queue_item_id = await reset_replay_queue_item_if_idle(
        session=session,
        event_id=event_id,
        details=details,
    )
    if replay_queue_item_id is not None:
        return replay_queue_item_id
    try:
        async with session.begin_nested():
            queue_item = LLMReplayQueueItem(
                stage=REPLAY_STAGE,
                event_id=event_id,
                priority=500,
                details=details,
            )
            session.add(queue_item)
            await session.flush()
        queue_item_id = queue_item.id or cast(
            "UUID | None",
            await session.scalar(
                select(LLMReplayQueueItem.id)
                .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
                .where(LLMReplayQueueItem.event_id == event_id)
                .limit(1)
            ),
        )
        assert queue_item_id is not None
        return queue_item_id
    except IntegrityError:
        return await reset_replay_queue_item_if_idle(
            session=session,
            event_id=event_id,
            details=details,
        )


async def reset_replay_queue_item_if_idle(
    *,
    session: AsyncSession,
    event_id: UUID,
    details: dict[str, Any],
) -> UUID | None:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(LLMReplayQueueItem)
            .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
            .where(LLMReplayQueueItem.event_id == event_id)
            .where(LLMReplayQueueItem.status != "processing")
            .values(
                priority=500,
                status="pending",
                locked_at=None,
                locked_by=None,
                processed_at=None,
                last_error=None,
                details=details,
            )
            .execution_options(synchronize_session="fetch")
        ),
    )
    if not result.rowcount:
        return None
    return cast(
        "UUID | None",
        await session.scalar(
            select(LLMReplayQueueItem.id)
            .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
            .where(LLMReplayQueueItem.event_id == event_id)
            .limit(1)
        ),
    )


async def delete_event_replay_queue_items(*, session: AsyncSession, event_id: UUID) -> None:
    deleted_queue_item_ids = tuple(
        (
            await session.scalars(
                select(LLMReplayQueueItem.id)
                .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
                .where(LLMReplayQueueItem.event_id == event_id)
                .where(LLMReplayQueueItem.status != "processing")
            )
        ).all()
    )
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(LLMReplayQueueItem)
            .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
            .where(LLMReplayQueueItem.event_id == event_id)
            .where(LLMReplayQueueItem.status != "processing")
        ),
    )
    if result.rowcount:
        await mark_lineages_superseded_for_queue_items(
            session=session,
            queue_item_ids=deleted_queue_item_ids,
        )
        return
    processing_item_id = await session.scalar(
        select(LLMReplayQueueItem.id)
        .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
        .where(LLMReplayQueueItem.event_id == event_id)
        .where(LLMReplayQueueItem.status == "processing")
        .limit(1)
    )
    if processing_item_id is not None:
        raise RuntimeError("cannot merge event while source replay is processing")


async def mark_lineages_superseded_for_queue_items(
    *,
    session: AsyncSession,
    queue_item_ids: tuple[UUID, ...],
) -> None:
    if not queue_item_ids:
        return
    queue_item_id_strings = {str(queue_item_id) for queue_item_id in queue_item_ids}
    lineages = list((await session.scalars(select(EventLineage))).all())
    for lineage in lineages:
        lineage_queue_item_ids = {
            str(value) for value in (lineage.details or {}).get("replay_queue_item_ids", [])
        }
        if not lineage_queue_item_ids.intersection(queue_item_id_strings):
            continue
        details = dict(lineage.details or {})
        details["status"] = "replay_superseded"
        lineage.details = details


def clear_stale_event_extractions(event: Event) -> None:
    event.extracted_claims = None
    event.extracted_who = None
    event.extracted_what = None
    event.extracted_where = None
    event.extracted_when = None
    event.categories = []
    event.has_contradictions = False
    event.contradiction_notes = None


def replay_source_provenance(event: Event) -> dict[str, Any]:
    provenance = dict(event.extraction_provenance or {})
    original = provenance.get("original_extraction_provenance")
    if isinstance(original, dict):
        return dict(original)
    return provenance
