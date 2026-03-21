"""Shared report LLM payload and invocation helpers."""

from __future__ import annotations

from typing import Any

from src.core.runtime_provenance import build_llm_runtime_provenance
from src.processing.cost_tracker import TIER2
from src.processing.llm_failover import LLMChatRoute
from src.processing.llm_policy import build_safe_payload_content, invoke_with_policy


def build_report_payload_content(
    *,
    payload: dict[str, Any],
    report_type: str,
    max_tokens: int,
    chars_per_token: int,
    truncation_marker: str,
) -> str:
    return build_safe_payload_content(
        payload,
        tag="UNTRUSTED_REPORT_PAYLOAD",
        max_tokens=max_tokens,
        chars_per_token=chars_per_token,
        truncation_marker=truncation_marker,
        warning_message="Report narrative payload exceeded token budget; truncating",
        warning_context={"report_type": report_type},
    )


async def invoke_report_narrative(
    *,
    payload: dict[str, Any],
    prompt_path: str,
    prompt_template: str,
    report_type: str,
    primary_provider: str,
    primary_model: str,
    primary_client: Any,
    secondary_provider: str | None,
    secondary_model: str | None,
    secondary_client: Any | None,
    api_mode: str,
    cost_tracker: Any,
    max_tokens: int,
    chars_per_token: int,
    truncation_marker: str,
) -> tuple[str | None, dict[str, Any]]:
    payload_content = build_report_payload_content(
        payload=payload,
        report_type=report_type,
        max_tokens=max_tokens,
        chars_per_token=chars_per_token,
        truncation_marker=truncation_marker,
    )
    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": payload_content},
    ]
    secondary_route = (
        None
        if secondary_client is None or secondary_model is None
        else LLMChatRoute(
            provider=secondary_provider or primary_provider,
            model=secondary_model,
            client=secondary_client,
            api_mode=api_mode,
        )
    )
    invocation = await invoke_with_policy(
        stage="reporting",
        messages=messages,
        primary_route=LLMChatRoute(
            provider=primary_provider,
            model=primary_model,
            client=primary_client,
            api_mode=api_mode,
        ),
        secondary_route=secondary_route,
        temperature=0.2,
        cost_tracker=cost_tracker,
        budget_tier=TIER2,
    )
    response = invocation.response
    content = getattr(response.choices[0].message, "content", None)
    provenance = build_llm_runtime_provenance(
        stage="reporting",
        requested_provider=primary_provider,
        requested_model=primary_model,
        requested_reasoning_effort=None,
        active_provider=invocation.active_provider,
        active_model=invocation.active_model,
        active_reasoning_effort=invocation.active_reasoning_effort,
        api_mode=api_mode,
        prompt_path=prompt_path,
        prompt_template=prompt_template,
        schema_name="report_narrative",
        schema_payload=None,
        request_overrides=None,
    )
    return ((content.strip() if isinstance(content, str) and content.strip() else None), provenance)
