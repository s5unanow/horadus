from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.processing.llm_invocation_adapter import create_route_completion

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_create_route_completion_chat_mode_passes_through() -> None:
    calls: list[dict[str, object]] = []

    class ChatCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
            )

    route = SimpleNamespace(
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        client=SimpleNamespace(chat=SimpleNamespace(completions=ChatCompletions())),
    )
    response = await create_route_completion(
        route=route,
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert response.usage.prompt_tokens == 3


@pytest.mark.asyncio
async def test_create_route_completion_responses_mode_normalizes_output() -> None:
    calls: list[dict[str, object]] = []

    class ResponsesApi:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text="Normalized response text",
                usage=SimpleNamespace(input_tokens=9, output_tokens=4),
            )

    route = SimpleNamespace(
        model="gpt-4.1-mini",
        api_mode="responses",
        client=SimpleNamespace(responses=ResponsesApi()),
    )
    response = await create_route_completion(
        route=route,
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        temperature=0.2,
        response_format=None,
    )

    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-4.1-mini"
    assert isinstance(calls[0]["input"], list)
    assert response.choices[0].message.content == "Normalized response text"
    assert response.usage.prompt_tokens == 9
    assert response.usage.completion_tokens == 4
