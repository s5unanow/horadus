"""Deterministic behavior-oriented eval suites for high-risk runtime contracts."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from src.core.report_runtime import build_fallback_narrative_result
from src.eval import artifact_provenance as provenance
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.trend_impact_mapping import map_event_trend_impacts
from src.storage.event_extraction import (
    capture_canonical_extraction,
    demote_current_extraction_to_provisional,
)
from src.storage.models import Event

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESULT_PREFIX = "behavior"


@dataclass(frozen=True, slots=True)
class BehaviorEvalCaseDefinition:
    """Static definition for one deterministic behavior-eval case."""

    case_id: str
    title: str
    suite: str
    tags: tuple[str, ...]
    production_contract: str
    expected_behavior: str
    surface_paths: tuple[str, ...]
    runner: Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BehaviorEvalCaseResult:
    """Serializable result for one executed behavior-eval case."""

    case_id: str
    title: str
    suite: str
    tags: tuple[str, ...]
    production_contract: str
    expected_behavior: str
    surface_paths: tuple[str, ...]
    passed: bool
    duration_ms: int
    evidence: dict[str, Any] | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class BehaviorEvalRunResult:
    """Summary handle for a completed behavior-eval run."""

    output_path: Path
    passes_validation: bool
    total_cases: int
    selected_cases: int
    passed_cases: int
    failed_cases: int
    selected_suites: tuple[str, ...]
    selected_tags: tuple[str, ...]
    case_results: tuple[BehaviorEvalCaseResult, ...]


def available_behavior_suites() -> tuple[str, ...]:
    """Return the known behavior-eval suite names."""

    return tuple(sorted({case.suite for case in _behavior_case_definitions()}))


def available_behavior_tags() -> tuple[str, ...]:
    """Return the known behavior-eval tags."""

    tags: set[str] = set()
    for case in _behavior_case_definitions():
        tags.update(case.tags)
    return tuple(sorted(tags))


def run_behavior_evals(
    *,
    output_dir: str | Path,
    suites: list[str] | tuple[str, ...] | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
) -> BehaviorEvalRunResult:
    """Run deterministic behavior-eval suites and write a JSON artifact."""

    normalized_suites = _normalize_filter_values(suites)
    normalized_tags = _normalize_filter_values(tags)
    available_suites = set(available_behavior_suites())
    available_tags = set(available_behavior_tags())

    unknown_suites = sorted(set(normalized_suites) - available_suites)
    if unknown_suites:
        msg = (
            "Unknown behavior suite(s): "
            + ", ".join(unknown_suites)
            + ". Available: "
            + ", ".join(sorted(available_suites))
        )
        raise ValueError(msg)

    unknown_tags = sorted(set(normalized_tags) - available_tags)
    if unknown_tags:
        msg = (
            "Unknown behavior tag(s): "
            + ", ".join(unknown_tags)
            + ". Available: "
            + ", ".join(sorted(available_tags))
        )
        raise ValueError(msg)

    definitions = _select_cases(
        case_definitions=_behavior_case_definitions(),
        suites=normalized_suites,
        tags=normalized_tags,
    )
    if not definitions:
        msg = "No behavior eval cases matched the requested suite/tag filters."
        raise ValueError(msg)

    started_at = datetime.now(tz=UTC)
    results = tuple(_run_case(case) for case in definitions)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = len(results) - passed_cases
    output_path = _write_behavior_artifact(
        output_dir=output_dir,
        started_at=started_at,
        suites=normalized_suites,
        tags=normalized_tags,
        results=results,
    )
    return BehaviorEvalRunResult(
        output_path=output_path,
        passes_validation=failed_cases == 0,
        total_cases=len(_behavior_case_definitions()),
        selected_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        selected_suites=normalized_suites,
        selected_tags=normalized_tags,
        case_results=results,
    )


def _normalize_filter_values(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    normalized = {
        value.strip().lower() for value in values or () if isinstance(value, str) and value.strip()
    }
    return tuple(sorted(normalized))


def _select_cases(
    *,
    case_definitions: tuple[BehaviorEvalCaseDefinition, ...],
    suites: tuple[str, ...],
    tags: tuple[str, ...],
) -> tuple[BehaviorEvalCaseDefinition, ...]:
    requested_tags = set(tags)
    selected: list[BehaviorEvalCaseDefinition] = []
    for case in case_definitions:
        if suites and case.suite not in suites:
            continue
        if requested_tags and requested_tags.isdisjoint(case.tags):
            continue
        selected.append(case)
    return tuple(selected)


def _run_case(case: BehaviorEvalCaseDefinition) -> BehaviorEvalCaseResult:
    started = datetime.now(tz=UTC)
    try:
        evidence = case.runner()
    except Exception as exc:
        duration_ms = max(0, int((datetime.now(tz=UTC) - started).total_seconds() * 1000))
        return BehaviorEvalCaseResult(
            case_id=case.case_id,
            title=case.title,
            suite=case.suite,
            tags=case.tags,
            production_contract=case.production_contract,
            expected_behavior=case.expected_behavior,
            surface_paths=case.surface_paths,
            passed=False,
            duration_ms=duration_ms,
            evidence=None,
            failure_message=str(exc) or exc.__class__.__name__,
        )
    duration_ms = max(0, int((datetime.now(tz=UTC) - started).total_seconds() * 1000))
    return BehaviorEvalCaseResult(
        case_id=case.case_id,
        title=case.title,
        suite=case.suite,
        tags=case.tags,
        production_contract=case.production_contract,
        expected_behavior=case.expected_behavior,
        surface_paths=case.surface_paths,
        passed=True,
        duration_ms=duration_ms,
        evidence=evidence,
        failure_message=None,
    )


def _write_behavior_artifact(
    *,
    output_dir: str | Path,
    started_at: datetime,
    suites: tuple[str, ...],
    tags: tuple[str, ...],
    results: tuple[BehaviorEvalCaseResult, ...],
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = output_path / f"{_RESULT_PREFIX}-{timestamp}-{uuid4().hex[:8]}.json"
    payload = {
        "generated_at": started_at.isoformat(),
        "passes_validation": all(result.passed for result in results),
        "filters": {
            "suites": list(suites),
            "tags": list(tags),
        },
        "summary": {
            "total_cases": len(_behavior_case_definitions()),
            "selected_cases": len(results),
            "passed_cases": sum(1 for result in results if result.passed),
            "failed_cases": sum(1 for result in results if not result.passed),
            "suites": _suite_summary(results),
        },
        "source_control": provenance.build_source_control_provenance(repo_root=_REPO_ROOT),
        "cases": [asdict(result) for result in results],
    }
    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_path


def _suite_summary(results: tuple[BehaviorEvalCaseResult, ...]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = {}
    for result in results:
        entry = grouped.setdefault(result.suite, {"selected_cases": 0, "failed_cases": 0})
        entry["selected_cases"] += 1
        if not result.passed:
            entry["failed_cases"] += 1
    return [
        {
            "suite": suite,
            "selected_cases": values["selected_cases"],
            "failed_cases": values["failed_cases"],
        }
        for suite, values in sorted(grouped.items())
    ]


def _behavior_case_definitions() -> tuple[BehaviorEvalCaseDefinition, ...]:
    return (
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
                "No trend impacts are emitted and unresolved diagnostics record "
                "`ambiguous_mapping`."
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
                "Equivalent payloads produce distinct cache keys when a tracked "
                "basis input changes."
            ),
            surface_paths=("src/processing/semantic_cache.py",),
            runner=_eval_semantic_cache_basis_changes_invalidate_keys,
        ),
    )


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
    assert result.impacts == [], "Ambiguous mapping emitted deterministic impacts"
    unresolved = result.diagnostics["unresolved"]
    assert unresolved, "Ambiguous mapping did not record unresolved diagnostics"
    assert (
        unresolved[0]["reason"] == "ambiguous_mapping"
    ), "Ambiguous mapping did not record the expected unresolved reason"
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
    assert result.impacts == [], "No-match mapping emitted deterministic impacts"
    unresolved = result.diagnostics["unresolved"]
    assert unresolved, "No-match mapping did not record unresolved diagnostics"
    assert (
        unresolved[0]["reason"] == "no_matching_indicator"
    ), "No-match mapping did not record the expected unresolved reason"
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

    assert event.extraction_status == "provisional", "Degraded hold did not mark provisional"
    assert (
        event.event_summary == "Stable canonical summary"
    ), "Degraded hold overwrote canonical event summary"
    assert (
        event.extracted_what == "Canonical extraction"
    ), "Degraded hold overwrote canonical extraction text"
    assert event.categories == ["military"], "Degraded hold overwrote canonical categories"
    provisional = event.provisional_extraction
    assert (
        provisional["summary"] == "Held degraded summary"
    ), "Provisional payload did not retain degraded summary"
    assert (
        provisional["replay_enqueued"] is True
    ), "Provisional payload did not record replay enqueue state"
    assert provisional["policy"] == {
        "degraded_llm": True
    }, "Provisional payload did not record degraded policy metadata"
    return {
        "restored_summary": event.event_summary,
        "provisional_summary": provisional["summary"],
        "replay_enqueued": provisional["replay_enqueued"],
        "policy": provisional["policy"],
    }


def _eval_report_fallback_grounded() -> dict[str, Any]:
    prompt_path = _REPO_ROOT / "ai/prompts/weekly_report.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
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
    assert result.provisional is True, "Fallback report did not stay provisional"
    assert result.grounding_status == "fallback", "Supported fallback report was not grounded"
    assert result.grounding_violation_count == 0, "Supported fallback report recorded violations"
    assert result.grounding_references is None, "Supported fallback report emitted violations"
    assert (
        "Confidence is moderate" in result.narrative
    ), "Fallback report did not carry bounded uncertainty language"
    return {
        "grounding_status": result.grounding_status,
        "grounding_violation_count": result.grounding_violation_count,
        "provisional": result.provisional,
    }


def _eval_report_fallback_flags_unsupported_claims() -> dict[str, Any]:
    prompt_path = _REPO_ROOT / "ai/prompts/weekly_report.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
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
    assert (
        result.grounding_status == "flagged"
    ), "Unsupported fallback report claims were not surfaced as flagged"
    assert (
        result.grounding_violation_count >= 1
    ), "Unsupported fallback report claims did not increment violation count"
    references = result.grounding_references or {}
    assert references.get(
        "unsupported_claims"
    ), "Unsupported fallback report claims did not record grounding references"
    return {
        "grounding_status": result.grounding_status,
        "grounding_violation_count": result.grounding_violation_count,
        "unsupported_claims": references["unsupported_claims"],
    }


def _eval_weekly_report_prompt_contract() -> dict[str, Any]:
    prompt_path = _REPO_ROOT / "ai/prompts/weekly_report.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    required_fragments = (
        "Every narrative claim must be directly supported by the provided structured payload",
        "explicitly framed as uncertainty/inference",
        "If evidence is sparse, conflicting, or low-coverage",
    )
    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert not missing, "Weekly report prompt is missing grounding fragments: " + ", ".join(missing)
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
    assert prompt_changed != base_key, "Prompt change did not invalidate cache key"
    assert schema_changed != base_key, "Schema change did not invalidate cache key"
    assert overrides_changed != base_key, "Request override change did not invalidate cache key"
    return {
        "base_key_prefix": base_key.split(":")[:4],
        "invalidated_inputs": ["prompt_template", "schema_payload", "request_overrides"],
    }


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
