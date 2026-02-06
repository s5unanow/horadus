"""
Celery tasks for ingestion collection.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

import httpx
import redis
import structlog
from celery import shared_task
from celery.signals import task_failure

from src.core.config import settings
from src.ingestion.gdelt_client import GDELTClient
from src.ingestion.rss_collector import RSSCollector
from src.storage.database import async_session_maker

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
    if not settings.ENABLE_RSS_INGESTION:
        return {"status": "disabled", "collector": "rss"}

    logger.info("Starting RSS collection task")
    result = _run_async(_collect_rss_async())
    logger.info(
        "Finished RSS collection task",
        stored=result["stored"],
        skipped=result["skipped"],
        errors=result["errors"],
    )
    return result


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
    if not settings.ENABLE_GDELT_INGESTION:
        return {"status": "disabled", "collector": "gdelt"}

    logger.info("Starting GDELT collection task")
    result = _run_async(_collect_gdelt_async())
    logger.info(
        "Finished GDELT collection task",
        stored=result["stored"],
        skipped=result["skipped"],
        errors=result["errors"],
    )
    return result


@typed_shared_task(name="workers.ping")
def ping() -> dict[str, str]:
    """Simple task to verify worker is up and processing jobs."""
    return {
        "status": "ok",
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }
