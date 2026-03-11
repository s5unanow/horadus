"""
Adapter layer for chat-completions vs responses API invocation.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _normalized_route_provider(route: Any) -> str:
    return str(getattr(route, "provider", "") or "").strip().lower()


def _normalized_route_model(route: Any) -> str:
    return str(getattr(route, "model", "") or "").strip().lower()


def _normalize_reasoning_effort(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return normalized


def _supports_reasoning_effort(route: Any) -> bool:
    return _normalized_route_provider(route) == "openai" and _normalized_route_model(
        route
    ).startswith("gpt-5")


def _should_omit_temperature(route: Any) -> bool:
    return _supports_reasoning_effort(route)


def resolve_route_reasoning_effort(route: Any) -> str | None:
    route_reasoning_effort = _normalize_reasoning_effort(getattr(route, "reasoning_effort", None))
    if route_reasoning_effort is not None:
        return route_reasoning_effort if _supports_reasoning_effort(route) else None

    request_overrides = getattr(route, "request_overrides", None)
    if not isinstance(request_overrides, dict):
        return None
    override_reasoning_effort = _normalize_reasoning_effort(
        request_overrides.get("reasoning_effort")
    )
    if override_reasoning_effort is None:
        return None
    return override_reasoning_effort if _supports_reasoning_effort(route) else None


def _to_responses_input(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user") or "user")
        content = str(message.get("content", ""))
        converted.append(
            {
                "role": role,
                "content": [{"type": "input_text", "text": content}],
            }
        )
    return converted


def _extract_responses_output_text(response: Any) -> str:
    direct_text = getattr(response, "output_text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    chunks: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for segment in content:
            segment_text = getattr(segment, "text", None)
            if isinstance(segment_text, str) and segment_text.strip():
                chunks.append(segment_text.strip())
    return "\n".join(chunks).strip()


async def create_route_completion(
    *,
    route: Any,
    messages: list[dict[str, str]],
    temperature: float,
    response_format: dict[str, Any] | None,
) -> Any:
    api_mode = str(getattr(route, "api_mode", "chat_completions") or "chat_completions")
    request_overrides = getattr(route, "request_overrides", None)
    normalized_request_overrides = (
        dict(request_overrides) if isinstance(request_overrides, dict) else {}
    )
    effective_reasoning_effort = resolve_route_reasoning_effort(route)
    effective_temperature = normalized_request_overrides.pop("temperature", temperature)
    normalized_request_overrides.pop("reasoning_effort", None)
    if api_mode == "chat_completions":
        create_kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": messages,
        }
        if not _should_omit_temperature(route):
            create_kwargs["temperature"] = effective_temperature
        if response_format is not None:
            create_kwargs["response_format"] = response_format
        if effective_reasoning_effort is not None:
            create_kwargs["reasoning_effort"] = effective_reasoning_effort
        if normalized_request_overrides:
            create_kwargs.update(normalized_request_overrides)
        return await route.client.chat.completions.create(**create_kwargs)

    if api_mode == "responses":
        if response_format is not None:
            msg = "Responses API adapter does not support response_format yet"
            raise ValueError(msg)
        responses_create_kwargs: dict[str, Any] = {
            "model": route.model,
            "input": _to_responses_input(messages),
        }
        if not _should_omit_temperature(route):
            responses_create_kwargs["temperature"] = effective_temperature
        if effective_reasoning_effort is not None:
            responses_create_kwargs["reasoning_effort"] = effective_reasoning_effort
        if normalized_request_overrides:
            responses_create_kwargs.update(normalized_request_overrides)
        raw_response = await route.client.responses.create(**responses_create_kwargs)
        output_text = _extract_responses_output_text(raw_response)
        usage = getattr(raw_response, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=output_text))],
            usage=SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            raw_response=raw_response,
        )

    msg = f"Unsupported LLM API mode '{api_mode}'"
    raise ValueError(msg)
