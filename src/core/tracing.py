"""
OpenTelemetry tracing bootstrap and Celery trace-context propagation.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import TYPE_CHECKING, Any, cast

import structlog
from celery.signals import before_task_publish, task_postrun, task_prerun

from src.core.config import settings

if TYPE_CHECKING:
    from celery import Celery
    from fastapi import FastAPI

logger = structlog.get_logger(__name__)

try:
    from opentelemetry import context as _otel_context
    from opentelemetry import propagate as _otel_propagate
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as _OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.celery import CeleryInstrumentor as _CeleryInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor as _FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import (
        HTTPXClientInstrumentor as _HTTPXClientInstrumentor,
    )
    from opentelemetry.instrumentation.redis import RedisInstrumentor as _RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor as _SQLAlchemyInstrumentor,
    )
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor as _BatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter as _ConsoleSpanExporter,
    )
    from opentelemetry.sdk.trace.sampling import (
        ParentBased as _ParentBased,
    )
    from opentelemetry.sdk.trace.sampling import (
        TraceIdRatioBased as _TraceIdRatioBased,
    )

    _OTEL_AVAILABLE = True
    _OTEL_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency optional in local dev
    _OTEL_AVAILABLE = False
    _OTEL_IMPORT_ERROR = exc
    _otel_context = None
    _otel_propagate = None
    _otel_trace = None
    _OTLPSpanExporter = None
    _CeleryInstrumentor = None
    _FastAPIInstrumentor = None
    _HTTPXClientInstrumentor = None
    _RedisInstrumentor = None
    _SQLAlchemyInstrumentor = None
    _Resource = None
    _TracerProvider = None
    _BatchSpanProcessor = None
    _ConsoleSpanExporter = None
    _ParentBased = None
    _TraceIdRatioBased = None


_provider_initialized = False
_shared_instrumentation_initialized = False
_celery_instrumentation_initialized = False
_celery_context_hooks_registered = False
_instrumented_fastapi_app_ids: set[int] = set()
_missing_dependencies_logged = False


def _parse_otlp_headers(headers_raw: str | None) -> dict[str, str] | None:
    if not headers_raw:
        return None

    parsed: dict[str, str] = {}
    for raw_pair in headers_raw.split(","):
        pair = raw_pair.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            parsed[normalized_key] = normalized_value
    return parsed or None


def _log_missing_otel_dependencies_once() -> None:
    global _missing_dependencies_logged
    if _missing_dependencies_logged:
        return
    _missing_dependencies_logged = True
    logger.warning(
        "OpenTelemetry tracing enabled but dependencies are unavailable",
        error=str(_OTEL_IMPORT_ERROR) if _OTEL_IMPORT_ERROR is not None else None,
    )


def _initialize_tracer_provider() -> None:
    global _provider_initialized
    if _provider_initialized:
        return

    assert _TracerProvider is not None  # nosec B101
    assert _Resource is not None  # nosec B101
    assert _ParentBased is not None  # nosec B101
    assert _TraceIdRatioBased is not None  # nosec B101
    assert _BatchSpanProcessor is not None  # nosec B101
    assert _ConsoleSpanExporter is not None  # nosec B101

    provider = _TracerProvider(
        resource=_Resource.create(
            {
                "service.name": settings.OTEL_SERVICE_NAME,
                "service.namespace": settings.OTEL_SERVICE_NAMESPACE,
                "deployment.environment": settings.ENVIRONMENT,
            }
        ),
        sampler=_ParentBased(_TraceIdRatioBased(settings.OTEL_TRACES_SAMPLER_RATIO)),
    )

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT and _OTLPSpanExporter is not None:
        exporter = _OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            headers=_parse_otlp_headers(settings.OTEL_EXPORTER_OTLP_HEADERS),
        )
    else:
        exporter = _ConsoleSpanExporter()
    provider.add_span_processor(_BatchSpanProcessor(exporter))

    assert _otel_trace is not None  # nosec B101
    _otel_trace.set_tracer_provider(provider)
    _provider_initialized = True
    logger.info(
        "OpenTelemetry tracer provider configured",
        service_name=settings.OTEL_SERVICE_NAME,
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT or "console",
    )


def _initialize_shared_instrumentation() -> None:
    global _shared_instrumentation_initialized
    if _shared_instrumentation_initialized:
        return

    assert _HTTPXClientInstrumentor is not None  # nosec B101
    assert _RedisInstrumentor is not None  # nosec B101
    assert _SQLAlchemyInstrumentor is not None  # nosec B101

    _HTTPXClientInstrumentor().instrument()
    _RedisInstrumentor().instrument()

    from src.storage.database import engine

    _SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    _shared_instrumentation_initialized = True


def _instrument_fastapi_app(fastapi_app: FastAPI) -> None:
    assert _FastAPIInstrumentor is not None  # nosec B101
    app_id = id(fastapi_app)
    if app_id in _instrumented_fastapi_app_ids:
        return
    _FastAPIInstrumentor.instrument_app(fastapi_app)
    _instrumented_fastapi_app_ids.add(app_id)


def _initialize_celery_instrumentation(_celery_app: Celery) -> None:
    global _celery_instrumentation_initialized
    if _celery_instrumentation_initialized:
        return

    assert _CeleryInstrumentor is not None  # nosec B101
    _CeleryInstrumentor().instrument()
    _celery_instrumentation_initialized = True


def inject_trace_context(headers: MutableMapping[str, Any]) -> None:
    if not (settings.OTEL_ENABLED and _OTEL_AVAILABLE):
        return
    assert _otel_propagate is not None  # nosec B101
    _otel_propagate.inject(carrier=headers)


def attach_trace_context(headers: Mapping[str, Any]) -> object | None:
    if not (settings.OTEL_ENABLED and _OTEL_AVAILABLE):
        return None
    assert _otel_propagate is not None  # nosec B101
    assert _otel_context is not None  # nosec B101
    context = _otel_propagate.extract(carrier=headers)
    return cast("object", _otel_context.attach(context))


def detach_trace_context(token: object | None) -> None:
    if token is None or not (settings.OTEL_ENABLED and _OTEL_AVAILABLE):
        return
    assert _otel_context is not None  # nosec B101
    _otel_context.detach(token)


def _before_task_publish_trace(*, headers: dict[str, Any] | None = None, **_: Any) -> None:
    if headers is None:
        return
    inject_trace_context(headers)


def _task_prerun_trace(*, task: Any = None, **_: Any) -> None:
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None)
    if not isinstance(headers, Mapping):
        return
    token = attach_trace_context(headers)
    if token is not None and request is not None:
        request._otel_trace_token = token


def _task_postrun_trace(*, task: Any = None, **_: Any) -> None:
    request = getattr(task, "request", None)
    token = getattr(request, "_otel_trace_token", None)
    if token is None:
        return
    detach_trace_context(token)
    if request is None:
        return
    request._otel_trace_token = None


def _register_celery_context_hooks() -> None:
    global _celery_context_hooks_registered
    if _celery_context_hooks_registered:
        return

    before_task_publish.connect(_before_task_publish_trace, weak=False)
    task_prerun.connect(_task_prerun_trace, weak=False)
    task_postrun.connect(_task_postrun_trace, weak=False)
    _celery_context_hooks_registered = True


def configure_tracing(
    *, fastapi_app: FastAPI | None = None, celery_app: Celery | None = None
) -> None:
    if not settings.OTEL_ENABLED:
        return
    if not _OTEL_AVAILABLE:
        _log_missing_otel_dependencies_once()
        return

    _initialize_tracer_provider()
    _initialize_shared_instrumentation()

    if fastapi_app is not None:
        _instrument_fastapi_app(fastapi_app)

    if celery_app is not None:
        _initialize_celery_instrumentation(celery_app)
        _register_celery_context_hooks()
