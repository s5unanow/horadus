from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.storage.event_state import EventActivityState


@dataclass(frozen=True, slots=True)
class RetentionCutoffs:
    now: datetime
    raw_item_noise_before: datetime
    raw_item_archived_event_before: datetime
    archived_event_before: datetime
    trend_evidence_before: datetime
    batch_size: int
    dry_run: bool


def build_retention_cutoffs(*, deps: Any, dry_run: bool | None = None) -> RetentionCutoffs:
    now = datetime.now(tz=UTC)
    effective_dry_run = deps.settings.RETENTION_CLEANUP_DRY_RUN if dry_run is None else dry_run
    return RetentionCutoffs(
        now=now,
        raw_item_noise_before=now - timedelta(days=deps.settings.RETENTION_RAW_ITEM_NOISE_DAYS),
        raw_item_archived_event_before=now
        - timedelta(days=deps.settings.RETENTION_RAW_ITEM_ARCHIVED_EVENT_DAYS),
        archived_event_before=now - timedelta(days=deps.settings.RETENTION_EVENT_ARCHIVED_DAYS),
        trend_evidence_before=now - timedelta(days=deps.settings.RETENTION_TREND_EVIDENCE_DAYS),
        batch_size=max(1, deps.settings.RETENTION_CLEANUP_BATCH_SIZE),
        dry_run=effective_dry_run,
    )


def is_raw_item_noise_retention_eligible(
    *,
    processing_status: Any,
    fetched_at: datetime,
    has_event_link: bool,
    cutoffs: RetentionCutoffs,
    noise_status: Any,
    error_status: Any,
) -> bool:
    return (
        processing_status in {noise_status, error_status}
        and fetched_at <= cutoffs.raw_item_noise_before
        and not has_event_link
    )


def is_raw_item_archived_event_retention_eligible(
    *,
    fetched_at: datetime,
    event_activity_state: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    if event_last_mention_at is None:
        return False
    return (
        event_activity_state == EventActivityState.CLOSED.value
        and event_last_mention_at <= cutoffs.raw_item_archived_event_before
        and fetched_at <= cutoffs.raw_item_archived_event_before
    )


def is_trend_evidence_retention_eligible(
    *,
    created_at: datetime,
    event_activity_state: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    if event_last_mention_at is None:
        return False
    return (
        event_activity_state == EventActivityState.CLOSED.value
        and event_last_mention_at <= cutoffs.archived_event_before
        and created_at <= cutoffs.trend_evidence_before
    )


def is_archived_event_retention_eligible(
    *,
    activity_state: str,
    last_mention_at: datetime,
    has_remaining_evidence: bool,
    cutoffs: RetentionCutoffs,
) -> bool:
    return (
        activity_state == EventActivityState.CLOSED.value
        and last_mention_at <= cutoffs.archived_event_before
        and not has_remaining_evidence
    )


async def select_noise_raw_item_ids(*, deps: Any, batch_size: int, cutoff: datetime) -> list[Any]:
    async with deps.async_session_maker() as session:
        linked_event_exists = (
            deps.select(deps.EventItem.item_id).where(deps.EventItem.item_id == deps.RawItem.id)
        ).exists()
        return list(
            (
                await session.scalars(
                    deps.select(deps.RawItem.id)
                    .where(
                        deps.RawItem.processing_status.in_(
                            [deps.ProcessingStatus.NOISE, deps.ProcessingStatus.ERROR]
                        )
                    )
                    .where(deps.RawItem.fetched_at <= cutoff)
                    .where(~linked_event_exists)
                    .order_by(deps.RawItem.fetched_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def select_archived_event_raw_item_ids(
    *,
    deps: Any,
    batch_size: int,
    cutoff: datetime,
) -> list[Any]:
    async with deps.async_session_maker() as session:
        return list(
            (
                await session.scalars(
                    deps.select(deps.RawItem.id)
                    .join(deps.EventItem, deps.EventItem.item_id == deps.RawItem.id)
                    .join(deps.Event, deps.Event.id == deps.EventItem.event_id)
                    .where(deps.Event.activity_state == EventActivityState.CLOSED.value)
                    .where(deps.Event.last_mention_at <= cutoff)
                    .where(deps.RawItem.fetched_at <= cutoff)
                    .order_by(deps.RawItem.fetched_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def select_trend_evidence_ids(
    *,
    deps: Any,
    batch_size: int,
    evidence_cutoff: datetime,
    archived_event_cutoff: datetime,
) -> list[Any]:
    async with deps.async_session_maker() as session:
        return list(
            (
                await session.scalars(
                    deps.select(deps.TrendEvidence.id)
                    .join(deps.Event, deps.Event.id == deps.TrendEvidence.event_id)
                    .where(deps.TrendEvidence.created_at <= evidence_cutoff)
                    .where(deps.Event.activity_state == EventActivityState.CLOSED.value)
                    .where(deps.Event.last_mention_at <= archived_event_cutoff)
                    .order_by(deps.TrendEvidence.created_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def run_data_retention_cleanup_async(
    *,
    deps: Any,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    cutoffs = deps._build_retention_cutoffs(dry_run=dry_run)

    noise_ids = await deps._select_noise_raw_item_ids(
        batch_size=cutoffs.batch_size,
        cutoff=cutoffs.raw_item_noise_before,
    )
    archived_event_raw_ids = await deps._select_archived_event_raw_item_ids(
        batch_size=cutoffs.batch_size,
        cutoff=cutoffs.raw_item_archived_event_before,
    )
    evidence_ids = await deps._select_trend_evidence_ids(
        batch_size=cutoffs.batch_size,
        evidence_cutoff=cutoffs.trend_evidence_before,
        archived_event_cutoff=cutoffs.archived_event_before,
    )

    raw_ids = list(dict.fromkeys([*noise_ids, *archived_event_raw_ids]))
    deleted_raw = 0
    deleted_evidence = 0
    deleted_events = 0
    event_ids: list[Any] = []

    async with deps.async_session_maker() as session:
        if not cutoffs.dry_run:
            if raw_ids:
                deleted_raw_result = await session.execute(
                    deps.delete(deps.RawItem).where(deps.RawItem.id.in_(raw_ids))
                )
                deleted_raw = int(getattr(deleted_raw_result, "rowcount", 0) or 0)

            if evidence_ids:
                deleted_evidence_result = await session.execute(
                    deps.delete(deps.TrendEvidence).where(deps.TrendEvidence.id.in_(evidence_ids))
                )
                deleted_evidence = int(getattr(deleted_evidence_result, "rowcount", 0) or 0)

            await session.flush()

        has_evidence = (
            deps.select(deps.TrendEvidence.id)
            .where(deps.TrendEvidence.event_id == deps.Event.id)
            .exists()
        )
        event_ids = list(
            (
                await session.scalars(
                    deps.select(deps.Event.id)
                    .where(deps.Event.activity_state == EventActivityState.CLOSED.value)
                    .where(deps.Event.last_mention_at <= cutoffs.archived_event_before)
                    .where(~has_evidence)
                    .order_by(deps.Event.last_mention_at.asc())
                    .limit(cutoffs.batch_size)
                )
            ).all()
        )

        if not cutoffs.dry_run and event_ids:
            deleted_events_result = await session.execute(
                deps.delete(deps.Event).where(deps.Event.id.in_(event_ids))
            )
            deleted_events = int(getattr(deleted_events_result, "rowcount", 0) or 0)

        if cutoffs.dry_run:
            await session.rollback()
        else:
            await session.commit()

    return {
        "status": "ok",
        "task": "run_data_retention_cleanup",
        "dry_run": cutoffs.dry_run,
        "batch_size": cutoffs.batch_size,
        "cutoffs": {
            "raw_item_noise_before": cutoffs.raw_item_noise_before.isoformat(),
            "raw_item_archived_event_before": cutoffs.raw_item_archived_event_before.isoformat(),
            "archived_event_before": cutoffs.archived_event_before.isoformat(),
            "trend_evidence_before": cutoffs.trend_evidence_before.isoformat(),
        },
        "eligible": {
            "raw_items_noise": len(noise_ids),
            "raw_items_archived_event": len(archived_event_raw_ids),
            "raw_items_total": len(raw_ids),
            "trend_evidence": len(evidence_ids),
            "events": len(event_ids),
        },
        "deleted": {
            "raw_items": deleted_raw,
            "trend_evidence": deleted_evidence,
            "events": deleted_events,
        },
    }
