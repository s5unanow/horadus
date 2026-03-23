from __future__ import annotations

from datetime import UTC, datetime, timedelta
from inspect import signature
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError

from src.processing.pipeline_retry import build_retryable_pipeline_error
from src.storage.event_lineage_models import EventLineage
from src.storage.models import LLMReplayQueueItem

DEFAULT_REPLAY_MAX_ATTEMPTS = 3
DEFAULT_REPLAY_BACKOFF_SECONDS = 300
MAX_REPLAY_BACKOFF_SECONDS = 3600


def _replay_provenance_derivation(*, item: Any, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "replay_queue",
        "queue_item_id": str(item.id),
        "original_extraction_provenance": details.get("original_extraction_provenance"),
    }


def _replay_retry_max_attempts(*, deps: Any) -> int:
    return max(
        1,
        int(
            getattr(
                deps.settings,
                "LLM_DEGRADED_REPLAY_RETRY_MAX_ATTEMPTS",
                DEFAULT_REPLAY_MAX_ATTEMPTS,
            )
        ),
    )


def _replay_backoff_seconds(*, deps: Any, attempt_count: int) -> int:
    base_delay_seconds = max(
        0,
        int(
            getattr(
                deps.settings,
                "LLM_DEGRADED_REPLAY_RETRY_BACKOFF_SECONDS",
                DEFAULT_REPLAY_BACKOFF_SECONDS,
            )
        ),
    )
    if base_delay_seconds == 0:
        return 0
    return min(base_delay_seconds * max(1, attempt_count), MAX_REPLAY_BACKOFF_SECONDS)


def _retryable_replay_failure_reason(exc: Exception) -> str | None:
    retryable_error = build_retryable_pipeline_error(
        item_id=None,
        stage="replay_degraded_events",
        exc=exc,
    )
    if retryable_error is not None:
        return retryable_error.reason
    if isinstance(exc, OperationalError):
        return "db_operational_error"
    if isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False)):
        return "db_connection_invalidated"
    return None


def _scheduled_replay_retry_at(*, deps: Any, now: datetime, attempt_count: int) -> datetime:
    return now + timedelta(seconds=_replay_backoff_seconds(deps=deps, attempt_count=attempt_count))


def _pending_replay_due_at(item: Any) -> datetime | None:
    details = item.details or {}
    retry_state = details.get("replay_failure") if isinstance(details, dict) else None
    raw_value = retry_state.get("next_attempt_after") if isinstance(retry_state, dict) else None
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        due_at = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if due_at.tzinfo is None:
        return due_at.replace(tzinfo=UTC)
    return due_at


def _is_replay_item_ready(*, item: Any, now: datetime) -> bool:
    due_at = _pending_replay_due_at(item)
    return due_at is None or due_at <= now


async def _load_due_replay_items(
    *,
    deps: Any,
    session: Any,
    now: datetime,
    limit: int,
) -> list[Any]:
    pending_query = (
        deps.select(deps.LLMReplayQueueItem)
        .where(deps.LLMReplayQueueItem.status == "pending")
        .order_by(
            deps.LLMReplayQueueItem.priority.desc(),
            deps.LLMReplayQueueItem.enqueued_at.asc(),
        )
    )
    if not getattr(deps.settings, "LLM_DEGRADED_REPLAY_ENABLED", True):
        pending_query = pending_query.where(
            deps.LLMReplayQueueItem.details["reason"].as_string() == "event_lineage_repair"
        )
    rows = (await session.scalars(pending_query.with_for_update(skip_locked=True))).all()
    return [item for item in rows if _is_replay_item_ready(item=item, now=now)][:limit]


async def _build_replay_runtime(*, deps: Any, session: Any) -> tuple[list[Any], Any, Any]:
    trends = list(
        (
            await session.scalars(
                deps.select(deps.Trend)
                .where(deps.Trend.is_active.is_(True))
                .order_by(deps.Trend.name.asc())
            )
        ).all()
    )
    tier2 = deps.Tier2Classifier(
        session=session,
        model=deps.settings.LLM_TIER2_MODEL,
        secondary_model=None,
    )
    pipeline = deps.ProcessingPipeline(
        session=session,
        tier2_classifier=tier2,
        degraded_llm_tracker=None,
    )
    return trends, tier2, pipeline


async def _replay_one_degraded_item(
    *,
    deps: Any,
    session: Any,
    tier2: Any,
    pipeline: Any,
    trends: list[Any],
    item: Any,
    now: datetime,
) -> bool:
    event = await session.get(deps.Event, item.event_id)
    if event is None:
        raise ValueError(f"Event not found: {item.event_id}")
    details = dict(item.details or {})
    classify_kwargs = {"event": event, "trends": trends}
    if "provenance_derivation" in signature(tier2.classify_event).parameters:
        classify_kwargs["provenance_derivation"] = _replay_provenance_derivation(
            item=item,
            details=details,
        )
    await tier2.classify_event(**classify_kwargs)
    impacts_seen, updates_applied = await pipeline._apply_trend_impacts(
        event=event,
        trends=trends,
    )
    item.status = "done"
    item.processed_at = now
    item.locked_at = None
    item.locked_by = None
    item.last_error = None
    details.pop("replay_failure", None)
    details["replay_result"] = {
        "impacts_seen": impacts_seen,
        "updates_applied": updates_applied,
        "processed_at": now.isoformat(),
        "model": deps.settings.LLM_TIER2_MODEL,
    }
    item.details = details
    await session.flush()
    await _sync_lineage_replay_status(session=session, event_id=item.event_id)
    return True


async def _sync_lineage_replay_status(*, session: Any, event_id: Any) -> None:
    relevant_lineages = await _load_relevant_lineages(session=session, event_id=event_id)
    if not relevant_lineages:
        return

    (
        status_by_event_id,
        status_by_queue_item_id,
        status_by_request_id,
    ) = await _load_replay_status_maps(
        session=session,
        lineages=relevant_lineages,
    )
    for lineage in relevant_lineages:
        _apply_lineage_replay_status(
            lineage=lineage,
            status_by_event_id=status_by_event_id,
            status_by_queue_item_id=status_by_queue_item_id,
            status_by_request_id=status_by_request_id,
        )


async def _handle_replay_item_failure(
    *,
    deps: Any,
    session: Any,
    item: Any,
    exc: Exception,
    now: datetime,
) -> None:
    attempt_count = int(item.attempt_count or 0)
    max_attempts = _replay_retry_max_attempts(deps=deps)
    retry_reason = _retryable_replay_failure_reason(exc)
    details = dict(item.details or {})
    failure_details: dict[str, Any] = {
        "attempt_count": attempt_count,
        "error_type": type(exc).__name__,
        "failed_at": now.isoformat(),
        "max_attempts": max_attempts,
    }
    if retry_reason is not None:
        failure_details["reason"] = retry_reason
    item.locked_at = None
    item.locked_by = None
    item.processed_at = None
    item.last_error = str(exc)[:1000]
    if retry_reason is not None and attempt_count < max_attempts:
        next_attempt_after = _scheduled_replay_retry_at(
            deps=deps,
            now=now,
            attempt_count=attempt_count,
        )
        failure_details["disposition"] = "retryable"
        failure_details["next_attempt_after"] = next_attempt_after.isoformat()
        item.status = "pending"
    elif retry_reason is not None:
        failure_details["disposition"] = "retry_exhausted"
        item.status = "error"
    else:
        failure_details["disposition"] = "manual_review"
        item.status = "error"
    details["replay_failure"] = failure_details
    item.details = details
    await session.flush()
    if item.status == "error":
        await _sync_lineage_replay_status(session=session, event_id=item.event_id)


def _parse_lineage_replay_ids(lineage: EventLineage) -> tuple[UUID, ...]:
    parsed_ids: list[UUID] = []
    for value in (lineage.details or {}).get("replay_enqueued_event_ids", []):
        try:
            parsed_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return tuple(parsed_ids)


def _parse_lineage_queue_item_ids(lineage: EventLineage) -> tuple[UUID, ...]:
    parsed_ids: list[UUID] = []
    for value in (lineage.details or {}).get("replay_queue_item_ids", []):
        try:
            parsed_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return tuple(parsed_ids)


def _parse_lineage_replay_request_ids(lineage: EventLineage) -> tuple[UUID, ...]:
    parsed_ids: list[UUID] = []
    for value in (lineage.details or {}).get("replay_request_ids", []):
        try:
            parsed_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return tuple(parsed_ids)


async def _load_relevant_lineages(*, session: Any, event_id: Any) -> list[EventLineage]:
    event_id_str = str(event_id)
    return [
        lineage
        for lineage in (
            await session.scalars(
                select(EventLineage).where(
                    (EventLineage.source_event_id == event_id)
                    | (EventLineage.target_event_id == event_id)
                )
            )
        ).all()
        if event_id_str
        in {str(value) for value in (lineage.details or {}).get("replay_enqueued_event_ids", [])}
    ]


async def _load_replay_status_maps(
    *,
    session: Any,
    lineages: list[EventLineage],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    replay_event_ids = {
        parsed_id for lineage in lineages for parsed_id in _parse_lineage_replay_ids(lineage)
    }
    status_rows = (
        await session.execute(
            select(
                LLMReplayQueueItem.id,
                LLMReplayQueueItem.event_id,
                LLMReplayQueueItem.status,
                LLMReplayQueueItem.details,
            ).where(
                (LLMReplayQueueItem.stage == "tier2")
                & (LLMReplayQueueItem.event_id.in_(tuple(replay_event_ids)))
            )
        )
    ).all()
    return _build_replay_status_maps(status_rows)


def _build_replay_status_maps(
    status_rows: list[tuple[Any, ...]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    status_by_event_id: dict[str, str] = {}
    status_by_queue_item_id: dict[str, str] = {}
    status_by_request_id: dict[str, str] = {}
    for row in status_rows:
        if len(row) == 4:
            queue_item_id, replay_event_id, status, details = row
            if queue_item_id is not None:
                status_by_queue_item_id[str(queue_item_id)] = status
            if replay_event_id is not None:
                status_by_event_id[str(replay_event_id)] = status
            replay_request_id = _parse_queue_row_replay_request_id(details)
            if replay_request_id is not None:
                status_by_request_id[str(replay_request_id)] = status
            continue
        if len(row) == 3:
            queue_item_id, replay_event_id, status = row
            if queue_item_id is not None:
                status_by_queue_item_id[str(queue_item_id)] = status
            if replay_event_id is not None:
                status_by_event_id[str(replay_event_id)] = status
            continue
        replay_event_id, status = row
        if replay_event_id is not None:
            status_by_event_id[str(replay_event_id)] = status
    return status_by_event_id, status_by_queue_item_id, status_by_request_id


def _apply_lineage_replay_status(
    *,
    lineage: EventLineage,
    status_by_event_id: dict[str, str],
    status_by_queue_item_id: dict[str, str],
    status_by_request_id: dict[str, str],
) -> None:
    replay_request_ids = tuple(
        str(parsed_id) for parsed_id in _parse_lineage_replay_request_ids(lineage)
    )
    replay_queue_ids = tuple(str(parsed_id) for parsed_id in _parse_lineage_queue_item_ids(lineage))
    replay_ids = tuple(str(parsed_id) for parsed_id in _parse_lineage_replay_ids(lineage))
    if replay_request_ids:
        status_lookup = status_by_request_id
        tracked_ids = replay_request_ids
    elif replay_queue_ids:
        status_lookup = status_by_queue_item_id
        tracked_ids = replay_queue_ids
    else:
        status_lookup = status_by_event_id
        tracked_ids = replay_ids
    if not tracked_ids:
        return
    replay_statuses = {status_lookup.get(replay_id) for replay_id in tracked_ids}
    details = dict(lineage.details or {})
    if "error" in replay_statuses:
        details["status"] = "replay_error"
        lineage.details = details
        return
    if None in replay_statuses:
        if details.get("status") in {"replay_complete", "replay_error"}:
            return
        details["status"] = "replay_superseded"
        lineage.details = details
        return
    if all(status_lookup.get(replay_id) == "done" for replay_id in tracked_ids):
        details["status"] = "replay_complete"
        lineage.details = details


def _parse_queue_row_replay_request_id(details: Any) -> UUID | None:
    value = details.get("replay_request_id") if isinstance(details, dict) else None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def snapshot_trends_async(*, deps: Any) -> dict[str, Any]:
    snapshot_time = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    async with deps.async_session_maker() as session:
        trends = list(
            (
                await session.scalars(
                    deps.select(deps.Trend)
                    .where(deps.Trend.is_active.is_(True))
                    .order_by(deps.Trend.name.asc())
                )
            ).all()
        )

        created = 0
        skipped = 0
        for trend in trends:
            trend_id = trend.id
            if trend_id is None:
                skipped += 1
                continue

            existing = await session.scalar(
                deps.select(deps.TrendSnapshot.trend_id)
                .where(deps.TrendSnapshot.trend_id == trend_id)
                .where(deps.TrendSnapshot.timestamp == snapshot_time)
                .limit(1)
            )
            if existing is not None:
                skipped += 1
                continue

            session.add(
                deps.TrendSnapshot(
                    trend_id=trend_id,
                    timestamp=snapshot_time,
                    state_version_id=getattr(trend, "active_state_version_id", None),
                    log_odds=float(trend.current_log_odds),
                )
            )
            created += 1

        await session.commit()

    return {
        "status": "ok",
        "task": "snapshot_trends",
        "timestamp": snapshot_time.isoformat(),
        "scanned": len(trends),
        "created": created,
        "skipped": skipped,
    }


async def decay_trends_async(*, deps: Any) -> dict[str, Any]:
    as_of = datetime.now(tz=UTC)
    async with deps.async_session_maker() as session:
        engine = deps.TrendEngine(session=session)
        trends = list(
            (
                await session.scalars(
                    deps.select(deps.Trend)
                    .where(deps.Trend.is_active.is_(True))
                    .order_by(deps.Trend.name.asc())
                )
            ).all()
        )

        decayed = 0
        unchanged = 0
        for trend in trends:
            previous_probability = engine.get_probability(trend)
            new_probability = await engine.apply_decay(trend=trend, as_of=as_of)
            if abs(new_probability - previous_probability) > 1e-12:
                decayed += 1
            else:
                unchanged += 1
            deps.logger.debug(
                "Applied trend decay",
                trend_id=str(trend.id),
                trend_name=trend.name,
                previous_probability=previous_probability,
                new_probability=new_probability,
            )

        await session.commit()

    return {
        "status": "ok",
        "task": "apply_trend_decay",
        "as_of": as_of.isoformat(),
        "scanned": len(trends),
        "decayed": decayed,
        "unchanged": unchanged,
    }


async def check_event_lifecycles_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        manager = deps.EventLifecycleManager(session)
        run_result = await manager.run_decay_check()
        await session.commit()

    return {
        "status": "ok",
        **run_result,
    }


async def generate_weekly_reports_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        generator = deps.ReportGenerator(session=session)
        run_result = await generator.generate_weekly_reports()
        await session.commit()

    return {
        "status": "ok",
        "task": "generate_weekly_reports",
        "period_start": run_result.period_start.isoformat(),
        "period_end": run_result.period_end.isoformat(),
        "scanned": run_result.scanned,
        "created": run_result.created,
        "updated": run_result.updated,
    }


async def generate_monthly_reports_async(*, deps: Any) -> dict[str, Any]:
    async with deps.async_session_maker() as session:
        generator = deps.ReportGenerator(session=session)
        run_result = await generator.generate_monthly_reports()
        await session.commit()

    return {
        "status": "ok",
        "task": "generate_monthly_reports",
        "period_start": run_result.period_start.isoformat(),
        "period_end": run_result.period_end.isoformat(),
        "scanned": run_result.scanned,
        "created": run_result.created,
        "updated": run_result.updated,
    }


async def replay_degraded_events_async(*, deps: Any, limit: int) -> dict[str, Any]:
    tracker = (
        deps.DegradedLLMTracker(stage="tier2") if deps.settings.LLM_DEGRADED_MODE_ENABLED else None
    )
    if tracker is not None:
        status = await deps.asyncio.to_thread(tracker.evaluate)
        if status.is_degraded:
            return {
                "status": "skipped",
                "task": "replay_degraded_events",
                "reason": "degraded_llm_active",
                "stage": status.stage,
                "window": {
                    "total_calls": status.window.total_calls,
                    "secondary_calls": status.window.secondary_calls,
                    "failover_ratio": round(status.window.failover_ratio, 6),
                },
            }

    now = datetime.now(tz=UTC)
    async with deps.async_session_maker() as session:
        run_limit = max(1, int(limit))
        items = await _load_due_replay_items(
            deps=deps,
            session=session,
            now=now,
            limit=run_limit,
        )
        if not items:
            return {
                "status": "ok",
                "task": "replay_degraded_events",
                "drained": 0,
                "errors": 0,
            }

        for item in items:
            item.status = "processing"
            item.locked_at = now
            item.locked_by = "workers.replay_degraded_events"
            item.attempt_count = int(item.attempt_count or 0) + 1
            item.last_attempt_at = now
        await session.flush()

        trends, tier2, pipeline = await _build_replay_runtime(deps=deps, session=session)

        drained = errors = 0
        for item in items:
            drained += 1
            try:
                await _replay_one_degraded_item(
                    deps=deps,
                    session=session,
                    tier2=tier2,
                    pipeline=pipeline,
                    trends=trends,
                    item=item,
                    now=now,
                )
            except Exception as exc:
                errors += 1
                await _handle_replay_item_failure(
                    deps=deps,
                    session=session,
                    item=item,
                    exc=exc,
                    now=now,
                )
        await session.commit()

    return {
        "status": "ok",
        "task": "replay_degraded_events",
        "drained": drained,
        "errors": errors,
    }
