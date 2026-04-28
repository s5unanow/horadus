"""Tier 1 batch orchestration helper."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from src.processing.cost_tracker import TIER1
from src.processing.llm_policy import build_safe_payload_content
from src.processing.llm_runtime_cache import build_semantic_cache_kwargs
from src.processing.tier1_contract import normalize_output_payload, strict_response_format
from src.processing.tier1_types import Tier1Output, Tier1Usage

if TYPE_CHECKING:
    from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult
    from src.storage.models import RawItem, Trend


async def classify_batch_with_context(
    classifier: Tier1Classifier,
    *,
    items: list[RawItem],
    trends: list[Trend],
) -> tuple[list[Tier1ItemResult], Tier1Usage]:
    payload = classifier._build_payload(items=items, trends=trends)
    response_format = strict_response_format(
        classifier._STRICT_RESPONSE_FORMAT,
        items=items,
        trends=trends,
        trend_identifier=classifier._trend_identifier,
    )
    cached_result = await _cached_result(
        classifier=classifier,
        payload=payload,
        response_format=response_format,
        items=items,
        trends=trends,
    )
    if cached_result is not None:
        return cached_result
    if (
        classifier._estimate_payload_tokens(payload) > classifier._MAX_REQUEST_INPUT_TOKENS
        and len(items) > 1
    ):
        midpoint = max(1, len(items) // 2)
        left_results, left_usage = await classifier._classify_batch(items[:midpoint], trends)
        right_results, right_usage = await classifier._classify_batch(items[midpoint:], trends)
        return (
            [*left_results, *right_results],
            classifier._merge_usage(left_usage=left_usage, right_usage=right_usage),
        )
    return await _live_result(
        classifier=classifier,
        payload=payload,
        response_format=response_format,
        items=items,
        trends=trends,
    )


async def _cached_result(
    *,
    classifier: Tier1Classifier,
    payload: dict[str, Any],
    response_format: dict[str, Any],
    items: list[RawItem],
    trends: list[Trend],
) -> tuple[list[Tier1ItemResult], Tier1Usage] | None:
    for provider, model, reasoning_effort in classifier._semantic_cache_read_routes():
        candidate = await asyncio.to_thread(
            classifier.semantic_cache.get,
            **_cache_kwargs(
                classifier=classifier,
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort,
                response_format=response_format,
            ),
            payload=payload,
        )
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        try:
            output = Tier1Output.model_validate(normalize_output_payload(json.loads(candidate)))
            classifier._validate_output_alignment(output, items=items)
            return (classifier._to_item_results(output, items=items, trends=trends), Tier1Usage())
        except (ValueError, json.JSONDecodeError):
            return None
    return None


async def _live_result(
    *,
    classifier: Tier1Classifier,
    payload: dict[str, Any],
    response_format: dict[str, Any],
    items: list[RawItem],
    trends: list[Trend],
) -> tuple[list[Tier1ItemResult], Tier1Usage]:
    invocation = await classifier._invoke_batch_model(
        messages=[
            {"role": "system", "content": classifier.prompt_template},
            {"role": "user", "content": _payload_content(classifier=classifier, payload=payload)},
        ],
        response_format=response_format,
    )
    output = classifier._parse_output(invocation.response)
    classifier._validate_output_alignment(output, items=items)
    results = classifier._to_item_results(output, items=items, trends=trends)
    await classifier._cache_batch_response(
        invocation=invocation,
        payload=payload,
        response_format=response_format,
    )
    return (
        results,
        Tier1Usage(
            prompt_tokens=invocation.prompt_tokens,
            completion_tokens=invocation.completion_tokens,
            api_calls=1,
            estimated_cost_usd=invocation.estimated_cost_usd,
            active_provider=invocation.active_provider,
            active_model=invocation.active_model,
            active_reasoning_effort=invocation.active_reasoning_effort,
            used_secondary_route=invocation.used_secondary_route,
        ),
    )


def _payload_content(*, classifier: Tier1Classifier, payload: dict[str, Any]) -> str:
    return build_safe_payload_content(
        payload,
        tag="UNTRUSTED_TIER1_PAYLOAD",
        max_tokens=classifier._MAX_REQUEST_INPUT_TOKENS,
        chars_per_token=classifier._CHARS_PER_TOKEN,
        truncation_marker=classifier._TRUNCATION_MARKER,
        warning_message="Tier 1 payload exceeded token budget; truncating",
        warning_context={"stage": TIER1, "model": classifier.model},
    )


def _cache_kwargs(
    *,
    classifier: Tier1Classifier,
    provider: str | None,
    model: str,
    reasoning_effort: str | None,
    response_format: dict[str, Any],
) -> dict[str, Any]:
    return build_semantic_cache_kwargs(
        stage=TIER1,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        prompt_path=classifier.prompt_path,
        prompt_template=classifier.prompt_template,
        schema_name="tier1_classification",
        schema_payload=response_format["json_schema"]["schema"],
        request_overrides=classifier.request_overrides,
    )
