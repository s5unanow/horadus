from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.processing.llm_failover import (
    LLMChatFailoverInvoker,
    LLMChatRetryPolicy,
    LLMChatRoute,
    LLMInvocationErrorCode,
)

pytestmark = pytest.mark.unit


class _HttpStatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


@dataclass(slots=True)
class _SequenceCompletions:
    outcomes: list[Any]
    calls: int = 0

    async def create(self, **kwargs):
        _ = kwargs
        if not self.outcomes:
            msg = "No more outcomes configured"
            raise AssertionError(msg)
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _route(
    provider: str, model: str, outcomes: list[Any]
) -> tuple[LLMChatRoute, _SequenceCompletions]:
    completions = _SequenceCompletions(outcomes=outcomes)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return (LLMChatRoute(provider=provider, model=model, client=client), completions)


def _response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
    )


@pytest.mark.asyncio
async def test_invoker_retries_primary_route_before_success() -> None:
    primary_route, primary = _route(
        "openai",
        "gpt-4.1-nano",
        outcomes=[TimeoutError("primary timeout"), _response()],
    )
    invoker = LLMChatFailoverInvoker(
        stage="tier1",
        primary=primary_route,
        retry_policy=LLMChatRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    _response_obj, active_route = await invoker.create_chat_completion(
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert active_route.model == "gpt-4.1-nano"
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_invoker_fails_over_after_primary_retry_budget() -> None:
    primary_route, primary = _route(
        "openai",
        "gpt-4.1-nano",
        outcomes=[_HttpStatusError(429), _HttpStatusError(429)],
    )
    secondary_route, secondary = _route(
        "secondary",
        "gpt-4.1-mini",
        outcomes=[_response()],
    )
    invoker = LLMChatFailoverInvoker(
        stage="tier2",
        primary=primary_route,
        secondary=secondary_route,
        retry_policy=LLMChatRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    _response_obj, active_route = await invoker.create_chat_completion(
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert active_route.model == "gpt-4.1-mini"
    assert primary.calls == 2
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_invoker_raises_after_secondary_retry_budget_exhausted() -> None:
    primary_route, primary = _route(
        "openai",
        "gpt-4.1-nano",
        outcomes=[_HttpStatusError(429), _HttpStatusError(429)],
    )
    secondary_route, secondary = _route(
        "secondary",
        "gpt-4.1-mini",
        outcomes=[TimeoutError("secondary timeout"), TimeoutError("secondary timeout")],
    )
    invoker = LLMChatFailoverInvoker(
        stage="tier2",
        primary=primary_route,
        secondary=secondary_route,
        retry_policy=LLMChatRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    with pytest.raises(TimeoutError, match="secondary timeout"):
        await invoker.create_chat_completion(
            messages=[{"role": "user", "content": "{}"}],
            temperature=0,
            response_format={"type": "json_object"},
        )

    assert primary.calls == 2
    assert secondary.calls == 2


def test_classify_error_reports_retryable_taxonomy() -> None:
    timeout_error = TimeoutError("timeout")
    timeout_classification = LLMChatFailoverInvoker.classify_error(timeout_error)
    assert timeout_classification.code == LLMInvocationErrorCode.TIMEOUT
    assert timeout_classification.retryable is True

    rate_limit_error = _HttpStatusError(429)
    rate_limit_classification = LLMChatFailoverInvoker.classify_error(rate_limit_error)
    assert rate_limit_classification.code == LLMInvocationErrorCode.RATE_LIMIT
    assert rate_limit_classification.retryable is True

    bad_request_error = _HttpStatusError(400)
    bad_request_classification = LLMChatFailoverInvoker.classify_error(bad_request_error)
    assert bad_request_classification.code == LLMInvocationErrorCode.NON_RETRYABLE
    assert bad_request_classification.retryable is False


def test_retry_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_attempts >= 1"):
        LLMChatRetryPolicy(max_attempts=0)

    with pytest.raises(ValueError, match="backoff_seconds >= 0"):
        LLMChatRetryPolicy(backoff_seconds=-0.1)


@pytest.mark.asyncio
async def test_invoker_sleeps_before_retry_when_backoff_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_route, primary = _route(
        "openai",
        "gpt-4.1-nano",
        outcomes=[TimeoutError("primary timeout"), _response()],
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.processing.llm_failover.asyncio.sleep", sleep_mock)
    invoker = LLMChatFailoverInvoker(
        stage="tier1",
        primary=primary_route,
        retry_policy=LLMChatRetryPolicy(max_attempts=2, backoff_seconds=0.5),
    )

    await invoker.create_chat_completion(
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert primary.calls == 2
    sleep_mock.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_create_for_route_uses_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    route, _ = _route("openai", "gpt-4.1-nano", outcomes=[])
    invoker = LLMChatFailoverInvoker(stage="tier1", primary=route)
    expected = _response()
    captured: dict[str, object] = {}

    async def fake_create_route_completion(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        "src.processing.llm_failover.create_route_completion", fake_create_route_completion
    )

    response = await invoker._create_for_route(
        route=route,
        messages=[{"role": "user", "content": "{}"}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    assert response is expected
    assert captured["route"] is route
    assert captured["temperature"] == 0.3


def test_extract_status_code_and_error_reason_helpers() -> None:
    response_error = SimpleNamespace(response=SimpleNamespace(status_code=503))

    assert LLMChatFailoverInvoker._extract_status_code(response_error) == 503
    assert LLMChatFailoverInvoker._extract_status_code(Exception("boom")) is None
    assert LLMChatFailoverInvoker._error_reason(_HttpStatusError(429)) == "rate_limit"


def test_classify_error_supports_openai_exception_types(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRateLimitError(Exception):
        pass

    class FakeTimeoutError(Exception):
        pass

    class FakeConnectionError(Exception):
        pass

    class FakeStatusError(Exception):
        def __init__(self, status_code: int):
            super().__init__(f"status {status_code}")
            self.status_code = status_code

    monkeypatch.setattr("src.processing.llm_failover.RateLimitError", FakeRateLimitError)
    monkeypatch.setattr("src.processing.llm_failover.APITimeoutError", FakeTimeoutError)
    monkeypatch.setattr("src.processing.llm_failover.APIConnectionError", FakeConnectionError)
    monkeypatch.setattr("src.processing.llm_failover.APIStatusError", FakeStatusError)

    rate_limit = LLMChatFailoverInvoker.classify_error(FakeRateLimitError("boom"))
    timeout = LLMChatFailoverInvoker.classify_error(FakeTimeoutError("boom"))
    connection = LLMChatFailoverInvoker.classify_error(FakeConnectionError("boom"))
    http_5xx = LLMChatFailoverInvoker.classify_error(FakeStatusError(503))

    assert rate_limit.code == LLMInvocationErrorCode.RATE_LIMIT
    assert timeout.code == LLMInvocationErrorCode.TIMEOUT
    assert connection.code == LLMInvocationErrorCode.CONNECTION
    assert http_5xx.code == LLMInvocationErrorCode.PROVIDER_HTTP_5XX


def test_classify_error_uses_response_status_when_present() -> None:
    error = Exception("boom")
    error.response = SimpleNamespace(status_code=500)  # type: ignore[attr-defined]

    classification = LLMChatFailoverInvoker.classify_error(error)

    assert classification.code == LLMInvocationErrorCode.PROVIDER_HTTP_5XX
    assert classification.retryable is True
