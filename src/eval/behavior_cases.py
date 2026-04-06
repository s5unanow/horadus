"""Scenario definitions for deterministic behavior-oriented eval suites."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from src.core.report_runtime import build_fallback_narrative_result
from src.eval.behavior_types import BehaviorEvalCaseDefinition
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.trend_impact_mapping import map_event_trend_impacts
from src.storage.event_extraction import (
    capture_canonical_extraction,
    demote_current_extraction_to_provisional,
)
from src.storage.models import Event

_REPO_ROOT = Path(__file__).resolve().parents[2]


def behavior_case_definitions() -> tuple[BehaviorEvalCaseDefinition, ...]:
    """Return the static behavior-eval scenario definitions."""

    return _BEHAVIOR_CASE_DEFINITIONS


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _eval_taxonomy_ambiguous_mapping_fail_closed() -> dict[str, Any]:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Troop movement near the border",
        extracted_claims={
            "claims": ["Troop deployment increased near the border."],
            "claim_graph": {
                "nodes": [
                    {
                        "claim_id": "claim_1",
                        "text": "Troop deployment increased near the border.",
                    }
                ],
                "links": [],
            },
        },
    )
    result = map_event_trend_impacts(
        event=event,
        trends=cast(
            "Any",
            [
                _trend(trend_id="eu-russia", actors=[], regions=[]),
                _trend(trend_id="us-china", actors=[], regions=[]),
            ],
        ),
    )
    _require(result.impacts == [], "Ambiguous mapping emitted deterministic impacts")
    unresolved = result.diagnostics["unresolved"]
    _require(bool(unresolved), "Ambiguous mapping did not record unresolved diagnostics")
    _require(
        unresolved[0]["reason"] == "ambiguous_mapping",
        "Ambiguous mapping did not record the expected unresolved reason",
    )
    return {
        "unresolved_reason": unresolved[0]["reason"],
        "unresolved_count": len(unresolved),
        "impact_count": len(result.impacts),
    }


def _eval_taxonomy_no_match_fail_closed() -> dict[str, Any]:
    event = Event(
        id=uuid4(),
        canonical_summary="Summary",
        extracted_what="Economic talks resumed",
        extracted_claims={"claims": [], "claim_graph": {"nodes": [], "links": []}},
    )
    result = map_event_trend_impacts(
        event=event,
        trends=cast(
            "Any",
            [
                _trend(
                    indicators={
                        "incident": {
                            "direction": "escalatory",
                            "keywords": ["fired upon"],
                        }
                    }
                )
            ],
        ),
    )
    _require(result.impacts == [], "No-match mapping emitted deterministic impacts")
    unresolved = result.diagnostics["unresolved"]
    _require(bool(unresolved), "No-match mapping did not record unresolved diagnostics")
    _require(
        unresolved[0]["reason"] == "no_matching_indicator",
        "No-match mapping did not record the expected unresolved reason",
    )
    return {
        "unresolved_reason": unresolved[0]["reason"],
        "event_claim_key": unresolved[0]["event_claim_key"],
        "impact_count": len(result.impacts),
    }


def _eval_degraded_hold_preserves_canonical_extraction() -> dict[str, Any]:
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        event_summary="Stable canonical summary",
        extracted_what="Canonical extraction",
        categories=["military"],
        extraction_provenance={"stage": "tier2", "active_route": {"model": "gpt-4.1-mini"}},
        extraction_status="canonical",
    )
    snapshot = capture_canonical_extraction(event)
    event.event_summary = "Held degraded summary"
    event.extracted_what = "Held degraded extraction"
    event.categories = ["security"]
    event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
    event.extraction_provenance = {"stage": "tier2", "active_route": {"model": "gpt-4.1-nano"}}

    demote_current_extraction_to_provisional(
        event,
        canonical_snapshot=snapshot,
        policy={"degraded_llm": True},
        replay_enqueued=True,
    )

    _require(event.extraction_status == "provisional", "Degraded hold did not mark provisional")
    _require(
        event.event_summary == "Stable canonical summary",
        "Degraded hold overwrote canonical event summary",
    )
    _require(
        event.extracted_what == "Canonical extraction",
        "Degraded hold overwrote canonical extraction text",
    )
    _require(event.categories == ["military"], "Degraded hold overwrote canonical categories")
    provisional = event.provisional_extraction
    _require(
        provisional["summary"] == "Held degraded summary",
        "Provisional payload did not retain degraded summary",
    )
    _require(
        provisional["replay_enqueued"] is True,
        "Provisional payload did not record replay enqueue state",
    )
    _require(
        provisional["policy"] == {"degraded_llm": True},
        "Provisional payload did not record degraded policy metadata",
    )
    return {
        "restored_summary": event.event_summary,
        "provisional_summary": provisional["summary"],
        "replay_enqueued": provisional["replay_enqueued"],
        "policy": provisional["policy"],
    }


def _eval_report_fallback_grounded() -> dict[str, Any]:
    prompt_path, prompt_template = _weekly_report_prompt()
    result = build_fallback_narrative_result(
        trend=SimpleNamespace(name="Signal Watch"),
        report_type="weekly",
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 8,
        },
        payload={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "evidence_count_weekly": 8,
        },
        prompt_path=str(prompt_path.relative_to(_REPO_ROOT)),
        prompt_template=prompt_template,
        fallback_reason="budget_denied",
        attempted_provenance={"stage": "reporting", "mode": "llm"},
        violation_threshold=0,
        numeric_tolerance=0.05,
    )
    _require(result.provisional is True, "Fallback report did not stay provisional")
    _require(
        result.grounding_status == "fallback",
        "Supported fallback report was not grounded",
    )
    _require(
        result.grounding_violation_count == 0,
        "Supported fallback report recorded violations",
    )
    _require(
        result.grounding_references is None,
        "Supported fallback report emitted violations",
    )
    _require(
        "Confidence is moderate" in result.narrative,
        "Fallback report did not carry bounded uncertainty language",
    )
    return {
        "grounding_status": result.grounding_status,
        "grounding_violation_count": result.grounding_violation_count,
        "provisional": result.provisional,
    }


def _eval_report_fallback_flags_unsupported_claims() -> dict[str, Any]:
    prompt_path, prompt_template = _weekly_report_prompt()
    result = build_fallback_narrative_result(
        trend=SimpleNamespace(name="Signal Watch"),
        report_type="weekly",
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 8,
        },
        payload={"current_probability": 0.42},
        prompt_path=str(prompt_path.relative_to(_REPO_ROOT)),
        prompt_template=prompt_template,
        fallback_reason="grounding_failed",
        attempted_provenance={"stage": "reporting", "mode": "llm"},
        violation_threshold=0,
        numeric_tolerance=0.05,
    )
    _require(
        result.grounding_status == "flagged",
        "Unsupported fallback report claims were not surfaced as flagged",
    )
    _require(
        result.grounding_violation_count >= 1,
        "Unsupported fallback report claims did not increment violation count",
    )
    references = result.grounding_references or {}
    _require(
        bool(references.get("unsupported_claims")),
        "Unsupported fallback report claims did not record grounding references",
    )
    return {
        "grounding_status": result.grounding_status,
        "grounding_violation_count": result.grounding_violation_count,
        "unsupported_claims": references["unsupported_claims"],
    }


def _eval_weekly_report_prompt_contract() -> dict[str, Any]:
    prompt_path, prompt = _weekly_report_prompt()
    required_fragments = (
        "Every narrative claim must be directly supported by the provided structured payload",
        "explicitly framed as uncertainty/inference",
        "If evidence is sparse, conflicting, or low-coverage",
    )
    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    _require(
        not missing,
        "Weekly report prompt is missing grounding fragments: " + ", ".join(missing),
    )
    return {
        "prompt_path": str(prompt_path.relative_to(_REPO_ROOT)),
        "required_fragments_checked": list(required_fragments),
    }


def _eval_semantic_cache_basis_changes_invalidate_keys() -> dict[str, Any]:
    base_key = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    prompt_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt-v2",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    schema_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "array"},
        request_overrides={"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    overrides_changed = LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider="openai",
        model="gpt-4.1-mini",
        api_mode="chat_completions",
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template="prompt-v1",
        schema_name="tier2_event_classification",
        schema_payload={"type": "object"},
        request_overrides={"service_tier": "flex"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )
    _require(prompt_changed != base_key, "Prompt change did not invalidate cache key")
    _require(schema_changed != base_key, "Schema change did not invalidate cache key")
    _require(
        overrides_changed != base_key,
        "Request override change did not invalidate cache key",
    )
    return {
        "base_key_prefix": base_key.split(":")[:4],
        "invalidated_inputs": ["prompt_template", "schema_payload", "request_overrides"],
    }


def _weekly_report_prompt() -> tuple[Path, str]:
    prompt_path = _REPO_ROOT / "ai/prompts/weekly_report.md"
    return (prompt_path, prompt_path.read_text(encoding="utf-8"))


def _trend(
    *,
    trend_id: str = "eu-russia",
    indicators: dict[str, dict[str, object]] | None = None,
    actors: list[str] | None = None,
    regions: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=trend_id,
        definition={
            "id": trend_id,
            "actors": actors or ["NATO", "Russia"],
            "regions": regions or ["Baltic region"],
        },
        indicators=indicators
        or {
            "military_movement": {
                "direction": "escalatory",
                "description": "Force repositioning without direct hostile contact.",
                "keywords": ["troop deployment", "deployment"],
            }
        },
    )


_BEHAVIOR_CASE_DEFINITIONS = (
    BehaviorEvalCaseDefinition(
        case_id="taxonomy-ambiguous-fail-closed",
        title="Ambiguous mappings fail closed",
        suite="taxonomy-safety",
        tags=("taxonomy", "safety", "tier2"),
        production_contract=(
            "Deterministic trend mapping must fail closed when multiple candidate "
            "indicators remain materially ambiguous."
        ),
        expected_behavior=(
            "No trend impacts are emitted and unresolved diagnostics record `ambiguous_mapping`."
        ),
        surface_paths=("src/processing/trend_impact_mapping.py",),
        runner=_eval_taxonomy_ambiguous_mapping_fail_closed,
    ),
    BehaviorEvalCaseDefinition(
        case_id="taxonomy-no-match-fail-closed",
        title="Unmapped claims do not emit impacts",
        suite="taxonomy-safety",
        tags=("taxonomy", "safety", "tier2"),
        production_contract=(
            "Deterministic trend mapping must not synthesize impacts for claims "
            "that match no configured indicator."
        ),
        expected_behavior=(
            "No trend impacts are emitted and unresolved diagnostics record "
            "`no_matching_indicator`."
        ),
        surface_paths=("src/processing/trend_impact_mapping.py",),
        runner=_eval_taxonomy_no_match_fail_closed,
    ),
    BehaviorEvalCaseDefinition(
        case_id="degraded-hold-preserves-canonical",
        title="Degraded hold preserves canonical extraction",
        suite="degraded-mode-safety",
        tags=("degraded-mode", "provisional", "tier2", "safety"),
        production_contract=(
            "Degraded Tier-2 output must be held in provisional storage without "
            "overwriting durable canonical extraction fields."
        ),
        expected_behavior=(
            "Canonical fields are restored, extraction status becomes "
            "`provisional`, and the degraded write is retained in the "
            "provisional payload."
        ),
        surface_paths=("src/storage/event_extraction.py",),
        runner=_eval_degraded_hold_preserves_canonical_extraction,
    ),
    BehaviorEvalCaseDefinition(
        case_id="report-fallback-grounded",
        title="Fallback report stays provisional and grounded",
        suite="report-grounding",
        tags=("reporting", "grounding", "fallback", "safety"),
        production_contract=(
            "Fallback report narratives must remain explicitly provisional and "
            "carry grounding status derived from structured payload support."
        ),
        expected_behavior=(
            "Supported fallback narratives remain provisional with "
            "`grounding_status=fallback` and zero grounding violations."
        ),
        surface_paths=("src/core/report_runtime.py", "src/core/narrative_grounding.py"),
        runner=_eval_report_fallback_grounded,
    ),
    BehaviorEvalCaseDefinition(
        case_id="report-fallback-flags-unsupported-claims",
        title="Fallback report flags unsupported numeric claims",
        suite="report-grounding",
        tags=("reporting", "grounding", "fallback", "safety"),
        production_contract=(
            "Fallback report narratives must expose unsupported numeric claims "
            "instead of silently marking them grounded."
        ),
        expected_behavior=(
            "Grounding violations produce `grounding_status=flagged` with "
            "unsupported-claim references."
        ),
        surface_paths=("src/core/report_runtime.py", "src/core/narrative_grounding.py"),
        runner=_eval_report_fallback_flags_unsupported_claims,
    ),
    BehaviorEvalCaseDefinition(
        case_id="weekly-prompt-requires-grounding-language",
        title="Weekly report prompt requires grounding language",
        suite="report-grounding",
        tags=("reporting", "grounding", "prompt-contract", "uncertainty"),
        production_contract=(
            "Weekly report prompts must require direct grounding and explicit "
            "uncertainty framing for unsupported or sparse evidence."
        ),
        expected_behavior=(
            "The prompt text includes direct-grounding instructions and "
            "explicit uncertainty/inference language."
        ),
        surface_paths=("ai/prompts/weekly_report.md",),
        runner=_eval_weekly_report_prompt_contract,
    ),
    BehaviorEvalCaseDefinition(
        case_id="semantic-cache-basis-invalidates-on-basis-change",
        title="Semantic cache keys invalidate on basis changes",
        suite="cache-invalidation",
        tags=("cache", "invalidation", "runtime", "safety"),
        production_contract=(
            "Semantic cache entries must invalidate when model, prompt, schema, "
            "or request-basis inputs change."
        ),
        expected_behavior=(
            "Equivalent payloads produce distinct cache keys when a tracked basis input changes."
        ),
        surface_paths=("src/processing/semantic_cache.py",),
        runner=_eval_semantic_cache_basis_changes_invalidate_keys,
    ),
)
