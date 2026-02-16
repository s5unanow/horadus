from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core import tracing as tracing_module

pytestmark = pytest.mark.unit


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
