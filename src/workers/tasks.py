"""
Celery tasks for ingestion collection and processing orchestration.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar, cast

import httpx
import redis
import structlog
from celery import shared_task
from celery.signals import task_failure
from sqlalchemy import delete, func, select

from src.core.config import settings
from src.core.observability import (
    record_collector_metrics,
    record_pipeline_metrics,
    record_processing_backlog_depth,
    record_processing_dispatch_decision,
    record_processing_reaper_resets,
    record_retention_cleanup_rows,
    record_retention_cleanup_run,
    record_source_catchup_dispatch,
    record_source_freshness_stale,
    record_worker_error,
)
from src.core.report_generator import ReportGenerator
from src.core.source_freshness import build_source_freshness_report
from src.core.trend_engine import TrendEngine
from src.ingestion.gdelt_client import GDELTClient
from src.ingestion.rss_collector import RSSCollector
from src.processing.cost_tracker import CostTracker
from src.processing.event_lifecycle import EventLifecycleManager
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.storage.database import async_session_maker
from src.storage.models import (
    Event,
    EventItem,
    EventLifecycle,
    ProcessingStatus,
    RawItem,
    Trend,
    TrendEvidence,
    TrendSnapshot,
)

logger = structlog.get_logger(__name__)

DEAD_LETTER_KEY = "celery:dead_letter"
DEAD_LETTER_MAX_ITEMS = 1000
PROCESSING_IN_FLIGHT_KEY = "horadus:processing:in_flight"
PROCESSING_DISPATCH_LOCK_KEY = "horadus:processing:dispatch_lock"

TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Any])


class CollectorTransientRunError(RuntimeError):
    """Raised when a collector run should be requeued for transient outages."""


@dataclass(slots=True)
class ProcessingDispatchPlan:
    should_dispatch: bool
    reason: str
    task_limit: int
    pending_backlog: int
    in_flight: int
    budget_status: str
    budget_remaining_usd: float | None


@dataclass(frozen=True, slots=True)
class RetentionCutoffs:
    now: datetime
    raw_item_noise_before: datetime
    raw_item_archived_event_before: datetime
    archived_event_before: datetime
    trend_evidence_before: datetime
    batch_size: int
    dry_run: bool


def _build_retention_cutoffs(*, dry_run: bool | None = None) -> RetentionCutoffs:
    now = datetime.now(tz=UTC)
    effective_dry_run = settings.RETENTION_CLEANUP_DRY_RUN if dry_run is None else dry_run
    return RetentionCutoffs(
        now=now,
        raw_item_noise_before=now - timedelta(days=settings.RETENTION_RAW_ITEM_NOISE_DAYS),
        raw_item_archived_event_before=now
        - timedelta(days=settings.RETENTION_RAW_ITEM_ARCHIVED_EVENT_DAYS),
        archived_event_before=now - timedelta(days=settings.RETENTION_EVENT_ARCHIVED_DAYS),
        trend_evidence_before=now - timedelta(days=settings.RETENTION_TREND_EVIDENCE_DAYS),
        batch_size=max(1, settings.RETENTION_CLEANUP_BATCH_SIZE),
        dry_run=effective_dry_run,
    )


def _is_raw_item_noise_retention_eligible(
    *,
    processing_status: ProcessingStatus,
    fetched_at: datetime,
    has_event_link: bool,
    cutoffs: RetentionCutoffs,
) -> bool:
    return (
        processing_status in {ProcessingStatus.NOISE, ProcessingStatus.ERROR}
        and fetched_at <= cutoffs.raw_item_noise_before
        and not has_event_link
    )


def _is_raw_item_archived_event_retention_eligible(
    *,
    fetched_at: datetime,
    event_lifecycle_status: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    if event_last_mention_at is None:
        return False
    return (
        event_lifecycle_status == EventLifecycle.ARCHIVED.value
        and event_last_mention_at <= cutoffs.raw_item_archived_event_before
        and fetched_at <= cutoffs.raw_item_archived_event_before
    )


def _is_trend_evidence_retention_eligible(
    *,
    created_at: datetime,
    event_lifecycle_status: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    if event_last_mention_at is None:
        return False
    return (
        event_lifecycle_status == EventLifecycle.ARCHIVED.value
        and event_last_mention_at <= cutoffs.archived_event_before
        and created_at <= cutoffs.trend_evidence_before
    )


def _is_archived_event_retention_eligible(
    *,
    lifecycle_status: str,
    last_mention_at: datetime,
    has_remaining_evidence: bool,
    cutoffs: RetentionCutoffs,
) -> bool:
    return (
        lifecycle_status == EventLifecycle.ARCHIVED.value
        and last_mention_at <= cutoffs.archived_event_before
        and not has_remaining_evidence
    )


def typed_shared_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskFunc], TaskFunc]:
    """
    Typed wrapper around Celery's shared_task decorator.

    Celery decorators are untyped, which conflicts with strict mypy settings.
    """
    decorator = shared_task(*task_args, **task_kwargs)
    return cast("Callable[[TaskFunc], TaskFunc]", decorator)


def _run_async(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    return asyncio.run(coro)


def _should_requeue_collector_run(result: dict[str, Any]) -> bool:
    transient_errors = int(result.get("transient_errors", 0))
    terminal_errors = int(result.get("terminal_errors", 0))
    sources_succeeded = int(result.get("sources_succeeded", 0))
    sources_failed = int(result.get("sources_failed", 0))
    return (
        transient_errors > 0
        and terminal_errors == 0
        and sources_succeeded == 0
        and sources_failed > 0
    )


def _push_dead_letter(payload: dict[str, Any]) -> None:
    client: redis.Redis[str] | None = None
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.lpush(DEAD_LETTER_KEY, json.dumps(payload))
        client.ltrim(DEAD_LETTER_KEY, 0, DEAD_LETTER_MAX_ITEMS - 1)
    except Exception:
        logger.exception("Failed to push dead letter payload")
    finally:
        if client is not None:
            client.close()


def _record_worker_activity(
    *,
    task_name: str,
    status: str,
    error: str | None = None,
) -> None:
    client: redis.Redis[str] | None = None
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        payload = {
            "task": task_name,
            "status": status,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        if error:
            payload["error"] = error[:500]
        client.set(
            settings.WORKER_HEARTBEAT_REDIS_KEY,
            json.dumps(payload),
            ex=max(60, settings.WORKER_HEARTBEAT_TTL_SECONDS),
        )
    except Exception:
        logger.exception("Failed to record worker heartbeat", task_name=task_name, status=status)
    finally:
        if client is not None:
            client.close()


def _run_task_with_heartbeat(
    *,
    task_name: str,
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    _record_worker_activity(task_name=task_name, status="started")
    try:
        result = runner()
    except Exception as exc:
        _record_worker_activity(task_name=task_name, status="failed", error=str(exc))
        raise
    _record_worker_activity(task_name=task_name, status="ok")
    return result


def _handle_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **_extra: Any,
) -> None:
    request = getattr(sender, "request", None)
    current_retries = int(getattr(request, "retries", 0))

    max_retries_raw = getattr(sender, "max_retries", None)
    max_retries = max_retries_raw if isinstance(max_retries_raw, int) else None

    # Ignore intermediate failures that are still within retry budget.
    if max_retries is not None and current_retries < max_retries:
        return

    payload = {
        "task_name": getattr(sender, "name", "unknown"),
        "task_id": task_id,
        "exception_type": type(exception).__name__ if exception is not None else "unknown",
        "exception_message": str(exception) if exception is not None else "",
        "args": args or (),
        "kwargs": kwargs or {},
        "retries": current_retries,
        "failed_at": datetime.now(tz=UTC).isoformat(),
    }
    record_worker_error(task_name=str(payload["task_name"]))
    _push_dead_letter(payload)


task_failure.connect(_handle_task_failure)


def _build_processing_dispatch_plan(
    *,
    stored_items: int,
    pending_backlog: int,
    in_flight: int,
    budget_status: str,
    budget_remaining_usd: float | None,
    daily_cost_limit_usd: float,
) -> ProcessingDispatchPlan:
    if stored_items <= 0:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="no_new_items",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )
    if not settings.ENABLE_PROCESSING_PIPELINE:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="pipeline_disabled",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    max_in_flight = max(1, settings.PROCESSING_DISPATCH_MAX_IN_FLIGHT)
    if in_flight >= max_in_flight:
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="in_flight_throttle",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    queue_limit = max(1, settings.PROCESSING_PIPELINE_BATCH_SIZE)
    base_limit = min(queue_limit, max(stored_items, min(pending_backlog, queue_limit)))
    if budget_status == "sleep_mode":
        return ProcessingDispatchPlan(
            should_dispatch=False,
            reason="budget_denied",
            task_limit=0,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    min_headroom_pct = max(0, settings.PROCESSING_DISPATCH_MIN_BUDGET_HEADROOM_PCT)
    if (
        budget_remaining_usd is not None
        and daily_cost_limit_usd > 0
        and min_headroom_pct > 0
        and ((budget_remaining_usd / daily_cost_limit_usd) * 100.0) <= min_headroom_pct
    ):
        throttled_limit = min(base_limit, max(1, settings.PROCESSING_DISPATCH_LOW_HEADROOM_LIMIT))
        return ProcessingDispatchPlan(
            should_dispatch=throttled_limit > 0,
            reason="budget_low_headroom",
            task_limit=throttled_limit,
            pending_backlog=max(0, pending_backlog),
            in_flight=max(0, in_flight),
            budget_status=budget_status,
            budget_remaining_usd=budget_remaining_usd,
        )

    return ProcessingDispatchPlan(
        should_dispatch=True,
        reason="ok",
        task_limit=base_limit,
        pending_backlog=max(0, pending_backlog),
        in_flight=max(0, in_flight),
        budget_status=budget_status,
        budget_remaining_usd=budget_remaining_usd,
    )


def _get_redis_client() -> redis.Redis[str]:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_processing_in_flight_count() -> int:
    client: redis.Redis[str] | None = None
    try:
        client = _get_redis_client()
        raw_value = client.get(PROCESSING_IN_FLIGHT_KEY)
        return max(0, int(raw_value or 0))
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def _increment_processing_in_flight() -> int:
    client: redis.Redis[str] | None = None
    try:
        client = _get_redis_client()
        current = int(client.incr(PROCESSING_IN_FLIGHT_KEY))
        client.expire(PROCESSING_IN_FLIGHT_KEY, 3600)
        return max(0, current)
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def _decrement_processing_in_flight() -> int:
    client: redis.Redis[str] | None = None
    try:
        client = _get_redis_client()
        updated = int(client.decr(PROCESSING_IN_FLIGHT_KEY))
        if updated <= 0:
            client.delete(PROCESSING_IN_FLIGHT_KEY)
            return 0
        return updated
    except Exception:
        return 0
    finally:
        if client is not None:
            client.close()


def _acquire_processing_dispatch_lock() -> bool:
    lock_ttl = max(0, settings.PROCESSING_DISPATCH_LOCK_TTL_SECONDS)
    if lock_ttl == 0:
        return True

    client: redis.Redis[str] | None = None
    try:
        client = _get_redis_client()
        acquired = client.set(
            PROCESSING_DISPATCH_LOCK_KEY,
            datetime.now(tz=UTC).isoformat(),
            ex=lock_ttl,
            nx=True,
        )
        return bool(acquired)
    except Exception:
        return True
    finally:
        if client is not None:
            client.close()


async def _load_processing_dispatch_inputs_async() -> dict[str, Any]:
    async with async_session_maker() as session:
        pending_count_raw = await session.scalar(
            select(func.count(RawItem.id)).where(
                RawItem.processing_status == ProcessingStatus.PENDING
            )
        )
        pending_count = int(pending_count_raw or 0)
        budget_summary = await CostTracker(session=session).get_daily_summary()
    return {
        "pending_backlog": pending_count,
        "budget_status": str(budget_summary.get("status", "active")),
        "budget_remaining_usd": budget_summary.get("budget_remaining_usd"),
        "daily_cost_limit_usd": float(budget_summary.get("daily_cost_limit_usd", 0.0) or 0.0),
    }


async def _collect_rss_async() -> dict[str, Any]:
    async with (
        httpx.AsyncClient() as http_client,
        async_session_maker() as session,
    ):
        collector = RSSCollector(session=session, http_client=http_client)
        results = await collector.collect_all()
        await session.commit()

    return {
        "status": "ok",
        "collector": "rss",
        "fetched": sum(result.items_fetched for result in results),
        "stored": sum(result.items_stored for result in results),
        "skipped": sum(result.items_skipped for result in results),
        "errors": sum(len(result.errors) for result in results),
        "transient_errors": sum(result.transient_errors for result in results),
        "terminal_errors": sum(result.terminal_errors for result in results),
        "sources_succeeded": sum(1 for result in results if not result.errors),
        "sources_failed": sum(1 for result in results if result.errors),
        "results": [asdict(result) for result in results],
    }


async def _collect_gdelt_async() -> dict[str, Any]:
    async with (
        httpx.AsyncClient() as http_client,
        async_session_maker() as session,
    ):
        collector = GDELTClient(session=session, http_client=http_client)
        results = await collector.collect_all()
        await session.commit()

    return {
        "status": "ok",
        "collector": "gdelt",
        "fetched": sum(result.items_fetched for result in results),
        "stored": sum(result.items_stored for result in results),
        "skipped": sum(result.items_skipped for result in results),
        "errors": sum(len(result.errors) for result in results),
        "transient_errors": sum(result.transient_errors for result in results),
        "terminal_errors": sum(result.terminal_errors for result in results),
        "sources_succeeded": sum(1 for result in results if not result.errors),
        "sources_failed": sum(1 for result in results if result.errors),
        "results": [asdict(result) for result in results],
    }


async def _check_source_freshness_async() -> dict[str, Any]:
    async with async_session_maker() as session:
        report = await build_source_freshness_report(session=session)

    stale_rows = [row for row in report.rows if row.is_stale]
    stale_by_collector: dict[str, int] = {}
    for row in stale_rows:
        stale_by_collector[row.collector] = stale_by_collector.get(row.collector, 0) + 1

    for collector, stale_count in stale_by_collector.items():
        record_source_freshness_stale(collector=collector, stale_count=stale_count)

    catchup_dispatched: list[str] = []
    dispatch_budget = max(0, settings.SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES)
    if dispatch_budget > 0:
        stale_collectors = set(report.stale_collectors)
        if (
            "rss" in stale_collectors
            and settings.ENABLE_RSS_INGESTION
            and len(catchup_dispatched) < dispatch_budget
        ):
            cast("Any", collect_rss).delay()
            record_source_catchup_dispatch(collector="rss")
            catchup_dispatched.append("rss")
        if (
            "gdelt" in stale_collectors
            and settings.ENABLE_GDELT_INGESTION
            and len(catchup_dispatched) < dispatch_budget
        ):
            cast("Any", collect_gdelt).delay()
            record_source_catchup_dispatch(collector="gdelt")
            catchup_dispatched.append("gdelt")

    stale_source_rows = [
        {
            "source_id": str(row.source_id),
            "source_name": row.source_name,
            "collector": row.collector,
            "last_fetched_at": row.last_fetched_at.isoformat() if row.last_fetched_at else None,
            "age_seconds": row.age_seconds,
            "stale_after_seconds": row.stale_after_seconds,
        }
        for row in stale_rows
    ]

    return {
        "status": "ok",
        "task": "check_source_freshness",
        "checked_at": report.checked_at.isoformat(),
        "stale_multiplier": report.stale_multiplier,
        "stale_count": len(stale_rows),
        "stale_collectors": list(report.stale_collectors),
        "stale_by_collector": stale_by_collector,
        "catchup_dispatch_budget": dispatch_budget,
        "catchup_dispatched": catchup_dispatched,
        "stale_sources": stale_source_rows,
    }


def _queue_processing_for_new_items(*, collector: str, stored_items: int) -> bool:
    dispatch_inputs = _run_async(_load_processing_dispatch_inputs_async())
    pending_backlog = int(dispatch_inputs["pending_backlog"])
    budget_status = str(dispatch_inputs["budget_status"])
    budget_remaining_raw = dispatch_inputs.get("budget_remaining_usd")
    budget_remaining = (
        float(budget_remaining_raw) if isinstance(budget_remaining_raw, int | float) else None
    )
    daily_cost_limit = float(dispatch_inputs.get("daily_cost_limit_usd", 0.0) or 0.0)
    in_flight = _get_processing_in_flight_count()

    plan = _build_processing_dispatch_plan(
        stored_items=stored_items,
        pending_backlog=pending_backlog,
        in_flight=in_flight,
        budget_status=budget_status,
        budget_remaining_usd=budget_remaining,
        daily_cost_limit_usd=daily_cost_limit,
    )
    record_processing_backlog_depth(pending_count=pending_backlog)

    if plan.should_dispatch and not _acquire_processing_dispatch_lock():
        record_processing_dispatch_decision(dispatched=False, reason="dispatch_lock_active")
        logger.info(
            "Skipped processing dispatch due to active dispatch lock",
            collector=collector,
            stored_items=stored_items,
            pending_backlog=pending_backlog,
            in_flight=in_flight,
        )
        return False

    if not plan.should_dispatch:
        record_processing_dispatch_decision(dispatched=False, reason=plan.reason)
        logger.info(
            "Skipped processing dispatch",
            collector=collector,
            stored_items=stored_items,
            reason=plan.reason,
            pending_backlog=plan.pending_backlog,
            in_flight=plan.in_flight,
            budget_status=plan.budget_status,
            budget_remaining_usd=plan.budget_remaining_usd,
        )
        return False

    cast("Any", process_pending_items).delay(limit=plan.task_limit)
    record_processing_dispatch_decision(dispatched=True, reason=plan.reason)
    logger.info(
        "Queued processing pipeline task",
        collector=collector,
        stored_items=stored_items,
        task_limit=plan.task_limit,
        pending_backlog=plan.pending_backlog,
        in_flight=plan.in_flight,
        budget_status=plan.budget_status,
        budget_remaining_usd=plan.budget_remaining_usd,
    )
    return True


async def _process_pending_async(limit: int) -> dict[str, Any]:
    async with async_session_maker() as session:
        pipeline = ProcessingPipeline(session=session)
        run_result = await pipeline.process_pending_items(limit=limit)
        await session.commit()

    return {
        "status": "ok",
        "task": "processing_pipeline",
        **ProcessingPipeline.run_result_to_dict(run_result),
    }


async def _reap_stale_processing_async() -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    stale_before = now - timedelta(minutes=settings.PROCESSING_STALE_TIMEOUT_MINUTES)
    async with async_session_maker() as session:
        stale_items = list(
            (
                await session.scalars(
                    select(RawItem)
                    .where(RawItem.processing_status == ProcessingStatus.PROCESSING)
                    .where(RawItem.processing_started_at.is_not(None))
                    .where(RawItem.processing_started_at <= stale_before)
                    .order_by(RawItem.processing_started_at.asc())
                    .limit(max(1, settings.PROCESSING_PIPELINE_BATCH_SIZE))
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

        reset_item_ids: list[str] = []
        for item in stale_items:
            item.processing_status = ProcessingStatus.PENDING
            item.processing_started_at = None
            item.error_message = None
            reset_item_ids.append(str(item.id))

        await session.commit()

    logger.info(
        "Reaped stale processing items",
        scanned=len(stale_items),
        reset_count=len(reset_item_ids),
        reset_item_ids=reset_item_ids,
        stale_before=stale_before.isoformat(),
    )
    return {
        "status": "ok",
        "task": "reap_stale_processing_items",
        "checked_at": now.isoformat(),
        "stale_before": stale_before.isoformat(),
        "scanned": len(stale_items),
        "reset": len(reset_item_ids),
        "reset_item_ids": reset_item_ids,
    }


async def _snapshot_trends_async() -> dict[str, Any]:
    snapshot_time = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    async with async_session_maker() as session:
        trends = list(
            (
                await session.scalars(
                    select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
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
                select(TrendSnapshot.trend_id)
                .where(TrendSnapshot.trend_id == trend_id)
                .where(TrendSnapshot.timestamp == snapshot_time)
                .limit(1)
            )
            if existing is not None:
                skipped += 1
                continue

            session.add(
                TrendSnapshot(
                    trend_id=trend_id,
                    timestamp=snapshot_time,
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


async def _decay_trends_async() -> dict[str, Any]:
    as_of = datetime.now(tz=UTC)
    async with async_session_maker() as session:
        engine = TrendEngine(session=session)
        trends = list(
            (
                await session.scalars(
                    select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
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
            logger.debug(
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


async def _check_event_lifecycles_async() -> dict[str, Any]:
    async with async_session_maker() as session:
        manager = EventLifecycleManager(session)
        run_result = await manager.run_decay_check()
        await session.commit()

    return {
        "status": "ok",
        **run_result,
    }


async def _select_noise_raw_item_ids(*, batch_size: int, cutoff: datetime) -> list[Any]:
    async with async_session_maker() as session:
        linked_event_exists = (
            select(EventItem.item_id).where(EventItem.item_id == RawItem.id).exists()
        )
        return list(
            (
                await session.scalars(
                    select(RawItem.id)
                    .where(
                        RawItem.processing_status.in_(
                            [ProcessingStatus.NOISE, ProcessingStatus.ERROR]
                        )
                    )
                    .where(RawItem.fetched_at <= cutoff)
                    .where(~linked_event_exists)
                    .order_by(RawItem.fetched_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def _select_archived_event_raw_item_ids(
    *,
    batch_size: int,
    cutoff: datetime,
) -> list[Any]:
    async with async_session_maker() as session:
        return list(
            (
                await session.scalars(
                    select(RawItem.id)
                    .join(EventItem, EventItem.item_id == RawItem.id)
                    .join(Event, Event.id == EventItem.event_id)
                    .where(Event.lifecycle_status == EventLifecycle.ARCHIVED.value)
                    .where(Event.last_mention_at <= cutoff)
                    .where(RawItem.fetched_at <= cutoff)
                    .order_by(RawItem.fetched_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def _select_trend_evidence_ids(
    *,
    batch_size: int,
    evidence_cutoff: datetime,
    archived_event_cutoff: datetime,
) -> list[Any]:
    async with async_session_maker() as session:
        return list(
            (
                await session.scalars(
                    select(TrendEvidence.id)
                    .join(Event, Event.id == TrendEvidence.event_id)
                    .where(TrendEvidence.created_at <= evidence_cutoff)
                    .where(Event.lifecycle_status == EventLifecycle.ARCHIVED.value)
                    .where(Event.last_mention_at <= archived_event_cutoff)
                    .order_by(TrendEvidence.created_at.asc())
                    .limit(max(1, batch_size))
                )
            ).all()
        )


async def _run_data_retention_cleanup_async(*, dry_run: bool | None = None) -> dict[str, Any]:
    cutoffs = _build_retention_cutoffs(dry_run=dry_run)

    noise_ids = await _select_noise_raw_item_ids(
        batch_size=cutoffs.batch_size,
        cutoff=cutoffs.raw_item_noise_before,
    )
    archived_event_raw_ids = await _select_archived_event_raw_item_ids(
        batch_size=cutoffs.batch_size,
        cutoff=cutoffs.raw_item_archived_event_before,
    )
    evidence_ids = await _select_trend_evidence_ids(
        batch_size=cutoffs.batch_size,
        evidence_cutoff=cutoffs.trend_evidence_before,
        archived_event_cutoff=cutoffs.archived_event_before,
    )

    raw_ids = list(dict.fromkeys([*noise_ids, *archived_event_raw_ids]))
    deleted_raw = 0
    deleted_evidence = 0
    deleted_events = 0
    event_ids: list[Any] = []

    async with async_session_maker() as session:
        if not cutoffs.dry_run:
            if raw_ids:
                deleted_raw_result = await session.execute(
                    delete(RawItem).where(RawItem.id.in_(raw_ids))
                )
                deleted_raw = int(getattr(deleted_raw_result, "rowcount", 0) or 0)

            if evidence_ids:
                deleted_evidence_result = await session.execute(
                    delete(TrendEvidence).where(TrendEvidence.id.in_(evidence_ids))
                )
                deleted_evidence = int(getattr(deleted_evidence_result, "rowcount", 0) or 0)

            await session.flush()

        has_evidence = select(TrendEvidence.id).where(TrendEvidence.event_id == Event.id).exists()
        event_ids = list(
            (
                await session.scalars(
                    select(Event.id)
                    .where(Event.lifecycle_status == EventLifecycle.ARCHIVED.value)
                    .where(Event.last_mention_at <= cutoffs.archived_event_before)
                    .where(~has_evidence)
                    .order_by(Event.last_mention_at.asc())
                    .limit(cutoffs.batch_size)
                )
            ).all()
        )

        if not cutoffs.dry_run and event_ids:
            deleted_events_result = await session.execute(
                delete(Event).where(Event.id.in_(event_ids))
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


async def _generate_weekly_reports_async() -> dict[str, Any]:
    async with async_session_maker() as session:
        generator = ReportGenerator(session=session)
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


async def _generate_monthly_reports_async() -> dict[str, Any]:
    async with async_session_maker() as session:
        generator = ReportGenerator(session=session)
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


@typed_shared_task(
    name="workers.process_pending_items",
    autoretry_for=(httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_pending_items(limit: int | None = None) -> dict[str, Any]:
    """Run processing pipeline for pending raw items."""

    def _runner() -> dict[str, Any]:
        configured_limit = max(1, settings.PROCESSING_PIPELINE_BATCH_SIZE)
        run_limit = max(1, limit or configured_limit)
        in_flight = _increment_processing_in_flight()

        logger.info("Starting processing pipeline task", limit=run_limit, in_flight=in_flight)
        try:
            result = _run_async(_process_pending_async(limit=run_limit))
            record_pipeline_metrics(result)
            logger.info(
                "Finished processing pipeline task",
                scanned=result["scanned"],
                processed=result["processed"],
                classified=result["classified"],
                noise=result["noise"],
                errors=result["errors"],
            )
            return result
        finally:
            remaining_in_flight = _decrement_processing_in_flight()
            logger.debug(
                "Updated processing in-flight counter",
                in_flight=remaining_in_flight,
            )

    return _run_task_with_heartbeat(
        task_name="workers.process_pending_items",
        runner=_runner,
    )


@typed_shared_task(name="workers.reap_stale_processing_items")
def reap_stale_processing_items() -> dict[str, Any]:
    """Reset stale processing items after worker crashes/timeouts."""

    def _runner() -> dict[str, Any]:
        logger.info(
            "Starting stale processing reaper task",
            timeout_minutes=settings.PROCESSING_STALE_TIMEOUT_MINUTES,
        )
        result = _run_async(_reap_stale_processing_async())
        record_processing_reaper_resets(reset_count=int(result["reset"]))
        logger.info(
            "Finished stale processing reaper task",
            reset=result["reset"],
            scanned=result["scanned"],
            reset_item_ids=result["reset_item_ids"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.reap_stale_processing_items",
        runner=_runner,
    )


@typed_shared_task(name="workers.run_data_retention_cleanup")
def run_data_retention_cleanup(dry_run: bool | None = None) -> dict[str, Any]:
    """Run retention cleanup for high-churn operational tables."""

    def _runner() -> dict[str, Any]:
        cutoffs = _build_retention_cutoffs(dry_run=dry_run)
        logger.info(
            "Starting data retention cleanup task",
            dry_run=cutoffs.dry_run,
            batch_size=cutoffs.batch_size,
            raw_item_noise_days=settings.RETENTION_RAW_ITEM_NOISE_DAYS,
            raw_item_archived_event_days=settings.RETENTION_RAW_ITEM_ARCHIVED_EVENT_DAYS,
            archived_event_days=settings.RETENTION_EVENT_ARCHIVED_DAYS,
            trend_evidence_days=settings.RETENTION_TREND_EVIDENCE_DAYS,
        )
        result = _run_async(_run_data_retention_cleanup_async(dry_run=dry_run))

        eligible_counts = result["eligible"]
        deleted_counts = result["deleted"]
        effective_dry_run = bool(result["dry_run"])

        for table_name, eligible_value in (
            ("raw_items", eligible_counts["raw_items_total"]),
            ("trend_evidence", eligible_counts["trend_evidence"]),
            ("events", eligible_counts["events"]),
        ):
            record_retention_cleanup_rows(
                table=table_name,
                action="eligible",
                dry_run=effective_dry_run,
                count=int(eligible_value),
            )

        for table_name, deleted_value in (
            ("raw_items", deleted_counts["raw_items"]),
            ("trend_evidence", deleted_counts["trend_evidence"]),
            ("events", deleted_counts["events"]),
        ):
            record_retention_cleanup_rows(
                table=table_name,
                action="deleted",
                dry_run=effective_dry_run,
                count=int(deleted_value),
            )

        record_retention_cleanup_run(dry_run=effective_dry_run, status="ok")
        logger.info(
            "Finished data retention cleanup task",
            dry_run=effective_dry_run,
            eligible_raw_items=eligible_counts["raw_items_total"],
            eligible_trend_evidence=eligible_counts["trend_evidence"],
            eligible_events=eligible_counts["events"],
            deleted_raw_items=deleted_counts["raw_items"],
            deleted_trend_evidence=deleted_counts["trend_evidence"],
            deleted_events=deleted_counts["events"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.run_data_retention_cleanup",
        runner=_runner,
    )


@typed_shared_task(name="workers.snapshot_trends")
def snapshot_trends() -> dict[str, Any]:
    """Persist point-in-time snapshots for active trends."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting trend snapshot task")
        result = _run_async(_snapshot_trends_async())
        logger.info(
            "Finished trend snapshot task",
            scanned=result["scanned"],
            created=result["created"],
            skipped=result["skipped"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.snapshot_trends",
        runner=_runner,
    )


@typed_shared_task(name="workers.apply_trend_decay")
def apply_trend_decay() -> dict[str, Any]:
    """Apply time-based decay to all active trends."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting trend decay task")
        result = _run_async(_decay_trends_async())
        logger.info(
            "Finished trend decay task",
            scanned=result["scanned"],
            decayed=result["decayed"],
            unchanged=result["unchanged"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.apply_trend_decay",
        runner=_runner,
    )


@typed_shared_task(name="workers.generate_weekly_reports")
def generate_weekly_reports() -> dict[str, Any]:
    """Generate and store weekly reports for all active trends."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting weekly report generation task")
        result = _run_async(_generate_weekly_reports_async())
        logger.info(
            "Finished weekly report generation task",
            scanned=result["scanned"],
            created=result["created"],
            updated=result["updated"],
            period_end=result["period_end"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.generate_weekly_reports",
        runner=_runner,
    )


@typed_shared_task(name="workers.check_event_lifecycles")
def check_event_lifecycles() -> dict[str, Any]:
    """Periodically transition events across lifecycle states."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting event lifecycle check task")
        result = _run_async(_check_event_lifecycles_async())
        logger.info(
            "Finished event lifecycle check task",
            confirmed_to_fading=result["confirmed_to_fading"],
            fading_to_archived=result["fading_to_archived"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.check_event_lifecycles",
        runner=_runner,
    )


@typed_shared_task(name="workers.generate_monthly_reports")
def generate_monthly_reports() -> dict[str, Any]:
    """Generate and store monthly reports for all active trends."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting monthly report generation task")
        result = _run_async(_generate_monthly_reports_async())
        logger.info(
            "Finished monthly report generation task",
            scanned=result["scanned"],
            created=result["created"],
            updated=result["updated"],
            period_end=result["period_end"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.generate_monthly_reports",
        runner=_runner,
    )


@typed_shared_task(
    name="workers.collect_rss",
    autoretry_for=(
        httpx.TimeoutException,
        httpx.NetworkError,
        ConnectionError,
        TimeoutError,
        CollectorTransientRunError,
    ),
    retry_backoff=True,
    retry_backoff_max=settings.COLLECTOR_RETRY_BACKOFF_MAX_SECONDS,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.COLLECTOR_TASK_MAX_RETRIES},
)
def collect_rss() -> dict[str, Any]:
    """Collect RSS sources and store new raw items."""

    def _runner() -> dict[str, Any]:
        if not settings.ENABLE_RSS_INGESTION:
            return {"status": "disabled", "collector": "rss"}

        logger.info("Starting RSS collection task")
        result = _run_async(_collect_rss_async())
        record_collector_metrics(
            collector="rss",
            fetched=int(result["fetched"]),
            stored=int(result["stored"]),
            skipped=int(result["skipped"]),
            errors=int(result["errors"]),
        )
        if _should_requeue_collector_run(result):
            request = getattr(cast("Any", collect_rss), "request", None)
            current_retries = int(getattr(request, "retries", 0))
            max_retries = max(0, settings.COLLECTOR_TASK_MAX_RETRIES)
            logger.warning(
                "Transient RSS collector outage; requeueing",
                collector="rss",
                transient_errors=int(result["transient_errors"]),
                terminal_errors=int(result["terminal_errors"]),
                sources_failed=int(result["sources_failed"]),
                sources_succeeded=int(result["sources_succeeded"]),
                timeout_budget_seconds=settings.RSS_COLLECTOR_TOTAL_TIMEOUT_SECONDS,
                current_retries=current_retries,
                max_retries=max_retries,
                remaining_retries=max(0, max_retries - current_retries),
            )
            raise CollectorTransientRunError("Transient RSS collector outage")
        _queue_processing_for_new_items(collector="rss", stored_items=int(result["stored"]))
        logger.info(
            "Finished RSS collection task",
            stored=result["stored"],
            skipped=result["skipped"],
            errors=result["errors"],
            transient_errors=int(result.get("transient_errors", 0)),
            terminal_errors=int(result.get("terminal_errors", 0)),
            sources_failed=int(result.get("sources_failed", 0)),
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.collect_rss",
        runner=_runner,
    )


@typed_shared_task(
    name="workers.collect_gdelt",
    autoretry_for=(
        httpx.TimeoutException,
        httpx.NetworkError,
        ConnectionError,
        TimeoutError,
        CollectorTransientRunError,
    ),
    retry_backoff=True,
    retry_backoff_max=settings.COLLECTOR_RETRY_BACKOFF_MAX_SECONDS,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.COLLECTOR_TASK_MAX_RETRIES},
)
def collect_gdelt() -> dict[str, Any]:
    """Collect GDELT sources and store new raw items."""

    def _runner() -> dict[str, Any]:
        if not settings.ENABLE_GDELT_INGESTION:
            return {"status": "disabled", "collector": "gdelt"}

        logger.info("Starting GDELT collection task")
        result = _run_async(_collect_gdelt_async())
        record_collector_metrics(
            collector="gdelt",
            fetched=int(result["fetched"]),
            stored=int(result["stored"]),
            skipped=int(result["skipped"]),
            errors=int(result["errors"]),
        )
        if _should_requeue_collector_run(result):
            request = getattr(cast("Any", collect_gdelt), "request", None)
            current_retries = int(getattr(request, "retries", 0))
            max_retries = max(0, settings.COLLECTOR_TASK_MAX_RETRIES)
            logger.warning(
                "Transient GDELT collector outage; requeueing",
                collector="gdelt",
                transient_errors=int(result["transient_errors"]),
                terminal_errors=int(result["terminal_errors"]),
                sources_failed=int(result["sources_failed"]),
                sources_succeeded=int(result["sources_succeeded"]),
                timeout_budget_seconds=settings.GDELT_COLLECTOR_TOTAL_TIMEOUT_SECONDS,
                current_retries=current_retries,
                max_retries=max_retries,
                remaining_retries=max(0, max_retries - current_retries),
            )
            raise CollectorTransientRunError("Transient GDELT collector outage")
        _queue_processing_for_new_items(collector="gdelt", stored_items=int(result["stored"]))
        logger.info(
            "Finished GDELT collection task",
            stored=result["stored"],
            skipped=result["skipped"],
            errors=result["errors"],
            transient_errors=int(result.get("transient_errors", 0)),
            terminal_errors=int(result.get("terminal_errors", 0)),
            sources_failed=int(result.get("sources_failed", 0)),
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.collect_gdelt",
        runner=_runner,
    )


@typed_shared_task(name="workers.check_source_freshness")
def check_source_freshness() -> dict[str, Any]:
    """Evaluate source freshness SLOs and trigger bounded catch-up dispatch."""

    def _runner() -> dict[str, Any]:
        logger.info("Starting source freshness check task")
        result = _run_async(_check_source_freshness_async())
        logger.info(
            "Finished source freshness check task",
            stale_count=result["stale_count"],
            stale_collectors=result["stale_collectors"],
            catchup_dispatched=result["catchup_dispatched"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.check_source_freshness",
        runner=_runner,
    )


@typed_shared_task(name="workers.ping")
def ping() -> dict[str, Any]:
    """Simple task to verify worker is up and processing jobs."""

    def _runner() -> dict[str, str]:
        return {
            "status": "ok",
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

    return _run_task_with_heartbeat(
        task_name="workers.ping",
        runner=_runner,
    )
