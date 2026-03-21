"""Shared cache/provenance helpers for LLM runtime surfaces."""

from __future__ import annotations

from typing import Any

from src.core.runtime_provenance import build_llm_runtime_provenance


def build_semantic_cache_kwargs(
    *,
    stage: str,
    provider: str | None,
    model: str,
    reasoning_effort: str | None,
    prompt_path: str,
    prompt_template: str,
    schema_name: str,
    schema_payload: dict[str, Any] | None,
    request_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "api_mode": None,
        "prompt_path": prompt_path,
        "prompt_template": prompt_template,
        "schema_name": schema_name,
        "schema_payload": schema_payload,
        "request_overrides": request_overrides,
    }


def build_tier2_event_provenance(
    *,
    requested_provider: str | None,
    requested_model: str,
    requested_reasoning_effort: str | None,
    active_provider: str | None,
    active_model: str,
    active_reasoning_effort: str | None,
    prompt_path: str,
    prompt_template: str,
    schema_payload: dict[str, Any] | None,
    request_overrides: dict[str, Any] | None,
    derivation: dict[str, Any] | None,
) -> dict[str, Any]:
    return build_llm_runtime_provenance(
        stage="tier2",
        requested_provider=requested_provider,
        requested_model=requested_model,
        requested_reasoning_effort=requested_reasoning_effort,
        active_provider=active_provider,
        active_model=active_model,
        active_reasoning_effort=active_reasoning_effort,
        api_mode=None,
        prompt_path=prompt_path,
        prompt_template=prompt_template,
        schema_name="tier2_event_classification",
        schema_payload=schema_payload,
        request_overrides=request_overrides,
        derivation=derivation,
    )


def with_cache_hit_derivation(provenance_derivation: dict[str, Any] | None) -> dict[str, Any]:
    derivation = dict(provenance_derivation or {})
    derivation["cache_hit"] = True
    return derivation
