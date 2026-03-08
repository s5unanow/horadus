from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.processing.llm_failover import LLMChatRoute
from src.processing.llm_policy import (
    build_safe_payload_content,
    extract_usage_tokens,
    invoke_with_policy,
    is_strict_schema_unsupported_error,
)

pytestmark = pytest.mark.unit


class _StrictSchemaUnsupportedError(Exception):
    def __init__(self):
        super().__init__("response_format json_schema strict mode is not supported")
        self.status_code = 400


class _OtherError(Exception):
    def __init__(self, message: str, *, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class _SequenceCompletions:
    outcomes: list[object]

    async def create(self, **kwargs):
        _ = kwargs
        if not self.outcomes:
            raise AssertionError("No more outcomes configured")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(*, prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"ok": True})))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def test_extract_usage_tokens_defaults_to_zero() -> None:
    assert extract_usage_tokens(SimpleNamespace()) == (0, 0)


def test_is_strict_schema_unsupported_error_requires_matching_status_and_message() -> None:
    assert is_strict_schema_unsupported_error(_StrictSchemaUnsupportedError()) is True
    assert (
        is_strict_schema_unsupported_error(
            _OtherError("response_format unsupported", status_code=500)
        )
        is False
    )
    assert (
        is_strict_schema_unsupported_error(_OtherError("plain bad request", status_code=400))
        is False
    )


@pytest.mark.asyncio
async def test_invoke_with_policy_records_budget_and_cost() -> None:
    route = LLMChatRoute(
        provider="openai",
        model="gpt-4.1-mini",
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=_SequenceCompletions([_response(prompt_tokens=10, completion_tokens=5)])
            )
        ),
    )
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )

    result = await invoke_with_policy(
        stage="tier2",
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "{}"}],
        primary_route=route,
        secondary_route=None,
        temperature=0,
        fallback_response_format={"type": "json_object"},
        cost_tracker=cost_tracker,
        budget_tier="tier2",
    )

    assert result.active_provider == "openai"
    assert result.active_model == "gpt-4.1-mini"
    assert result.active_reasoning_effort is None
    assert result.used_secondary_route is False
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.estimated_cost_usd == pytest.approx(0.000012, rel=0.001)
    cost_tracker.ensure_within_budget.assert_awaited_once_with(
        "tier2",
        provider="openai",
        model="gpt-4.1-mini",
    )
    cost_tracker.record_usage.assert_awaited_once_with(
        tier="tier2",
        input_tokens=10,
        output_tokens=5,
        provider="openai",
        model="gpt-4.1-mini",
    )


@pytest.mark.asyncio
async def test_invoke_with_policy_falls_back_when_strict_schema_unsupported() -> None:
    completions = _SequenceCompletions(
        [
            _StrictSchemaUnsupportedError(),
            _response(prompt_tokens=7, completion_tokens=3),
        ]
    )
    route = LLMChatRoute(
        provider="openai",
        model="gpt-4.1-nano",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )

    result = await invoke_with_policy(
        stage="tier1",
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "{}"}],
        primary_route=LLMChatRoute(
            provider="openai",
            model="gpt-5-nano",
            reasoning_effort="minimal",
            client=route.client,
        ),
        secondary_route=None,
        temperature=0,
        strict_response_format={"type": "json_schema"},
        fallback_response_format={"type": "json_object"},
        cost_tracker=cost_tracker,
        budget_tier="tier1",
    )

    assert result.prompt_tokens == 7
    assert result.completion_tokens == 3
    assert result.active_reasoning_effort == "minimal"
    assert result.used_secondary_route is False
    cost_tracker.ensure_within_budget.assert_awaited_once_with(
        "tier1",
        provider="openai",
        model="gpt-5-nano",
    )
    cost_tracker.record_usage.assert_awaited_once()


def test_build_safe_payload_content_wraps_and_truncates() -> None:
    payload = {"text": "x " * 500}
    content = build_safe_payload_content(
        payload,
        tag="UNTRUSTED_TEST",
        max_tokens=10,
        chars_per_token=4,
        truncation_marker="[TRUNCATED]",
        warning_message="payload too large",
    )

    assert content.startswith("<UNTRUSTED_TEST>")
    assert content.endswith("</UNTRUSTED_TEST>")
    assert "[TRUNCATED]" in content


@pytest.mark.asyncio
async def test_invoke_with_policy_records_failover_without_budget_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_route = LLMChatRoute(provider="openai", model="gpt-4.1-mini", client=SimpleNamespace())
    secondary_route = LLMChatRoute(
        provider="openai", model="gpt-4.1-nano", client=SimpleNamespace()
    )
    failovers: list[str] = []

    class _FakeInvoker:
        @staticmethod
        def _extract_status_code(exc: Exception) -> int | None:
            return getattr(exc, "status_code", None)

        def __init__(self, **_: object) -> None:
            pass

        async def create_chat_completion(
            self,
            *,
            messages: list[dict[str, str]],
            temperature: float,
            response_format: dict[str, object] | None,
        ) -> tuple[SimpleNamespace, LLMChatRoute]:
            assert messages
            assert temperature == 0
            assert response_format == {"type": "json_object"}
            return _response(prompt_tokens=4, completion_tokens=2), secondary_route

    monkeypatch.setattr("src.processing.llm_policy.LLMChatFailoverInvoker", _FakeInvoker)
    monkeypatch.setattr(
        "src.processing.llm_policy.record_llm_failover", lambda *, stage: failovers.append(stage)
    )

    result = await invoke_with_policy(
        stage="tier2",
        messages=[{"role": "user", "content": "{}"}],
        primary_route=primary_route,
        secondary_route=secondary_route,
        temperature=0,
        fallback_response_format={"type": "json_object"},
        cost_tracker=None,
        budget_tier=None,
    )

    assert result.used_secondary_route is True
    assert result.active_model == "gpt-4.1-nano"
    assert failovers == ["tier2"]
