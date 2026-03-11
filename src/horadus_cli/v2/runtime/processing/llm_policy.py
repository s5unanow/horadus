"""
Unified LLM invocation policy helpers.

Centralizes shared budget checks, failover/retry invocation, strict-schema
fallback behavior, usage accounting, cost estimation, and payload safety hooks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from src.horadus_cli.v2.runtime.core.config import settings
from src.horadus_cli.v2.runtime.core.observability import record_llm_failover
from src.horadus_cli.v2.runtime.processing.llm_failover import (
    LLMChatFailoverInvoker,
    LLMChatRetryPolicy,
    LLMChatRoute,
)
from src.horadus_cli.v2.runtime.processing.llm_input_safety import (
    estimate_tokens,
    truncate_to_token_limit,
    wrap_untrusted_text,
)
from src.horadus_cli.v2.runtime.processing.llm_invocation_adapter import (
    resolve_route_reasoning_effort,
)
from src.horadus_cli.v2.runtime.processing.llm_pricing import estimate_model_cost_usd

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LLMInvocationResult:
    response: Any
    active_provider: str
    active_model: str
    active_reasoning_effort: str | None
    used_secondary_route: bool
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float


def build_safe_payload_content(
    payload: dict[str, Any],
    *,
    tag: str,
    max_tokens: int,
    chars_per_token: int,
    truncation_marker: str,
    warning_message: str,
    warning_context: dict[str, Any] | None = None,
) -> str:
    raw_payload = json.dumps(payload, ensure_ascii=True)
    estimated_input_tokens = estimate_tokens(
        text=raw_payload,
        chars_per_token=chars_per_token,
    )
    if estimated_input_tokens > max_tokens:
        logger.warning(
            warning_message,
            estimated_tokens=estimated_input_tokens,
            max_tokens=max_tokens,
            **(warning_context or {}),
        )
        raw_payload = truncate_to_token_limit(
            text=raw_payload,
            max_tokens=max_tokens,
            marker=truncation_marker,
            chars_per_token=chars_per_token,
        )
    return wrap_untrusted_text(text=raw_payload, tag=tag)


def extract_usage_tokens(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return (prompt_tokens, completion_tokens)


def apply_latest_active_route_metadata(*, target_usage: Any, source_usage: Any) -> None:
    """Keep aggregated route metadata aligned with the latest real LLM invocation."""
    source_api_calls = int(getattr(source_usage, "api_calls", 0) or 0)
    source_provider = getattr(source_usage, "active_provider", None)
    source_model = getattr(source_usage, "active_model", None)
    if source_api_calls <= 0 and source_provider is None and source_model is None:
        return
    target_usage.active_provider = source_provider
    target_usage.active_model = source_model
    target_usage.active_reasoning_effort = getattr(source_usage, "active_reasoning_effort", None)


def is_strict_schema_unsupported_error(exc: Exception) -> bool:
    status_code = LLMChatFailoverInvoker._extract_status_code(exc)
    if status_code != 400:
        return False
    message = str(exc).lower()
    return "json_schema" in message or "response_format" in message or "strict" in message


async def invoke_with_policy(
    *,
    stage: str,
    messages: list[dict[str, str]],
    primary_route: LLMChatRoute,
    secondary_route: LLMChatRoute | None,
    temperature: float,
    strict_response_format: dict[str, Any] | None = None,
    fallback_response_format: dict[str, Any] | None = None,
    cost_tracker: Any | None = None,
    budget_tier: str | None = None,
    retry_policy: LLMChatRetryPolicy | None = None,
) -> LLMInvocationResult:
    if cost_tracker is not None and budget_tier is not None:
        await cost_tracker.ensure_within_budget(
            budget_tier,
            provider=primary_route.provider,
            model=primary_route.model,
        )
        if secondary_route is not None:
            await cost_tracker.ensure_within_budget(
                budget_tier,
                provider=secondary_route.provider,
                model=secondary_route.model,
            )

    invoker = LLMChatFailoverInvoker(
        stage=stage,
        primary=primary_route,
        secondary=secondary_route,
        retry_policy=retry_policy
        or LLMChatRetryPolicy(
            max_attempts=settings.LLM_ROUTE_RETRY_ATTEMPTS,
            backoff_seconds=settings.LLM_ROUTE_RETRY_BACKOFF_SECONDS,
        ),
    )

    if strict_response_format is not None:
        try:
            response, active_route = await invoker.create_chat_completion(
                messages=messages,
                temperature=temperature,
                response_format=strict_response_format,
            )
        except Exception as exc:
            if fallback_response_format is None or not is_strict_schema_unsupported_error(exc):
                raise
            logger.warning(
                "Strict schema unsupported; falling back to compatibility response format",
                stage=stage,
                model=primary_route.model,
                api_mode=primary_route.api_mode,
                reasoning_effort=resolve_route_reasoning_effort(primary_route),
            )
            response, active_route = await invoker.create_chat_completion(
                messages=messages,
                temperature=temperature,
                response_format=fallback_response_format,
            )
    else:
        response, active_route = await invoker.create_chat_completion(
            messages=messages,
            temperature=temperature,
            response_format=fallback_response_format,
        )

    prompt_tokens, completion_tokens = extract_usage_tokens(response)
    active_provider = active_route.provider
    active_model = active_route.model
    active_reasoning_effort = resolve_route_reasoning_effort(active_route)
    used_secondary = secondary_route is not None and active_route is secondary_route
    if used_secondary:
        record_llm_failover(stage=stage)
    if cost_tracker is not None and budget_tier is not None:
        await cost_tracker.record_usage(
            tier=budget_tier,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            provider=active_provider,
            model=active_model,
        )

    estimated_cost = estimate_model_cost_usd(
        model=active_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return LLMInvocationResult(
        response=response,
        active_provider=active_provider,
        active_model=active_model,
        active_reasoning_effort=active_reasoning_effort,
        used_secondary_route=used_secondary,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost,
    )
