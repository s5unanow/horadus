"""
Celery tasks for ingestion collection and processing orchestration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import redis
import structlog
from celery import shared_task
from celery.signals import task_failure
from sqlalchemy import delete, func, select

from src.core.cluster_drift import (
    ClusterDriftThresholds,
    ClusterEventSample,
    compute_cluster_drift_summary,
    load_latest_language_distribution,
    write_cluster_drift_artifact,
)
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
from src.processing.degraded_llm_tracker import DegradedLLMTracker
from src.processing.event_lifecycle import EventLifecycleManager
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.processing.tier2_canary import run_tier2_canary
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.database import async_session_maker
from src.storage.models import (
    Event,
    EventItem,
    EventLifecycle,
    LLMReplayQueueItem,
    ProcessingStatus,
    RawItem,
    Trend,
    TrendEvidence,
    TrendSnapshot,
)
from src.workers import _task_collectors as collector_helpers
from src.workers import _task_maintenance as maintenance_helpers
from src.workers import _task_processing as processing_helpers
from src.workers import _task_retention as retention_helpers
from src.workers import _task_shared as shared_helpers

logger = structlog.get_logger(__name__)

DEAD_LETTER_KEY = "celery:dead_letter"
DEAD_LETTER_MAX_ITEMS = 1000
PROCESSING_IN_FLIGHT_KEY = "horadus:processing:in_flight"
PROCESSING_DISPATCH_LOCK_KEY = "horadus:processing:dispatch_lock"

CollectorTransientRunError = shared_helpers.CollectorTransientRunError
ProcessingDispatchPlan = processing_helpers.ProcessingDispatchPlan
RetentionCutoffs = retention_helpers.RetentionCutoffs


def _deps() -> SimpleNamespace:
    return SimpleNamespace(
        asyncio=asyncio,
        httpx=httpx,
        redis=redis,
        logger=logger,
        settings=settings,
        delete=delete,
        func=func,
        select=select,
        ClusterDriftThresholds=ClusterDriftThresholds,
        ClusterEventSample=ClusterEventSample,
        compute_cluster_drift_summary=compute_cluster_drift_summary,
        load_latest_language_distribution=load_latest_language_distribution,
        write_cluster_drift_artifact=write_cluster_drift_artifact,
        record_collector_metrics=record_collector_metrics,
        record_pipeline_metrics=record_pipeline_metrics,
        record_processing_backlog_depth=record_processing_backlog_depth,
        record_processing_dispatch_decision=record_processing_dispatch_decision,
        record_processing_reaper_resets=record_processing_reaper_resets,
        record_retention_cleanup_rows=record_retention_cleanup_rows,
        record_retention_cleanup_run=record_retention_cleanup_run,
        record_source_catchup_dispatch=record_source_catchup_dispatch,
        record_source_freshness_stale=record_source_freshness_stale,
        record_worker_error=record_worker_error,
        ReportGenerator=ReportGenerator,
        build_source_freshness_report=build_source_freshness_report,
        TrendEngine=TrendEngine,
        GDELTClient=GDELTClient,
        RSSCollector=RSSCollector,
        CostTracker=CostTracker,
        DegradedLLMTracker=DegradedLLMTracker,
        EventLifecycleManager=EventLifecycleManager,
        ProcessingPipeline=ProcessingPipeline,
        run_tier2_canary=run_tier2_canary,
        Tier2Classifier=Tier2Classifier,
        async_session_maker=async_session_maker,
        Event=Event,
        EventItem=EventItem,
        EventLifecycle=EventLifecycle,
        LLMReplayQueueItem=LLMReplayQueueItem,
        ProcessingStatus=ProcessingStatus,
        RawItem=RawItem,
        Trend=Trend,
        TrendEvidence=TrendEvidence,
        TrendSnapshot=TrendSnapshot,
        DEAD_LETTER_KEY=DEAD_LETTER_KEY,
        DEAD_LETTER_MAX_ITEMS=DEAD_LETTER_MAX_ITEMS,
        PROCESSING_IN_FLIGHT_KEY=PROCESSING_IN_FLIGHT_KEY,
        PROCESSING_DISPATCH_LOCK_KEY=PROCESSING_DISPATCH_LOCK_KEY,
        _push_dead_letter=_push_dead_letter,
        _record_worker_activity=_record_worker_activity,
        _run_async=_run_async,
        _build_processing_dispatch_plan=_build_processing_dispatch_plan,
        _get_redis_client=_get_redis_client,
        _get_processing_in_flight_count=_get_processing_in_flight_count,
        _acquire_processing_dispatch_lock=_acquire_processing_dispatch_lock,
        _load_processing_dispatch_inputs_async=_load_processing_dispatch_inputs_async,
        _build_retention_cutoffs=_build_retention_cutoffs,
        _select_noise_raw_item_ids=_select_noise_raw_item_ids,
        _select_archived_event_raw_item_ids=_select_archived_event_raw_item_ids,
        _select_trend_evidence_ids=_select_trend_evidence_ids,
        process_pending_items=process_pending_items,
        collect_rss=collect_rss,
        collect_gdelt=collect_gdelt,
    )


def typed_shared_task(*task_args: Any, **task_kwargs: Any) -> Callable[[Any], Any]:
    return shared_helpers.typed_shared_task(
        *task_args,
        shared_task_decorator=shared_task,
        **task_kwargs,
    )


def _run_async(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    return shared_helpers.run_async(asyncio_module=asyncio, coro=coro)


def _should_requeue_collector_run(result: dict[str, Any]) -> bool:
    return shared_helpers.should_requeue_collector_run(result)


def _push_dead_letter(payload: dict[str, Any]) -> None:
    shared_helpers.push_dead_letter(deps=_deps(), payload=payload)


def _record_worker_activity(
    *,
    task_name: str,
    status: str,
    error: str | None = None,
) -> None:
    shared_helpers.record_worker_activity(
        deps=_deps(),
        task_name=task_name,
        status=status,
        error=error,
    )


def _run_task_with_heartbeat(
    *,
    task_name: str,
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return shared_helpers.run_task_with_heartbeat(
        deps=_deps(),
        task_name=task_name,
        runner=runner,
    )


def _handle_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    shared_helpers.handle_task_failure(
        deps=_deps(),
        sender=sender,
        task_id=task_id,
        exception=exception,
        args=args,
        kwargs=kwargs,
        **extra,
    )


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
    return processing_helpers.build_processing_dispatch_plan(
        deps=_deps(),
        stored_items=stored_items,
        pending_backlog=pending_backlog,
        in_flight=in_flight,
        budget_status=budget_status,
        budget_remaining_usd=budget_remaining_usd,
        daily_cost_limit_usd=daily_cost_limit_usd,
    )


def _get_redis_client() -> redis.Redis[str]:
    return cast("redis.Redis[str]", processing_helpers.get_redis_client(deps=_deps()))


def _get_processing_in_flight_count() -> int:
    return processing_helpers.get_processing_in_flight_count(deps=_deps())


def _increment_processing_in_flight() -> int:
    return processing_helpers.increment_processing_in_flight(deps=_deps())


def _decrement_processing_in_flight() -> int:
    return processing_helpers.decrement_processing_in_flight(deps=_deps())


def _acquire_processing_dispatch_lock() -> bool:
    return processing_helpers.acquire_processing_dispatch_lock(deps=_deps())


async def _load_processing_dispatch_inputs_async() -> dict[str, Any]:
    return await processing_helpers.load_processing_dispatch_inputs_async(deps=_deps())


async def _collect_rss_async() -> dict[str, Any]:
    return await collector_helpers.collect_rss_async(deps=_deps())


async def _collect_gdelt_async() -> dict[str, Any]:
    return await collector_helpers.collect_gdelt_async(deps=_deps())


async def _check_source_freshness_async() -> dict[str, Any]:
    return await collector_helpers.check_source_freshness_async(deps=_deps())


async def _monitor_cluster_drift_async() -> dict[str, Any]:
    return await collector_helpers.monitor_cluster_drift_async(deps=_deps())


def _queue_processing_for_new_items(*, collector: str, stored_items: int) -> bool:
    return processing_helpers.queue_processing_for_new_items(
        deps=_deps(),
        collector=collector,
        stored_items=stored_items,
    )


async def _process_pending_async(limit: int) -> dict[str, Any]:
    return await processing_helpers.process_pending_async(deps=_deps(), limit=limit)


async def _reap_stale_processing_async() -> dict[str, Any]:
    return await processing_helpers.reap_stale_processing_async(deps=_deps())


async def _snapshot_trends_async() -> dict[str, Any]:
    return await maintenance_helpers.snapshot_trends_async(deps=_deps())


async def _decay_trends_async() -> dict[str, Any]:
    return await maintenance_helpers.decay_trends_async(deps=_deps())


async def _check_event_lifecycles_async() -> dict[str, Any]:
    return await maintenance_helpers.check_event_lifecycles_async(deps=_deps())


def _build_retention_cutoffs(*, dry_run: bool | None = None) -> RetentionCutoffs:
    return retention_helpers.build_retention_cutoffs(deps=_deps(), dry_run=dry_run)


def _is_raw_item_noise_retention_eligible(
    *,
    processing_status: ProcessingStatus,
    fetched_at: datetime,
    has_event_link: bool,
    cutoffs: RetentionCutoffs,
) -> bool:
    return retention_helpers.is_raw_item_noise_retention_eligible(
        processing_status=processing_status,
        fetched_at=fetched_at,
        has_event_link=has_event_link,
        cutoffs=cutoffs,
        noise_status=ProcessingStatus.NOISE,
        error_status=ProcessingStatus.ERROR,
    )


def _is_raw_item_archived_event_retention_eligible(
    *,
    fetched_at: datetime,
    event_lifecycle_status: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    return retention_helpers.is_raw_item_archived_event_retention_eligible(
        fetched_at=fetched_at,
        event_lifecycle_status=event_lifecycle_status,
        event_last_mention_at=event_last_mention_at,
        cutoffs=cutoffs,
        archived_status=EventLifecycle.ARCHIVED.value,
    )


def _is_trend_evidence_retention_eligible(
    *,
    created_at: datetime,
    event_lifecycle_status: str,
    event_last_mention_at: datetime | None,
    cutoffs: RetentionCutoffs,
) -> bool:
    return retention_helpers.is_trend_evidence_retention_eligible(
        created_at=created_at,
        event_lifecycle_status=event_lifecycle_status,
        event_last_mention_at=event_last_mention_at,
        cutoffs=cutoffs,
        archived_status=EventLifecycle.ARCHIVED.value,
    )


def _is_archived_event_retention_eligible(
    *,
    lifecycle_status: str,
    last_mention_at: datetime,
    has_remaining_evidence: bool,
    cutoffs: RetentionCutoffs,
) -> bool:
    return retention_helpers.is_archived_event_retention_eligible(
        lifecycle_status=lifecycle_status,
        last_mention_at=last_mention_at,
        has_remaining_evidence=has_remaining_evidence,
        cutoffs=cutoffs,
        archived_status=EventLifecycle.ARCHIVED.value,
    )


async def _select_noise_raw_item_ids(*, batch_size: int, cutoff: datetime) -> list[Any]:
    return await retention_helpers.select_noise_raw_item_ids(
        deps=_deps(),
        batch_size=batch_size,
        cutoff=cutoff,
    )


async def _select_archived_event_raw_item_ids(
    *,
    batch_size: int,
    cutoff: datetime,
) -> list[Any]:
    return await retention_helpers.select_archived_event_raw_item_ids(
        deps=_deps(),
        batch_size=batch_size,
        cutoff=cutoff,
    )


async def _select_trend_evidence_ids(
    *,
    batch_size: int,
    evidence_cutoff: datetime,
    archived_event_cutoff: datetime,
) -> list[Any]:
    return await retention_helpers.select_trend_evidence_ids(
        deps=_deps(),
        batch_size=batch_size,
        evidence_cutoff=evidence_cutoff,
        archived_event_cutoff=archived_event_cutoff,
    )


async def _run_data_retention_cleanup_async(*, dry_run: bool | None = None) -> dict[str, Any]:
    return await retention_helpers.run_data_retention_cleanup_async(
        deps=_deps(),
        dry_run=dry_run,
    )


async def _generate_weekly_reports_async() -> dict[str, Any]:
    return await maintenance_helpers.generate_weekly_reports_async(deps=_deps())


async def _generate_monthly_reports_async() -> dict[str, Any]:
    return await maintenance_helpers.generate_monthly_reports_async(deps=_deps())


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
                degraded_llm=result.get("degraded_llm"),
                degraded_holds=result.get("degraded_holds"),
                replay_enqueued=result.get("replay_enqueued"),
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


async def _replay_degraded_events_async(limit: int) -> dict[str, Any]:
    return await maintenance_helpers.replay_degraded_events_async(deps=_deps(), limit=limit)


@typed_shared_task(name="workers.replay_degraded_events")
def replay_degraded_events(limit: int | None = None) -> dict[str, Any]:
    """Drain bounded degraded-mode replay queue when primary Tier-2 is healthy."""

    def _runner() -> dict[str, Any]:
        configured = max(1, int(settings.LLM_DEGRADED_REPLAY_DRAIN_LIMIT))
        run_limit = max(1, int(limit or configured))
        logger.info("Starting degraded replay task", limit=run_limit)
        result = _run_async(_replay_degraded_events_async(limit=run_limit))
        logger.info(
            "Finished degraded replay task",
            drained=result.get("drained"),
            errors=result.get("errors"),
            status=result.get("status"),
            reason=result.get("reason"),
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.replay_degraded_events",
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


@typed_shared_task(name="workers.monitor_cluster_drift")
def monitor_cluster_drift() -> dict[str, Any]:
    """Compute warn-only clustering drift proxies and persist daily artifact."""

    def _runner() -> dict[str, Any]:
        logger.info(
            "Starting cluster drift sentinel task",
            lookback_days=settings.CLUSTER_DRIFT_SENTINEL_LOOKBACK_DAYS,
        )
        result = _run_async(_monitor_cluster_drift_async())
        logger.info(
            "Finished cluster drift sentinel task",
            event_count=result["event_count"],
            warning_keys=result["warning_keys"],
            artifact_path=result["artifact_path"],
        )
        return result

    return _run_task_with_heartbeat(
        task_name="workers.monitor_cluster_drift",
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


__all__ = [
    "CollectorTransientRunError",
    "ProcessingDispatchPlan",
    "RetentionCutoffs",
    "apply_trend_decay",
    "check_event_lifecycles",
    "check_source_freshness",
    "collect_gdelt",
    "collect_rss",
    "generate_monthly_reports",
    "generate_weekly_reports",
    "monitor_cluster_drift",
    "ping",
    "process_pending_items",
    "reap_stale_processing_items",
    "replay_degraded_events",
    "run_data_retention_cleanup",
    "snapshot_trends",
]
