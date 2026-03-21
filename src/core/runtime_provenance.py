"""Shared runtime provenance helpers for LLM-derived artifacts and scoring math."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

from src.storage.scoring_contract import (
    TREND_SCORING_MATH_VERSION,
    TREND_SCORING_PARAMETER_SET,
    TREND_SCORING_PROMOTION_CHECK,
)


def canonical_json(value: Any) -> str:
    """Return a stable JSON serialization for provenance hashing."""

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonicalize_payload(value: Any) -> Any:
    """Normalize JSON-compatible data into a stable key order."""

    return json.loads(canonical_json(value))


def payload_sha256(value: Any) -> str:
    """Return a stable SHA-256 hash for JSON-compatible data."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_request_overrides(request_overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize request overrides into a stable JSON-compatible mapping."""

    if request_overrides is None:
        return None
    return cast("dict[str, Any]", canonicalize_payload(request_overrides))


def build_prompt_provenance(*, prompt_path: str, prompt_template: str) -> dict[str, str]:
    """Return prompt path and content hash for runtime provenance."""

    return {
        "path": str(prompt_path),
        "sha256": hashlib.sha256(prompt_template.encode("utf-8")).hexdigest(),
    }


def build_schema_provenance(
    *,
    schema_name: str,
    schema_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return schema provenance when a structured schema is available."""

    if schema_payload is None:
        return None
    normalized_schema = canonicalize_payload(schema_payload)
    return {
        "name": schema_name,
        "sha256": payload_sha256(normalized_schema),
    }


def build_semantic_cache_basis(
    *,
    stage: str,
    provider: str | None,
    model: str,
    api_mode: str | None,
    prompt_path: str,
    prompt_template: str,
    schema_name: str,
    schema_payload: Mapping[str, Any] | None,
    request_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the canonical cache/debug basis shared with persisted artifacts."""

    payload: dict[str, Any] = {
        "stage": stage,
        "provider": provider.strip() if isinstance(provider, str) and provider.strip() else None,
        "model": model.strip(),
        "api_mode": api_mode.strip() if isinstance(api_mode, str) and api_mode.strip() else None,
        "prompt": build_prompt_provenance(
            prompt_path=prompt_path,
            prompt_template=prompt_template,
        ),
        "schema": build_schema_provenance(
            schema_name=schema_name,
            schema_payload=schema_payload,
        ),
        "request_overrides": normalize_request_overrides(request_overrides),
    }
    return _strip_none(payload)


def build_llm_runtime_provenance(
    *,
    stage: str,
    requested_provider: str | None,
    requested_model: str,
    requested_reasoning_effort: str | None,
    active_provider: str | None,
    active_model: str,
    active_reasoning_effort: str | None,
    api_mode: str | None,
    prompt_path: str,
    prompt_template: str,
    schema_name: str,
    schema_payload: Mapping[str, Any] | None,
    request_overrides: dict[str, Any] | None,
    derivation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build persisted runtime provenance for one LLM-derived artifact."""

    cache_basis = build_semantic_cache_basis(
        stage=stage,
        provider=active_provider,
        model=active_model,
        api_mode=api_mode,
        prompt_path=prompt_path,
        prompt_template=prompt_template,
        schema_name=schema_name,
        schema_payload=schema_payload,
        request_overrides=request_overrides,
    )
    payload: dict[str, Any] = {
        "stage": stage,
        "prompt": cache_basis["prompt"],
        "schema": cache_basis.get("schema"),
        "request_overrides": cache_basis.get("request_overrides"),
        "requested_route": {
            "provider": requested_provider,
            "model": requested_model.strip(),
            "reasoning_effort": requested_reasoning_effort,
            "api_mode": api_mode,
        },
        "active_route": {
            "provider": active_provider,
            "model": active_model.strip(),
            "reasoning_effort": active_reasoning_effort,
            "api_mode": api_mode,
        },
        "cache_basis": cache_basis,
        "derivation": canonicalize_payload(derivation) if isinstance(derivation, dict) else None,
    }
    return _strip_none(payload)


def current_trend_scoring_contract() -> dict[str, Any]:
    """Return the current named scoring contract for persisted evidence/restatements."""

    return {
        "math_version": TREND_SCORING_MATH_VERSION,
        "parameter_set": TREND_SCORING_PARAMETER_SET,
        "promotion_check": canonicalize_payload(TREND_SCORING_PROMOTION_CHECK),
    }


def _strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
