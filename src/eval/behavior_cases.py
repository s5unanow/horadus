"""Scenario definitions for deterministic behavior-oriented eval suites."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from src.core.report_runtime import build_fallback_narrative_result
from src.eval.behavior_types import BehaviorEvalCaseDefinition
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.trend_impact_mapping import map_event_trend_impacts
from src.storage.event_extraction import (
    CanonicalExtractionSnapshot,
    capture_canonical_extraction,
    demote_current_extraction_to_provisional,
)
from src.storage.models import Event

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEGRADED_HOLD_FIXTURE = tuple[
    Event,
    CanonicalExtractionSnapshot,
    dict[str, Any],
    dict[str, Any],
    datetime,
]


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
    event, snapshot, degraded_claims, degraded_provenance, degraded_when = _degraded_hold_fixture()

    demote_current_extraction_to_provisional(
        event,
        canonical_snapshot=snapshot,
        policy={"degraded_llm": True},
        replay_enqueued=True,
    )

    _require(event.extraction_status == "provisional", "Degraded hold did not mark provisional")
    _require_snapshot_restored(event, snapshot)
    provisional = event.provisional_extraction
    _require_provisional_payload_retained(
        provisional,
        degraded_claims=degraded_claims,
        degraded_provenance=degraded_provenance,
        degraded_when=degraded_when,
    )
    return {
        "restored_summary": event.event_summary,
        "restored_fields_checked": [
            "event_summary",
            "extracted_who",
            "extracted_what",
            "extracted_where",
            "extracted_when",
            "extracted_claims",
            "categories",
            "has_contradictions",
            "contradiction_notes",
            "extraction_provenance",
            "lifecycle_status",
            "epistemic_state",
            "activity_state",
        ],
        "provisional_summary": provisional["summary"],
        "provisional_fields_checked": [
            "summary",
            "extracted_claims",
            "provenance",
            "extracted_when",
            "replay_enqueued",
            "policy",
        ],
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
    base_key = _behavior_cache_key()
    changed_inputs = {
        "provider": _behavior_cache_key(provider="openai-secondary"),
        "model": _behavior_cache_key(model="gpt-4o-mini"),
        "reasoning_effort": _behavior_cache_key(reasoning_effort="high"),
        "api_mode": _behavior_cache_key(api_mode="responses"),
        "prompt_template": _behavior_cache_key(prompt_template="prompt-v2"),
        "schema_payload": _behavior_cache_key(schema_payload={"type": "array"}),
        "request_overrides": _behavior_cache_key(request_overrides={"service_tier": "flex"}),
    }
    for input_name, changed_key in changed_inputs.items():
        _require(
            changed_key != base_key,
            f"{input_name} change did not invalidate cache key",
        )
    return {
        "base_key_prefix": base_key.split(":")[:4],
        "invalidated_inputs": list(changed_inputs),
    }


def _weekly_report_prompt() -> tuple[Path, str]:
    return (
        (prompt_path := _REPO_ROOT / "ai/prompts/weekly_report.md"),
        prompt_path.read_text(encoding="utf-8"),
    )


def _degraded_hold_fixture() -> _DEGRADED_HOLD_FIXTURE:
    canonical_when = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
    degraded_when = datetime(2026, 1, 6, 14, 45, tzinfo=UTC)
    canonical_claims = {"trend_impacts": [{"trend_id": "nato-russia", "signal_type": "deploy"}]}
    canonical_provenance = {
        "stage": "tier2",
        "active_route": {"model": "gpt-4.1-mini"},
        "prompt_hash": "canonical-hash",
    }
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        event_summary="Stable canonical summary",
        extracted_who=["NATO", "Russia"],
        extracted_what="Canonical extraction",
        extracted_where="Baltics",
        extracted_when=canonical_when,
        extracted_claims=canonical_claims,
        categories=["military"],
        has_contradictions=True,
        contradiction_notes="Conflicting source framing remains unresolved.",
        extraction_provenance=canonical_provenance,
        extraction_status="canonical",
        lifecycle_status="confirmed",
        epistemic_state="confirmed",
        activity_state="dormant",
    )
    snapshot = capture_canonical_extraction(event)
    degraded_claims = {"trend_impacts": [{"trend_id": "eu-russia", "signal_type": "incident"}]}
    degraded_provenance = {
        "stage": "tier2",
        "active_route": {"model": "gpt-4.1-nano"},
        "prompt_hash": "degraded-hash",
    }
    event.event_summary = "Held degraded summary"
    event.extracted_who = ["Operator note"]
    event.extracted_what = "Held degraded extraction"
    event.extracted_where = "Black Sea"
    event.extracted_when = degraded_when
    event.categories = ["security"]
    event.extracted_claims = degraded_claims
    event.has_contradictions = False
    event.contradiction_notes = None
    event.extraction_provenance = degraded_provenance
    event.lifecycle_status = "emerging"
    event.epistemic_state = "emerging"
    event.activity_state = "active"
    return event, snapshot, degraded_claims, degraded_provenance, degraded_when


def _require_snapshot_restored(event: Event, snapshot: CanonicalExtractionSnapshot) -> None:
    restored_checks = (
        ("event_summary", event.event_summary, snapshot.event_summary),
        ("extracted_who", event.extracted_who, snapshot.extracted_who),
        ("extracted_what", event.extracted_what, snapshot.extracted_what),
        ("extracted_where", event.extracted_where, snapshot.extracted_where),
        ("extracted_when", event.extracted_when, snapshot.extracted_when),
        ("extracted_claims", event.extracted_claims, snapshot.extracted_claims),
        ("categories", event.categories, snapshot.categories),
        ("has_contradictions", event.has_contradictions, snapshot.has_contradictions),
        ("contradiction_notes", event.contradiction_notes, snapshot.contradiction_notes),
        ("extraction_provenance", event.extraction_provenance, snapshot.extraction_provenance),
        ("lifecycle_status", event.lifecycle_status, snapshot.lifecycle_status),
        ("epistemic_state", event.epistemic_state, snapshot.epistemic_state),
        ("activity_state", event.activity_state, snapshot.activity_state),
    )
    for field_name, actual, expected in restored_checks:
        _require(actual == expected, f"Degraded hold lost canonical {field_name}")


def _require_provisional_payload_retained(
    provisional: dict[str, Any],
    *,
    degraded_claims: dict[str, Any],
    degraded_provenance: dict[str, Any],
    degraded_when: datetime,
) -> None:
    expected_checks = (
        ("summary", provisional["summary"], "Held degraded summary"),
        ("extracted_claims", provisional["extracted_claims"], degraded_claims),
        ("provenance", provisional["provenance"], degraded_provenance),
        ("extracted_when", provisional["extracted_when"], degraded_when.isoformat()),
        ("replay_enqueued", provisional["replay_enqueued"], True),
        ("policy", provisional["policy"], {"degraded_llm": True}),
    )
    for field_name, actual, expected in expected_checks:
        _require(actual == expected, f"Provisional payload did not retain {field_name}")


def _behavior_cache_key(
    *,
    provider: str = "openai",
    model: str = "gpt-4.1-mini",
    reasoning_effort: str = "medium",
    api_mode: str = "chat_completions",
    prompt_template: str = "prompt-v1",
    schema_payload: dict[str, Any] | None = None,
    request_overrides: dict[str, Any] | None = None,
) -> str:
    return LLMSemanticCache.build_cache_key(
        stage="tier2",
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        api_mode=api_mode,
        prompt_path="ai/prompts/tier2_classify.md",
        prompt_template=prompt_template,
        schema_name="tier2_event_classification",
        schema_payload=schema_payload or {"type": "object"},
        request_overrides=request_overrides or {"service_tier": "default"},
        payload={"event_id": "1"},
        redis_prefix="cache",
    )


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
            "Semantic cache entries must invalidate when provider, model, "
            "reasoning effort, API mode, prompt, schema, or request-basis "
            "inputs change."
        ),
        expected_behavior=(
            "Equivalent payloads produce distinct cache keys when a tracked basis input changes."
        ),
        surface_paths=("src/processing/semantic_cache.py",),
        runner=_eval_semantic_cache_basis_changes_invalidate_keys,
    ),
)
