"""
Celery tasks for ingestion collection and processing orchestration.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar, cast

import httpx
import redis
import structlog
from celery import shared_task
from celery.signals import task_failure
from sqlalchemy import select

from src.core.config import settings
from src.core.observability import (
    record_collector_metrics,
    record_pipeline_metrics,
    record_processing_reaper_resets,
    record_worker_error,
)
from src.core.report_generator import ReportGenerator
from src.core.trend_engine import TrendEngine
from src.ingestion.gdelt_client import GDELTClient
from src.ingestion.rss_collector import RSSCollector
from src.processing.event_lifecycle import EventLifecycleManager
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.storage.database import async_session_maker
from src.storage.models import ProcessingStatus, RawItem, Trend, TrendSnapshot

logger = structlog.get_logger(__name__)

DEAD_LETTER_KEY = "celery:dead_letter"
DEAD_LETTER_MAX_ITEMS = 1000

TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Any])


def typed_shared_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskFunc], TaskFunc]:
    """
    Typed wrapper around Celery's shared_task decorator.

    Celery decorators are untyped, which conflicts with strict mypy settings.
    """
    decorator = shared_task(*task_args, **task_kwargs)
    return cast("Callable[[TaskFunc], TaskFunc]", decorator)


def _run_async(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    return asyncio.run(coro)


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
        "results": [asdict(result) for result in results],
    }


def _queue_processing_for_new_items(*, collector: str, stored_items: int) -> bool:
    if stored_items <= 0:
        return False
    if not settings.ENABLE_PROCESSING_PIPELINE:
        return False

    queue_limit = max(1, settings.PROCESSING_PIPELINE_BATCH_SIZE)
    task_limit = min(stored_items, queue_limit)
    cast("Any", process_pending_items).delay(limit=task_limit)
    logger.info(
        "Queued processing pipeline task",
        collector=collector,
        stored_items=stored_items,
        task_limit=task_limit,
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

        logger.info("Starting processing pipeline task", limit=run_limit)
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
    autoretry_for=(httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
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
        _queue_processing_for_new_items(collector="rss", stored_items=int(result["stored"]))
        logger.info(
            "Finished RSS collection task",
            stored=result["stored"],
            skipped=result["skipped"],
            errors=result["errors"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.collect_rss",
        runner=_runner,
    )


@typed_shared_task(
    name="workers.collect_gdelt",
    autoretry_for=(httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
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
        _queue_processing_for_new_items(collector="gdelt", stored_items=int(result["stored"]))
        logger.info(
            "Finished GDELT collection task",
            stored=result["stored"],
            skipped=result["skipped"],
            errors=result["errors"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.collect_gdelt",
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
