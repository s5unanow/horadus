from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.processing.llm_invocation_adapter import (
    _extract_responses_output_text,
    _normalize_reasoning_effort,
    _normalized_route_model,
    _normalized_route_provider,
    _supports_reasoning_effort,
    _to_responses_input,
    create_route_completion,
    resolve_route_reasoning_effort,
)

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


@pytest.mark.asyncio
async def test_create_route_completion_omits_temperature_for_openai_gpt5_routes() -> None:
    calls: list[dict[str, object]] = []

    class ChatCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2),
            )

    route = SimpleNamespace(
        provider="openai",
        model="gpt-5-nano",
        api_mode="chat_completions",
        reasoning_effort="minimal",
        client=SimpleNamespace(chat=SimpleNamespace(completions=ChatCompletions())),
    )
    await create_route_completion(
        route=route,
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert len(calls) == 1
    assert "temperature" not in calls[0]
    assert calls[0]["reasoning_effort"] == "minimal"


@pytest.mark.asyncio
async def test_create_route_completion_omits_unsupported_reasoning_effort() -> None:
    calls: list[dict[str, object]] = []

    class ChatCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2),
            )

    route = SimpleNamespace(
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        reasoning_effort="medium",
        request_overrides={"service_tier": "flex"},
        client=SimpleNamespace(chat=SimpleNamespace(completions=ChatCompletions())),
    )
    await create_route_completion(
        route=route,
        messages=[{"role": "user", "content": "{}"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert len(calls) == 1
    assert "reasoning_effort" not in calls[0]
    assert calls[0]["service_tier"] == "flex"
    assert calls[0]["temperature"] == 0


def test_resolve_route_reasoning_effort_respects_provider_model_support() -> None:
    supported_route = SimpleNamespace(provider="openai", model="gpt-5-mini", reasoning_effort="low")
    unsupported_route = SimpleNamespace(
        provider="openai",
        model="gpt-4.1-mini",
        request_overrides={"reasoning_effort": "medium"},
    )

    assert resolve_route_reasoning_effort(supported_route) == "low"
    assert resolve_route_reasoning_effort(unsupported_route) is None


def test_route_normalization_helpers_handle_blank_values() -> None:
    blank_route = SimpleNamespace(provider="  ", model=None)
    supported_route = SimpleNamespace(provider=" OpenAI ", model=" GPT-5-mini ")

    assert _normalized_route_provider(blank_route) == ""
    assert _normalized_route_model(blank_route) == ""
    assert _normalized_route_provider(supported_route) == "openai"
    assert _normalized_route_model(supported_route) == "gpt-5-mini"


def test_reasoning_effort_normalization_and_support_checks() -> None:
    assert _normalize_reasoning_effort(None) is None
    assert _normalize_reasoning_effort("  ") is None
    assert _normalize_reasoning_effort(" HIGH ") == "high"
    assert _supports_reasoning_effort(SimpleNamespace(provider="openai", model="gpt-5"))
    assert not _supports_reasoning_effort(SimpleNamespace(provider="anthropic", model="claude-3"))


def test_resolve_route_reasoning_effort_uses_request_overrides_only_when_dict() -> None:
    missing_override_route = SimpleNamespace(
        provider="openai",
        model="gpt-5-mini",
        request_overrides="not-a-dict",
    )
    blank_override_route = SimpleNamespace(
        provider="openai",
        model="gpt-5-mini",
        request_overrides={"reasoning_effort": "  "},
    )
    supported_override_route = SimpleNamespace(
        provider="openai",
        model="gpt-5-mini",
        request_overrides={"reasoning_effort": " Medium "},
    )

    assert resolve_route_reasoning_effort(missing_override_route) is None
    assert resolve_route_reasoning_effort(blank_override_route) is None
    assert resolve_route_reasoning_effort(supported_override_route) == "medium"


def test_to_responses_input_normalizes_missing_roles_and_content() -> None:
    assert _to_responses_input(
        [
            {"role": "", "content": 123},
            {},
        ]
    ) == [
        {"role": "user", "content": [{"type": "input_text", "text": "123"}]},
        {"role": "user", "content": [{"type": "input_text", "text": ""}]},
    ]


def test_extract_responses_output_text_falls_back_to_content_segments() -> None:
    response = SimpleNamespace(
        output_text="  ",
        output=[
            SimpleNamespace(content="skip"),
            SimpleNamespace(
                content=[
                    SimpleNamespace(text=" first "),
                    SimpleNamespace(text=None),
                    SimpleNamespace(text=""),
                ]
            ),
            SimpleNamespace(content=[SimpleNamespace(text="second")]),
        ],
    )

    assert _extract_responses_output_text(response) == "first\nsecond"
    assert _extract_responses_output_text(SimpleNamespace(output="skip")) == ""


@pytest.mark.asyncio
async def test_create_route_completion_uses_override_temperature_and_filters_reasoning_override() -> (
    None
):
    calls: list[dict[str, object]] = []

    class ChatCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
            )

    route = SimpleNamespace(
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        request_overrides={"temperature": 0.7, "reasoning_effort": "high", "top_p": 0.5},
        client=SimpleNamespace(chat=SimpleNamespace(completions=ChatCompletions())),
    )

    await create_route_completion(
        route=route,
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        response_format=None,
    )

    assert calls == [
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
            "top_p": 0.5,
        }
    ]


@pytest.mark.asyncio
async def test_create_route_completion_responses_mode_handles_segment_fallback_and_gpt5_omissions() -> (
    None
):
    calls: list[dict[str, object]] = []

    class ResponsesApi:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output=[
                    SimpleNamespace(content=[SimpleNamespace(text=" alpha ")]),
                    SimpleNamespace(content=[SimpleNamespace(text="beta")]),
                ],
                usage=None,
            )

    route = SimpleNamespace(
        provider="openai",
        model="gpt-5-mini",
        api_mode="responses",
        request_overrides={"temperature": 0.6, "reasoning_effort": "high", "service_tier": "flex"},
        client=SimpleNamespace(responses=ResponsesApi()),
    )

    response = await create_route_completion(
        route=route,
        messages=[{"role": "system", "content": "s"}],
        temperature=0.2,
        response_format=None,
    )

    assert calls == [
        {
            "model": "gpt-5-mini",
            "input": [{"role": "system", "content": [{"type": "input_text", "text": "s"}]}],
            "reasoning_effort": "high",
            "service_tier": "flex",
        }
    ]
    assert response.choices[0].message.content == "alpha\nbeta"
    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0


@pytest.mark.asyncio
async def test_create_route_completion_rejects_response_format_for_responses_mode() -> None:
    route = SimpleNamespace(
        model="gpt-4.1-mini",
        api_mode="responses",
        client=SimpleNamespace(responses=SimpleNamespace(create=None)),
    )

    with pytest.raises(ValueError, match="does not support response_format"):
        await create_route_completion(
            route=route,
            messages=[{"role": "user", "content": "{}"}],
            temperature=0,
            response_format={"type": "json_object"},
        )


@pytest.mark.asyncio
async def test_create_route_completion_rejects_unknown_api_mode() -> None:
    route = SimpleNamespace(
        model="gpt-4.1-mini",
        api_mode="legacy",
        client=SimpleNamespace(),
    )

    with pytest.raises(ValueError, match="Unsupported LLM API mode 'legacy'"):
        await create_route_completion(
            route=route,
            messages=[{"role": "user", "content": "{}"}],
            temperature=0,
            response_format=None,
        )
