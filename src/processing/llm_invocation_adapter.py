"""
Adapter layer for chat-completions vs responses API invocation.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


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
    if api_mode == "chat_completions":
        create_kwargs: dict[str, Any] = {
            "model": route.model,
            "temperature": temperature,
            "messages": messages,
        }
        if response_format is not None:
            create_kwargs["response_format"] = response_format
        if isinstance(request_overrides, dict):
            create_kwargs.update(request_overrides)
        return await route.client.chat.completions.create(**create_kwargs)

    if api_mode == "responses":
        if response_format is not None:
            msg = "Responses API adapter does not support response_format yet"
            raise ValueError(msg)
        responses_create_kwargs: dict[str, Any] = {
            "model": route.model,
            "temperature": temperature,
            "input": _to_responses_input(messages),
        }
        if isinstance(request_overrides, dict):
            responses_create_kwargs.update(request_overrides)
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
