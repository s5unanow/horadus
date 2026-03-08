from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import src.storage.database as database_module
from src.core import tracing as tracing_module

pytestmark = pytest.mark.unit


def test_parse_otlp_headers_parses_valid_pairs_and_skips_invalid_entries() -> None:
    assert tracing_module._parse_otlp_headers(None) is None
    assert tracing_module._parse_otlp_headers(" , invalid, key = value , x=y=z , blank= ") == {
        "key": "value",
        "x": "y=z",
    }


def test_log_missing_otel_dependencies_logs_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()

    monkeypatch.setattr(tracing_module, "logger", logger)
    monkeypatch.setattr(tracing_module, "_missing_dependencies_logged", False)
    monkeypatch.setattr(tracing_module, "_OTEL_IMPORT_ERROR", RuntimeError("missing otel"))

    tracing_module._log_missing_otel_dependencies_once()
    tracing_module._log_missing_otel_dependencies_once()

    logger.warning.assert_called_once_with(
        "OpenTelemetry tracing enabled but dependencies are unavailable",
        error="missing otel",
    )


def test_initialize_tracer_provider_uses_otlp_exporter_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    provider = MagicMock()
    tracer_provider = MagicMock(return_value=provider)
    batch_processor = MagicMock(side_effect=lambda exporter: ("batch", exporter))
    otlp_exporter = MagicMock(return_value="otlp-exporter")
    console_exporter = MagicMock(return_value="console-exporter")
    set_tracer_provider = MagicMock()

    monkeypatch.setattr(tracing_module, "logger", logger)
    monkeypatch.setattr(tracing_module, "_provider_initialized", False)
    monkeypatch.setattr(tracing_module, "_TracerProvider", tracer_provider)
    monkeypatch.setattr(
        tracing_module, "_Resource", SimpleNamespace(create=MagicMock(return_value="resource"))
    )
    monkeypatch.setattr(
        tracing_module, "_ParentBased", MagicMock(side_effect=lambda sampler: ("parent", sampler))
    )
    monkeypatch.setattr(
        tracing_module,
        "_TraceIdRatioBased",
        MagicMock(side_effect=lambda ratio: ("ratio", ratio)),
    )
    monkeypatch.setattr(tracing_module, "_BatchSpanProcessor", batch_processor)
    monkeypatch.setattr(tracing_module, "_ConsoleSpanExporter", console_exporter)
    monkeypatch.setattr(tracing_module, "_OTLPSpanExporter", otlp_exporter)
    monkeypatch.setattr(
        tracing_module,
        "_otel_trace",
        SimpleNamespace(set_tracer_provider=set_tracer_provider),
    )
    monkeypatch.setattr(tracing_module.settings, "OTEL_SERVICE_NAME", "horadus-api")
    monkeypatch.setattr(tracing_module.settings, "OTEL_SERVICE_NAMESPACE", "intel")
    monkeypatch.setattr(tracing_module.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(tracing_module.settings, "OTEL_TRACES_SAMPLER_RATIO", 0.25)
    monkeypatch.setattr(tracing_module.settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel")
    monkeypatch.setattr(
        tracing_module.settings,
        "OTEL_EXPORTER_OTLP_HEADERS",
        "Authorization=Bearer token, project = alpha ",
    )

    tracing_module._initialize_tracer_provider()
    tracing_module._initialize_tracer_provider()

    otlp_exporter.assert_called_once_with(
        endpoint="http://otel",
        headers={"Authorization": "Bearer token", "project": "alpha"},
    )
    console_exporter.assert_not_called()
    provider.add_span_processor.assert_called_once_with(("batch", "otlp-exporter"))
    set_tracer_provider.assert_called_once_with(provider)
    logger.info.assert_called_once_with(
        "OpenTelemetry tracer provider configured",
        service_name="horadus-api",
        endpoint="http://otel",
    )


def test_initialize_tracer_provider_uses_console_exporter_when_no_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock()

    monkeypatch.setattr(tracing_module, "_provider_initialized", False)
    monkeypatch.setattr(tracing_module, "_TracerProvider", MagicMock(return_value=provider))
    monkeypatch.setattr(
        tracing_module, "_Resource", SimpleNamespace(create=MagicMock(return_value="resource"))
    )
    monkeypatch.setattr(
        tracing_module, "_ParentBased", MagicMock(side_effect=lambda sampler: ("parent", sampler))
    )
    monkeypatch.setattr(
        tracing_module,
        "_TraceIdRatioBased",
        MagicMock(side_effect=lambda ratio: ("ratio", ratio)),
    )
    monkeypatch.setattr(
        tracing_module,
        "_BatchSpanProcessor",
        MagicMock(side_effect=lambda exporter: ("batch", exporter)),
    )
    console_exporter = MagicMock(return_value="console-exporter")
    monkeypatch.setattr(tracing_module, "_ConsoleSpanExporter", console_exporter)
    monkeypatch.setattr(tracing_module, "_OTLPSpanExporter", None)
    monkeypatch.setattr(
        tracing_module,
        "_otel_trace",
        SimpleNamespace(set_tracer_provider=MagicMock()),
    )
    monkeypatch.setattr(tracing_module.settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setattr(tracing_module.settings, "OTEL_EXPORTER_OTLP_HEADERS", None)

    tracing_module._initialize_tracer_provider()

    console_exporter.assert_called_once_with()
    provider.add_span_processor.assert_called_once_with(("batch", "console-exporter"))


def test_initialize_shared_instrumentation_instruments_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    httpx_instrumentor = MagicMock()
    redis_instrumentor = MagicMock()
    sqlalchemy_instrumentor = MagicMock()

    monkeypatch.setattr(tracing_module, "_shared_instrumentation_initialized", False)
    monkeypatch.setattr(
        tracing_module, "_HTTPXClientInstrumentor", MagicMock(return_value=httpx_instrumentor)
    )
    monkeypatch.setattr(
        tracing_module, "_RedisInstrumentor", MagicMock(return_value=redis_instrumentor)
    )
    monkeypatch.setattr(
        tracing_module,
        "_SQLAlchemyInstrumentor",
        MagicMock(return_value=sqlalchemy_instrumentor),
    )
    monkeypatch.setattr(database_module, "engine", SimpleNamespace(sync_engine="sync-engine"))

    tracing_module._initialize_shared_instrumentation()
    tracing_module._initialize_shared_instrumentation()

    httpx_instrumentor.instrument.assert_called_once_with()
    redis_instrumentor.instrument.assert_called_once_with()
    sqlalchemy_instrumentor.instrument.assert_called_once_with(engine="sync-engine")


def test_instrument_fastapi_app_instruments_each_app_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instrument_app = MagicMock()
    fastapi_app = object()

    monkeypatch.setattr(
        tracing_module, "_FastAPIInstrumentor", SimpleNamespace(instrument_app=instrument_app)
    )
    monkeypatch.setattr(tracing_module, "_instrumented_fastapi_app_ids", set())

    tracing_module._instrument_fastapi_app(fastapi_app)
    tracing_module._instrument_fastapi_app(fastapi_app)
    tracing_module._instrument_fastapi_app(object())

    assert instrument_app.call_count == 2


def test_initialize_celery_instrumentation_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    celery_instrumentor = MagicMock()

    monkeypatch.setattr(tracing_module, "_celery_instrumentation_initialized", False)
    monkeypatch.setattr(
        tracing_module, "_CeleryInstrumentor", MagicMock(return_value=celery_instrumentor)
    )

    tracing_module._initialize_celery_instrumentation(object())
    tracing_module._initialize_celery_instrumentation(object())

    celery_instrumentor.instrument.assert_called_once_with()


def test_trace_context_helpers_use_propagator_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tracing_module.settings, "OTEL_ENABLED", True)
    monkeypatch.setattr(tracing_module, "_OTEL_AVAILABLE", True)

    injected_headers: dict[str, str] = {}
    attached_contexts: list[object] = []
    detached_tokens: list[object] = []

    def fake_inject(*, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = "00-abc123-def456-01"
        injected_headers.update(carrier)

    def fake_extract(*, carrier: dict[str, str]) -> dict[str, str]:
        return {"traceparent": carrier["traceparent"]}

    def fake_attach(context: object) -> str:
        attached_contexts.append(context)
        return "token-1"

    def fake_detach(token: object) -> None:
        detached_tokens.append(token)

    monkeypatch.setattr(
        tracing_module,
        "_otel_propagate",
        SimpleNamespace(inject=fake_inject, extract=fake_extract),
    )
    monkeypatch.setattr(
        tracing_module,
        "_otel_context",
        SimpleNamespace(attach=fake_attach, detach=fake_detach),
    )

    headers: dict[str, str] = {}
    tracing_module.inject_trace_context(headers)
    token = tracing_module.attach_trace_context(headers)
    tracing_module.detach_trace_context(token)

    assert injected_headers["traceparent"] == "00-abc123-def456-01"
    assert attached_contexts == [{"traceparent": "00-abc123-def456-01"}]
    assert detached_tokens == ["token-1"]


def test_task_trace_signal_hooks_attach_and_detach_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens: list[object] = []
    request = SimpleNamespace(headers={"traceparent": "00-a-b-01"}, _otel_trace_token=None)
    task = SimpleNamespace(request=request)

    monkeypatch.setattr(tracing_module, "attach_trace_context", lambda _headers: "token-2")
    monkeypatch.setattr(tracing_module, "detach_trace_context", lambda token: tokens.append(token))

    tracing_module._task_prerun_trace(task=task)
    assert request._otel_trace_token == "token-2"

    tracing_module._task_postrun_trace(task=task)
    assert tokens == ["token-2"]
    assert request._otel_trace_token is None


def test_before_task_publish_injects_into_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[dict[str, object]] = []

    def fake_inject(headers: dict[str, object]) -> None:
        headers["traceparent"] = "00-1-2-01"
        observed.append(dict(headers))

    monkeypatch.setattr(tracing_module, "inject_trace_context", fake_inject)

    headers: dict[str, object] = {"existing": "value"}
    tracing_module._before_task_publish_trace(headers=headers)

    assert observed == [{"existing": "value", "traceparent": "00-1-2-01"}]


def test_before_task_publish_noops_without_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    inject = MagicMock()
    monkeypatch.setattr(tracing_module, "inject_trace_context", inject)

    tracing_module._before_task_publish_trace(headers=None)

    inject.assert_not_called()


def test_task_trace_signal_hooks_noop_for_missing_headers_or_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attach = MagicMock(side_effect=[None, None, "ignored"])
    detach = MagicMock()

    monkeypatch.setattr(tracing_module, "attach_trace_context", attach)
    monkeypatch.setattr(tracing_module, "detach_trace_context", detach)

    tracing_module._task_prerun_trace(task=SimpleNamespace(request=SimpleNamespace(headers=None)))
    tracing_module._task_prerun_trace(
        task=SimpleNamespace(request=SimpleNamespace(headers={"a": "b"}))
    )
    request_without_token = SimpleNamespace(headers={"a": "b"}, _otel_trace_token=None)
    request_with_token = SimpleNamespace(headers={"c": "d"}, _otel_trace_token=None)
    tracing_module._task_prerun_trace(task=SimpleNamespace(request=request_without_token))
    tracing_module._task_prerun_trace(task=SimpleNamespace(request=request_with_token))
    tracing_module._task_postrun_trace(
        task=SimpleNamespace(request=SimpleNamespace(_otel_trace_token=None))
    )
    tracing_module._task_postrun_trace(task=SimpleNamespace(request=None))

    assert request_without_token._otel_trace_token is None
    assert request_with_token._otel_trace_token == "ignored"
    assert attach.call_args_list == [
        call({"a": "b"}),
        call({"a": "b"}),
        call({"c": "d"}),
    ]
    detach.assert_not_called()


def test_register_celery_context_hooks_registers_once(monkeypatch: pytest.MonkeyPatch) -> None:
    before_connect = MagicMock()
    prerun_connect = MagicMock()
    postrun_connect = MagicMock()

    monkeypatch.setattr(tracing_module, "_celery_context_hooks_registered", False)
    monkeypatch.setattr(
        tracing_module, "before_task_publish", SimpleNamespace(connect=before_connect)
    )
    monkeypatch.setattr(tracing_module, "task_prerun", SimpleNamespace(connect=prerun_connect))
    monkeypatch.setattr(tracing_module, "task_postrun", SimpleNamespace(connect=postrun_connect))

    tracing_module._register_celery_context_hooks()
    tracing_module._register_celery_context_hooks()

    before_connect.assert_called_once_with(tracing_module._before_task_publish_trace, weak=False)
    prerun_connect.assert_called_once_with(tracing_module._task_prerun_trace, weak=False)
    postrun_connect.assert_called_once_with(tracing_module._task_postrun_trace, weak=False)


def test_configure_tracing_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    init_provider = MagicMock()

    monkeypatch.setattr(tracing_module.settings, "OTEL_ENABLED", False)
    monkeypatch.setattr(tracing_module, "_initialize_tracer_provider", init_provider)

    tracing_module.configure_tracing(fastapi_app=object(), celery_app=object())

    init_provider.assert_not_called()


def test_configure_tracing_logs_once_when_dependencies_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_missing = MagicMock()

    monkeypatch.setattr(tracing_module.settings, "OTEL_ENABLED", True)
    monkeypatch.setattr(tracing_module, "_OTEL_AVAILABLE", False)
    monkeypatch.setattr(tracing_module, "_log_missing_otel_dependencies_once", log_missing)

    tracing_module.configure_tracing(fastapi_app=object(), celery_app=object())

    log_missing.assert_called_once_with()


def test_configure_tracing_initializes_fastapi_and_celery_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_provider = MagicMock()
    init_shared = MagicMock()
    instrument_fastapi = MagicMock()
    init_celery = MagicMock()
    register_hooks = MagicMock()
    fastapi_app = object()
    celery_app = object()

    monkeypatch.setattr(tracing_module.settings, "OTEL_ENABLED", True)
    monkeypatch.setattr(tracing_module, "_OTEL_AVAILABLE", True)
    monkeypatch.setattr(tracing_module, "_initialize_tracer_provider", init_provider)
    monkeypatch.setattr(tracing_module, "_initialize_shared_instrumentation", init_shared)
    monkeypatch.setattr(tracing_module, "_instrument_fastapi_app", instrument_fastapi)
    monkeypatch.setattr(tracing_module, "_initialize_celery_instrumentation", init_celery)
    monkeypatch.setattr(tracing_module, "_register_celery_context_hooks", register_hooks)

    tracing_module.configure_tracing(fastapi_app=fastapi_app, celery_app=celery_app)
    tracing_module.configure_tracing(fastapi_app=fastapi_app, celery_app=None)
    tracing_module.configure_tracing(fastapi_app=None, celery_app=celery_app)

    assert init_provider.call_count == 3
    assert init_shared.call_count == 3
    assert instrument_fastapi.call_count == 2
    init_celery.assert_called_with(celery_app)
    assert init_celery.call_count == 2
    assert register_hooks.call_count == 2


def test_trace_context_helpers_noop_when_tracing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tracing_module.settings, "OTEL_ENABLED", False)
    monkeypatch.setattr(tracing_module, "_OTEL_AVAILABLE", True)

    headers: dict[str, str] = {}
    tracing_module.inject_trace_context(headers)
    token = tracing_module.attach_trace_context(headers)
    tracing_module.detach_trace_context(token)

    assert headers == {}
    assert token is None
