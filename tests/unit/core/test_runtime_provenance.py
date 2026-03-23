from __future__ import annotations

from src.core.runtime_provenance import build_llm_runtime_provenance, build_semantic_cache_basis


def test_build_semantic_cache_basis_preserves_null_reasoning_effort() -> None:
    basis = build_semantic_cache_basis(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        reasoning_effort=None,
        api_mode=None,
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides=None,
    )

    assert basis["reasoning_effort"] is None


def test_build_llm_runtime_provenance_preserves_null_reasoning_fields() -> None:
    provenance = build_llm_runtime_provenance(
        stage="tier2",
        requested_provider="openai",
        requested_model="gpt-5-mini",
        requested_reasoning_effort="low",
        active_provider="openai",
        active_model="gpt-4.1-mini",
        active_reasoning_effort=None,
        api_mode=None,
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides=None,
    )

    assert provenance["active_route"]["reasoning_effort"] is None
    assert provenance["cache_basis"]["reasoning_effort"] is None
