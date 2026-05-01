"""Tier-2 request payload construction helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.core.trend_config import normalize_definition_payload, trend_runtime_id_for_record
from src.processing.llm_input_safety import (
    estimate_tokens,
    truncate_to_token_limit,
    wrap_untrusted_text,
)
from src.storage.event_summary import resolved_event_summary

if TYPE_CHECKING:
    from src.storage.models import Event, Trend


def build_tier2_payload(
    *,
    event: Event,
    trends: list[Trend],
    context_chunks: list[str],
    max_context_chunk_tokens: int,
    min_context_chunk_tokens: int,
    max_request_input_tokens: int,
    payload_headroom_tokens: int,
    chars_per_token: int,
    truncation_marker: str,
) -> dict[str, Any]:
    sanitized_chunks = [
        truncate_to_token_limit(
            text=chunk,
            max_tokens=max_context_chunk_tokens,
            marker=truncation_marker,
            chars_per_token=chars_per_token,
        )
        for chunk in context_chunks
        if chunk.strip()
    ]
    if not sanitized_chunks:
        sanitized_chunks = [truncation_marker]

    payload: dict[str, Any] = {
        "event_id": str(event.id),
        "summary": _summary_seed(event),
        "trend_signal_catalog": _build_trend_signal_catalog(trends),
        "context_chunks": sanitized_chunks,
    }
    enforce_tier2_payload_budget(
        payload,
        min_context_chunk_tokens=min_context_chunk_tokens,
        max_request_input_tokens=max_request_input_tokens,
        payload_headroom_tokens=payload_headroom_tokens,
        chars_per_token=chars_per_token,
        truncation_marker=truncation_marker,
    )
    payload["context_chunks"] = [
        wrap_untrusted_text(text=str(chunk), tag="UNTRUSTED_EVENT_CONTEXT")
        for chunk in payload["context_chunks"]
    ]
    if estimate_tier2_payload_tokens(payload, chars_per_token=chars_per_token) > (
        max_request_input_tokens
    ):
        msg = "Tier 2 payload exceeds safe input budget after deterministic reductions"
        raise ValueError(msg)
    return payload


def enforce_tier2_payload_budget(
    payload: dict[str, Any],
    *,
    min_context_chunk_tokens: int,
    max_request_input_tokens: int,
    payload_headroom_tokens: int,
    chars_per_token: int,
    truncation_marker: str,
    estimate_tokens_fn: Callable[[dict[str, Any]], int] | None = None,
) -> None:
    estimator = estimate_tokens_fn or (
        lambda candidate: estimate_tier2_payload_tokens(candidate, chars_per_token=chars_per_token)
    )
    budget_limit = max(1, max_request_input_tokens - payload_headroom_tokens)
    if estimator(payload) <= budget_limit:
        return

    context_chunks = payload.get("context_chunks")
    if not isinstance(context_chunks, list):
        return

    while len(context_chunks) > 1 and estimator(payload) > budget_limit:
        context_chunks.pop()

    if estimator(payload) <= budget_limit:
        return

    context_chunks[0] = truncate_to_token_limit(
        text=str(context_chunks[0]),
        max_tokens=min_context_chunk_tokens,
        marker=truncation_marker,
        chars_per_token=chars_per_token,
    )
    if estimator(payload) > budget_limit:
        msg = "Tier 2 payload exceeds safe input budget after deterministic reductions"
        raise ValueError(msg)


def estimate_tier2_payload_tokens(payload: dict[str, Any], *, chars_per_token: int) -> int:
    serialized = json.dumps(payload, ensure_ascii=True)
    return estimate_tokens(text=serialized, chars_per_token=chars_per_token)


def _summary_seed(event: Event) -> str | None:
    extraction_provenance = (
        event.extraction_provenance if isinstance(event.extraction_provenance, dict) else {}
    )
    if extraction_provenance.get("status") == "replay_pending":
        return event.canonical_summary
    return resolved_event_summary(event)


def _build_trend_signal_catalog(trends: list[Trend]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for trend in trends:
        definition = normalize_definition_payload(
            trend.definition if isinstance(trend.definition, dict) else None
        )
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        catalog.append(
            {
                "trend_id": trend_runtime_id_for_record(trend),
                "name": str(getattr(trend, "name", "") or definition.get("id", "")),
                "actors": _catalog_string_list(definition.get("actors"), limit=8),
                "regions": _catalog_string_list(definition.get("regions"), limit=8),
                "signals": _build_signal_catalog(indicators),
            }
        )
    return catalog


def _build_signal_catalog(indicators: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "signal_type": str(signal_type),
            "direction": str(raw_config.get("direction", "")).strip(),
            "description": _optional_catalog_string(raw_config.get("description")),
            "keywords": _catalog_string_list(raw_config.get("keywords"), limit=4),
        }
        for signal_type, raw_config in indicators.items()
        if isinstance(raw_config, dict)
    ]


def _optional_catalog_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _catalog_string_list(values: Any, *, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = " ".join(value.split())
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned
