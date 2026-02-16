from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.processing.llm_failover import LLMChatRoute
from src.processing.llm_policy import (
    build_safe_payload_content,
    invoke_with_policy,
)

pytestmark = pytest.mark.unit


class _StrictSchemaUnsupportedError(Exception):
    def __init__(self):
        super().__init__("response_format json_schema strict mode is not supported")
        self.status_code = 400


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

    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.estimated_cost_usd == pytest.approx(0.000012, rel=0.001)
    cost_tracker.ensure_within_budget.assert_awaited_once_with("tier2")
    cost_tracker.record_usage.assert_awaited_once_with(
        tier="tier2",
        input_tokens=10,
        output_tokens=5,
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
        primary_route=route,
        secondary_route=None,
        temperature=0,
        strict_response_format={"type": "json_schema"},
        fallback_response_format={"type": "json_object"},
        cost_tracker=cost_tracker,
        budget_tier="tier1",
    )

    assert result.prompt_tokens == 7
    assert result.completion_tokens == 3
    cost_tracker.ensure_within_budget.assert_awaited_once_with("tier1")
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
