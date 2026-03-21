"""Replay queue helpers shared by event lineage repair flows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID, uuid4

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
    replay_request_id = uuid4()
    superseded_request_ids = await _load_idle_replay_request_ids(session=session, event_id=event_id)
    details = {
        "reason": "event_lineage_repair",
        "repair_kind": reason,
        "replay_request_id": str(replay_request_id),
        "original_extraction_provenance": replay_source_provenance(event),
    }
    if await reset_replay_queue_item_if_idle(
        session=session,
        event_id=event_id,
        details=details,
    ):
        await mark_lineages_superseded_for_replay_requests(
            session=session,
            replay_request_ids=superseded_request_ids,
        )
        return replay_request_id
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
        return replay_request_id
    except IntegrityError:
        if await reset_replay_queue_item_if_idle(
            session=session,
            event_id=event_id,
            details=details,
        ):
            await mark_lineages_superseded_for_replay_requests(
                session=session,
                replay_request_ids=superseded_request_ids,
            )
            return replay_request_id
        return None


async def reset_replay_queue_item_if_idle(
    *,
    session: AsyncSession,
    event_id: UUID,
    details: dict[str, Any],
) -> bool:
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
    return bool(result.rowcount)


async def delete_event_replay_queue_items(*, session: AsyncSession, event_id: UUID) -> None:
    deleted_replay_request_ids = _extract_replay_request_ids(
        (
            await session.scalars(
                select(LLMReplayQueueItem.details)
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
        await mark_lineages_superseded_for_replay_requests(
            session=session,
            replay_request_ids=deleted_replay_request_ids,
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


async def mark_lineages_superseded_for_replay_requests(
    *,
    session: AsyncSession,
    replay_request_ids: tuple[UUID, ...],
) -> None:
    if not replay_request_ids:
        return
    replay_request_id_strings = {str(replay_request_id) for replay_request_id in replay_request_ids}
    lineages = list((await session.scalars(select(EventLineage))).all())
    for lineage in lineages:
        lineage_replay_request_ids = {
            str(value) for value in (lineage.details or {}).get("replay_request_ids", [])
        }
        if not lineage_replay_request_ids.intersection(replay_request_id_strings):
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


def _extract_replay_request_ids(queue_item_details: Sequence[Any]) -> tuple[UUID, ...]:
    replay_request_ids: list[UUID] = []
    for details in queue_item_details:
        value = details.get("replay_request_id") if isinstance(details, dict) else None
        try:
            replay_request_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return tuple(replay_request_ids)


async def _load_idle_replay_request_ids(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> tuple[UUID, ...]:
    return _extract_replay_request_ids(
        (
            await session.scalars(
                select(LLMReplayQueueItem.details)
                .where(LLMReplayQueueItem.stage == REPLAY_STAGE)
                .where(LLMReplayQueueItem.event_id == event_id)
                .where(LLMReplayQueueItem.status != "processing")
            )
        ).all()
    )
