from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Any])


class CollectorTransientRunError(RuntimeError):
    """Raised when a collector run should be requeued for transient outages."""


def typed_shared_task(
    *task_args: Any,
    shared_task_decorator: Callable[..., Any],
    **task_kwargs: Any,
) -> Callable[[TaskFunc], TaskFunc]:
    """
    Typed wrapper around Celery's shared_task decorator.

    Celery decorators are untyped, which conflicts with strict mypy settings.
    """
    decorator = shared_task_decorator(*task_args, **task_kwargs)
    return cast("Callable[[TaskFunc], TaskFunc]", decorator)


def run_async(
    *,
    asyncio_module: Any,
    coro: Coroutine[Any, Any, dict[str, Any]],
) -> dict[str, Any]:
    return cast("dict[str, Any]", asyncio_module.run(coro))


def should_requeue_collector_run(result: dict[str, Any]) -> bool:
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


def push_dead_letter(*, deps: Any, payload: dict[str, Any]) -> None:
    client: Any | None = None
    try:
        client = deps.redis.from_url(deps.settings.REDIS_URL, decode_responses=True)
        client.lpush(deps.DEAD_LETTER_KEY, json.dumps(payload))
        client.ltrim(deps.DEAD_LETTER_KEY, 0, deps.DEAD_LETTER_MAX_ITEMS - 1)
    except Exception:
        deps.logger.exception("Failed to push dead letter payload")
    finally:
        if client is not None:
            client.close()


def record_worker_activity(
    *,
    deps: Any,
    task_name: str,
    status: str,
    error: str | None = None,
) -> None:
    client: Any | None = None
    try:
        client = deps.redis.from_url(deps.settings.REDIS_URL, decode_responses=True)
        payload = {
            "task": task_name,
            "status": status,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        if error:
            payload["error"] = error[:500]
        client.set(
            deps.settings.WORKER_HEARTBEAT_REDIS_KEY,
            json.dumps(payload),
            ex=max(60, deps.settings.WORKER_HEARTBEAT_TTL_SECONDS),
        )
    except Exception:
        deps.logger.exception(
            "Failed to record worker heartbeat",
            task_name=task_name,
            status=status,
        )
    finally:
        if client is not None:
            client.close()


def run_task_with_heartbeat(
    *,
    deps: Any,
    task_name: str,
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    deps._record_worker_activity(task_name=task_name, status="started")
    try:
        result = runner()
    except Exception as exc:
        deps._record_worker_activity(task_name=task_name, status="failed", error=str(exc))
        raise
    deps._record_worker_activity(task_name=task_name, status="ok")
    return result


def handle_task_failure(
    *,
    deps: Any,
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
    deps.record_worker_error(task_name=str(payload["task_name"]))
    deps._push_dead_letter(payload)
