"""Event split/merge repair helpers with lineage and replay safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.source_credibility import DEFAULT_SOURCE_CREDIBILITY, source_multiplier_expression
from src.core.trend_engine import TrendEngine
from src.core.trend_restatement import (
    apply_compensating_restatement,
    remaining_evidence_delta,
    restatement_compensation_totals_by_evidence_id,
)
from src.processing.corroboration_provenance import refresh_event_provenance
from src.processing.event_claims import deactivate_event_claims
from src.processing.event_cluster_health import (
    apply_default_cluster_health,
    apply_repaired_cluster_health,
)
from src.processing.event_lifecycle import ARCHIVE_DAYS, FADING_HOURS, EventLifecycleManager
from src.processing.event_lineage_replay import (
    clear_stale_event_extractions as _clear_stale_event_extractions,
)
from src.processing.event_lineage_replay import (
    delete_event_replay_queue_items as _delete_event_replay_queue_items,
)
from src.processing.event_lineage_replay import (
    enqueue_event_replay as _enqueue_event_replay,
)
from src.storage.event_extraction import clear_all_extraction_state
from src.storage.event_lineage_models import EventLineage
from src.storage.event_state import (
    EventActivityState,
    EventEpistemicState,
    apply_event_state_update,
)
from src.storage.event_summary import (
    refresh_event_summary_from_canonical,
    resolved_event_summary,
)
from src.storage.models import (
    Event,
    EventItem,
    RawItem,
    Source,
    Trend,
    TrendEvidence,
)


@dataclass(frozen=True, slots=True)
class EventRepairResult:
    """Summary of one lineage repair operation."""

    action: str
    lineage_id: UUID
    source_event_id: UUID
    target_event_id: UUID
    created_event_id: UUID | None
    moved_item_ids: tuple[UUID, ...]
    invalidated_evidence_ids: tuple[UUID, ...]
    replay_enqueued_event_ids: tuple[UUID, ...]


async def split_event(
    *,
    session: AsyncSession,
    source_event: Event,
    item_ids: list[UUID],
    notes: str | None,
    created_by: str | None,
) -> EventRepairResult:
    """Split a subset of raw items from one event into a new event."""

    source_event_id = _require_event_id(source_event)
    await _lock_event_for_lineage_change(session=session, event_id=source_event_id)
    source_rows = await _load_event_item_rows(session=session, event_id=source_event_id)
    requested_item_ids = tuple(dict.fromkeys(item_ids))
    current_item_ids = {row.item.id for row in source_rows}
    if any(item_id not in current_item_ids for item_id in requested_item_ids):
        raise ValueError("split item_ids must all belong to the source event")
    selected_rows = [row for row in source_rows if row.item.id in set(requested_item_ids)]
    if not selected_rows:
        raise ValueError("split requires at least one current event item")
    if len(selected_rows) >= len(source_rows):
        raise ValueError("split must leave at least one item on the source event")

    new_event = await _build_event_from_rows(session=session, rows=selected_rows)
    moved_item_ids = tuple(row.item.id for row in selected_rows)
    for row in selected_rows:
        row.link.event_id = _require_event_id(new_event)
    await session.flush()

    await _refresh_event_after_item_change(session=session, event=source_event)
    await _refresh_event_after_item_change(session=session, event=new_event)
    (
        invalidated_evidence_ids,
        replay_enqueued_event_ids,
        replay_request_ids,
    ) = await _repair_affected_events(
        session=session,
        events=[source_event, new_event],
        reason="split",
    )
    lineage = EventLineage(
        lineage_kind="split",
        source_event_id=source_event_id,
        target_event_id=_require_event_id(new_event),
        created_by=created_by,
        notes=notes,
        details={
            "moved_item_ids": [str(item_id) for item_id in moved_item_ids],
            "moved_item_count": len(moved_item_ids),
            "invalidated_evidence_ids": [
                str(evidence_id) for evidence_id in invalidated_evidence_ids
            ],
            "replay_enqueued_event_ids": [str(event_id) for event_id in replay_enqueued_event_ids],
            "replay_request_ids": [
                str(replay_request_id) for replay_request_id in replay_request_ids
            ],
            "status": "replay_pending",
        },
    )
    session.add(lineage)
    await session.flush()
    assert lineage.id is not None
    return EventRepairResult(
        action="split",
        lineage_id=lineage.id,
        source_event_id=source_event_id,
        target_event_id=_require_event_id(new_event),
        created_event_id=_require_event_id(new_event),
        moved_item_ids=moved_item_ids,
        invalidated_evidence_ids=invalidated_evidence_ids,
        replay_enqueued_event_ids=replay_enqueued_event_ids,
    )


async def merge_events(
    *,
    session: AsyncSession,
    source_event: Event,
    target_event: Event,
    notes: str | None,
    created_by: str | None,
) -> EventRepairResult:
    """Merge one event's raw items into another event."""

    source_event_id = _require_event_id(source_event)
    target_event_id = _require_event_id(target_event)
    if source_event_id == target_event_id:
        raise ValueError("merge source and target events must differ")
    if (
        target_event.source_count == 0
        and target_event.activity_state == EventActivityState.CLOSED.value
    ):
        raise ValueError("merge target event cannot be an empty closed stub")

    await _lock_event_for_lineage_change(session=session, event_id=source_event_id)
    source_rows = await _load_event_item_rows(session=session, event_id=source_event_id)
    if not source_rows:
        raise ValueError("merge source event has no linked items")
    await _delete_event_replay_queue_items(session=session, event_id=source_event_id)
    moved_item_ids = tuple(row.item.id for row in source_rows)
    for row in source_rows:
        row.link.event_id = target_event_id
    await session.flush()

    await _refresh_event_after_item_change(session=session, event=target_event)
    await _close_empty_merged_event(source_event, replay_pending=False)
    await _mark_event_claims_stale(session=session, event_id=source_event_id)
    (
        invalidated_evidence_ids,
        replay_enqueued_event_ids,
        replay_request_ids,
    ) = await _repair_affected_events(
        session=session,
        events=[source_event, target_event],
        replay_event_ids=(target_event_id,),
        reason="merge",
    )
    lineage = EventLineage(
        lineage_kind="merge",
        source_event_id=source_event_id,
        target_event_id=target_event_id,
        created_by=created_by,
        notes=notes,
        details={
            "moved_item_ids": [str(item_id) for item_id in moved_item_ids],
            "moved_item_count": len(moved_item_ids),
            "invalidated_evidence_ids": [
                str(evidence_id) for evidence_id in invalidated_evidence_ids
            ],
            "replay_enqueued_event_ids": [str(event_id) for event_id in replay_enqueued_event_ids],
            "replay_request_ids": [
                str(replay_request_id) for replay_request_id in replay_request_ids
            ],
            "status": "replay_pending",
        },
    )
    session.add(lineage)
    await session.flush()
    assert lineage.id is not None
    return EventRepairResult(
        action="merge",
        lineage_id=lineage.id,
        source_event_id=source_event_id,
        target_event_id=target_event_id,
        created_event_id=None,
        moved_item_ids=moved_item_ids,
        invalidated_evidence_ids=invalidated_evidence_ids,
        replay_enqueued_event_ids=replay_enqueued_event_ids,
    )


async def load_event_lineage(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> list[dict[str, Any]]:
    """Return normalized lineage payloads for one event."""

    rows = list(
        (
            await session.scalars(
                select(EventLineage)
                .where(
                    (EventLineage.source_event_id == event_id)
                    | (EventLineage.target_event_id == event_id)
                )
                .order_by(EventLineage.created_at.desc(), EventLineage.id.desc())
            )
        ).all()
    )
    counterpart_ids = {
        lineage.target_event_id
        for lineage in rows
        if lineage.source_event_id == event_id and lineage.target_event_id is not None
    }
    counterpart_ids.update(
        lineage.source_event_id
        for lineage in rows
        if lineage.target_event_id == event_id and lineage.source_event_id is not None
    )
    counterparts = {
        event.id: event
        for event in (
            await session.scalars(select(Event).where(Event.id.in_(tuple(counterpart_ids or ()))))
        ).all()
        if event.id is not None
    }
    payloads: list[dict[str, Any]] = []
    for lineage in rows:
        role = "source" if lineage.source_event_id == event_id else "target"
        counterpart_id = lineage.target_event_id if role == "source" else lineage.source_event_id
        counterpart = counterparts.get(counterpart_id) if counterpart_id is not None else None
        details = dict(lineage.details or {})
        payloads.append(
            {
                "id": lineage.id,
                "lineage_kind": lineage.lineage_kind,
                "role": role,
                "counterpart_event_id": counterpart_id,
                "counterpart_summary": (
                    resolved_event_summary(counterpart) if counterpart is not None else None
                ),
                "moved_item_count": int(details.get("moved_item_count", 0) or 0),
                "moved_item_ids": list(details.get("moved_item_ids", [])),
                "invalidated_evidence_ids": list(details.get("invalidated_evidence_ids", [])),
                "replay_enqueued_event_ids": list(details.get("replay_enqueued_event_ids", [])),
                "status": details.get("status", "recorded"),
                "created_by": lineage.created_by,
                "notes": lineage.notes,
                "created_at": lineage.created_at,
            }
        )
    return payloads


@dataclass(slots=True)
class _EventItemRow:
    link: EventItem
    item: RawItem


async def _lock_event_for_lineage_change(*, session: AsyncSession, event_id: UUID) -> None:
    await session.get(Event, event_id, with_for_update=True)


async def _load_event_item_rows(
    *,
    session: AsyncSession,
    event_id: UUID,
) -> list[_EventItemRow]:
    rows = (
        await session.execute(
            select(EventItem, RawItem)
            .join(RawItem, RawItem.id == EventItem.item_id)
            .where(EventItem.event_id == event_id)
            .order_by(RawItem.published_at.asc().nullslast(), RawItem.fetched_at.asc().nullslast())
            .with_for_update(of=EventItem)
        )
    ).all()
    return [_EventItemRow(link=row[0], item=row[1]) for row in rows]


async def _build_event_from_rows(
    *,
    session: AsyncSession,
    rows: list[_EventItemRow],
) -> Event:
    primary_item = await _pick_primary_item(
        session=session, item_ids=tuple(row.item.id for row in rows)
    )
    timestamp = _item_timestamp(primary_item)
    event = Event(
        canonical_summary=_build_canonical_summary(primary_item),
        event_summary=_build_canonical_summary(primary_item),
        embedding=primary_item.embedding,
        embedding_model=primary_item.embedding_model,
        embedding_generated_at=primary_item.embedding_generated_at,
        embedding_input_tokens=primary_item.embedding_input_tokens,
        embedding_retained_tokens=primary_item.embedding_retained_tokens,
        embedding_was_truncated=bool(primary_item.embedding_was_truncated),
        embedding_truncation_strategy=primary_item.embedding_truncation_strategy,
        source_count=len(rows),
        unique_source_count=len({row.item.source_id for row in rows}),
        first_seen_at=timestamp,
        last_mention_at=max(_item_timestamp(row.item) for row in rows),
        primary_item_id=primary_item.id,
    )
    session.add(event)
    await session.flush()
    apply_default_cluster_health(event)
    return event


async def _refresh_event_after_item_change(*, session: AsyncSession, event: Event) -> None:
    event_id = _require_event_id(event)
    rows = await _load_event_item_rows(session=session, event_id=event_id)
    if not rows:
        await _close_empty_merged_event(event)
        return
    primary_item = await _pick_primary_item(
        session=session,
        item_ids=tuple(row.item.id for row in rows),
        current_primary_item_id=event.primary_item_id,
    )
    event.source_count = len(rows)
    event.unique_source_count = len({row.item.source_id for row in rows})
    previous_canonical_summary = event.canonical_summary
    event.primary_item_id = primary_item.id
    event.canonical_summary = _build_canonical_summary(primary_item)
    refresh_event_summary_from_canonical(
        event,
        previous_canonical_summary=previous_canonical_summary,
    )
    event.embedding = primary_item.embedding
    event.embedding_model = primary_item.embedding_model
    event.embedding_generated_at = primary_item.embedding_generated_at
    event.embedding_input_tokens = primary_item.embedding_input_tokens
    event.embedding_retained_tokens = primary_item.embedding_retained_tokens
    event.embedding_was_truncated = bool(primary_item.embedding_was_truncated)
    event.embedding_truncation_strategy = primary_item.embedding_truncation_strategy
    event.first_seen_at = min(_item_timestamp(row.item) for row in rows)
    event.last_mention_at = max(_item_timestamp(row.item) for row in rows)
    await refresh_event_provenance(session=session, event=event)
    apply_repaired_cluster_health(
        event,
        item_embeddings=[
            row.item.embedding
            for row in rows
            if event.embedding_model is None
            or row.item.embedding_model is None
            or row.item.embedding_model == event.embedding_model
        ],
    )
    _clear_stale_event_extractions(event)
    if event.epistemic_state == EventEpistemicState.RETRACTED.value:
        event.epistemic_state = EventEpistemicState.EMERGING.value
    EventLifecycleManager(session).sync_event_state(
        event,
        confirmed_at=event.last_mention_at,
        activity_state=_repaired_event_activity_state(event),
    )
    await _mark_event_replay_pending(event=event, reason="event_lineage_repair")
    await _mark_event_claims_stale(session=session, event_id=event_id)


def _repaired_event_activity_state(event: Event) -> str:
    last_mention_at = event.last_mention_at
    if last_mention_at is None:
        return EventActivityState.ACTIVE.value
    now = datetime.now(tz=UTC)
    if last_mention_at <= now - timedelta(days=ARCHIVE_DAYS):
        return EventActivityState.CLOSED.value
    if last_mention_at <= now - timedelta(hours=FADING_HOURS):
        return EventActivityState.DORMANT.value
    return EventActivityState.ACTIVE.value


async def _close_empty_merged_event(event: Event, *, replay_pending: bool = True) -> None:
    prior_extraction_provenance = dict(event.extraction_provenance or {})
    event.source_count = 0
    event.unique_source_count = 0
    event.independent_evidence_count = 0
    event.corroboration_score = 0.0
    event.corroboration_mode = "fallback"
    event.embedding = None
    event.embedding_model = None
    event.embedding_generated_at = None
    event.embedding_input_tokens = None
    event.embedding_retained_tokens = None
    event.embedding_was_truncated = False
    event.embedding_truncation_strategy = None
    apply_event_state_update(
        event,
        epistemic_state=EventEpistemicState.EMERGING.value,
        activity_state=EventActivityState.CLOSED.value,
    )
    if replay_pending:
        await _mark_event_replay_pending(event=event, reason="event_lineage_repair")
    else:
        clear_all_extraction_state(event)
        event.extraction_provenance = {
            "status": "closed",
            "reason": "event_lineage_repair",
            "original_extraction_provenance": prior_extraction_provenance,
        }
    apply_default_cluster_health(event)
    event.provenance_summary = {
        "method": "fallback",
        "reason": "lineage_repair_empty_cluster",
        "raw_source_count": 0,
        "unique_source_count": 0,
        "independent_evidence_count": 0,
        "weighted_corroboration_score": 0.0,
        "groups": [],
        "cluster_health": {"cluster_cohesion_score": 1.0, "split_risk_score": 0.0},
    }
    event.extracted_claims = None
    event.extracted_who = None
    event.extracted_what = None
    event.extracted_where = None
    event.extracted_when = None
    event.categories = None
    event.has_contradictions = False
    event.contradiction_notes = None


async def _repair_affected_events(
    *,
    session: AsyncSession,
    events: list[Event],
    reason: str,
    replay_event_ids: tuple[UUID, ...] | None = None,
) -> tuple[tuple[UUID, ...], tuple[UUID, ...], tuple[UUID, ...]]:
    event_ids = tuple(event.id for event in events if event.id is not None)
    if not event_ids:
        return ((), (), ())
    evidence_rows = list(
        (await session.scalars(select_from_active_evidence(event_ids=event_ids))).all()
    )
    prior_compensation_by_evidence_id = await _load_prior_compensation_by_evidence_id(
        session=session,
        evidences=evidence_rows,
    )
    trend_by_id = await _load_trends_for_evidence(
        session=session,
        trend_ids={evidence.trend_id for evidence in evidence_rows},
    )
    trend_engine = TrendEngine(session=session)
    recorded_at = datetime.now(tz=UTC)
    invalidated_evidence_ids: list[UUID] = []
    for evidence in evidence_rows:
        evidence.is_invalidated = True
        evidence.invalidated_at = recorded_at
        trend = trend_by_id.get(evidence.trend_id)
        if trend is None:
            continue
        await apply_compensating_restatement(
            trend_engine=trend_engine,
            trend=trend,
            compensation_delta_log_odds=_invalidation_compensation_delta(
                evidence=evidence,
                prior_compensation_by_evidence_id=prior_compensation_by_evidence_id,
            ),
            restatement_kind="reclassification",
            source="tier2_reconciliation",
            recorded_at=recorded_at,
            trend_evidence=evidence,
            original_evidence_delta_log_odds=float(evidence.delta_log_odds),
            notes=f"Event lineage repair {reason}",
            details={"event_action": reason, "policy": "lineage_repair_replay"},
        )
        if evidence.id is not None:
            invalidated_evidence_ids.append(evidence.id)
    replay_targets = replay_event_ids or tuple(
        event_id for event_id in event_ids if event_id is not None
    )
    enqueued_ids: list[UUID] = []
    replay_request_ids: list[UUID] = []
    for event_id in replay_targets:
        replay_request_id = await _enqueue_event_replay(
            session=session,
            event_id=event_id,
            reason=reason,
        )
        if replay_request_id is not None:
            enqueued_ids.append(event_id)
            replay_request_ids.append(replay_request_id)
    if len(enqueued_ids) != len(replay_targets):
        raise RuntimeError("event lineage repair requires replay queue items for all targets")
    return (
        tuple(invalidated_evidence_ids),
        tuple(enqueued_ids),
        tuple(replay_request_ids),
    )


def select_from_active_evidence(*, event_ids: tuple[UUID, ...]) -> Any:
    return (
        select(TrendEvidence)
        .where(TrendEvidence.event_id.in_(event_ids))
        .where(TrendEvidence.is_invalidated.is_(False))
        .order_by(TrendEvidence.created_at.asc(), TrendEvidence.id.asc())
    )


async def _load_trends_for_evidence(
    *,
    session: AsyncSession,
    trend_ids: set[UUID],
) -> dict[UUID, Trend]:
    if not trend_ids:
        return {}
    trends = list(
        (await session.scalars(select(Trend).where(Trend.id.in_(tuple(trend_ids))))).all()
    )
    return {trend.id: trend for trend in trends if trend.id is not None}


async def _load_prior_compensation_by_evidence_id(
    *,
    session: AsyncSession,
    evidences: list[TrendEvidence],
) -> dict[UUID, float]:
    evidence_ids = tuple(evidence.id for evidence in evidences if evidence.id is not None)
    return await restatement_compensation_totals_by_evidence_id(
        session=session,
        evidence_ids=evidence_ids,
    )


def _invalidation_compensation_delta(
    *,
    evidence: TrendEvidence,
    prior_compensation_by_evidence_id: dict[UUID, float],
) -> float:
    prior_compensation_delta = (
        prior_compensation_by_evidence_id.get(evidence.id, 0.0) if evidence.id is not None else 0.0
    )
    return -remaining_evidence_delta(
        evidence=evidence,
        prior_compensation_delta=prior_compensation_delta,
    )


async def _mark_event_claims_stale(*, session: AsyncSession, event_id: UUID) -> None:
    await deactivate_event_claims(session=session, event_id=event_id)


async def _mark_event_replay_pending(*, event: Event, reason: str) -> None:
    prior = dict(event.extraction_provenance or {})
    _clear_stale_event_extractions(event)
    event.extraction_provenance = {
        "status": "replay_pending",
        "stage": "tier2",
        "reason": reason,
        "original_extraction_provenance": prior,
    }


async def _pick_primary_item(
    *,
    session: AsyncSession,
    item_ids: tuple[UUID, ...],
    current_primary_item_id: UUID | None = None,
) -> RawItem:
    if not item_ids:
        raise ValueError("event repair requires at least one item")
    credibility_order = (
        func.coalesce(Source.credibility_score, DEFAULT_SOURCE_CREDIBILITY)
        * source_multiplier_expression(
            source_tier_col=Source.source_tier,
            reporting_type_col=Source.reporting_type,
        )
    ).desc()
    order_by: list[Any] = [credibility_order]
    if current_primary_item_id is not None:
        order_by.append(case((RawItem.id == current_primary_item_id, 1), else_=0).desc())
    order_by.extend(
        [
            RawItem.published_at.desc().nullslast(),
            RawItem.fetched_at.desc().nullslast(),
        ]
    )
    query = (
        select(RawItem)
        .join(Source, Source.id == RawItem.source_id)
        .where(RawItem.id.in_(item_ids))
        .order_by(*order_by)
        .limit(1)
    )
    item = await session.scalar(query)
    if item is None:
        raise ValueError("unable to resolve primary item for event repair")
    return item


def _build_canonical_summary(item: RawItem) -> str:
    if item.title and item.title.strip():
        return item.title.strip()
    content = item.raw_content.strip()
    return content[:400] if len(content) > 400 else content


def _item_timestamp(item: RawItem) -> datetime:
    if item.published_at is not None:
        return item.published_at
    if item.fetched_at is not None:
        return item.fetched_at
    return datetime.now(tz=UTC)


def _require_event_id(event: Event) -> UUID:
    if event.id is None:
        raise ValueError("event must have an id before repair")
    return event.id
