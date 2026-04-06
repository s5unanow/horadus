"""Deterministic behavior-oriented eval suites for high-risk runtime contracts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.eval import artifact_provenance as provenance
from src.eval.behavior_cases import behavior_case_definitions
from src.eval.behavior_types import (
    BehaviorEvalCaseDefinition,
    BehaviorEvalCaseResult,
    BehaviorEvalRunResult,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESULT_PREFIX = "behavior"


def available_behavior_suites() -> tuple[str, ...]:
    """Return the known behavior-eval suite names."""

    return tuple(sorted({case.suite for case in behavior_case_definitions()}))


def available_behavior_tags() -> tuple[str, ...]:
    """Return the known behavior-eval tags."""

    tags: set[str] = set()
    for case in behavior_case_definitions():
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
    _validate_filters(suites=normalized_suites, tags=normalized_tags)

    definitions = _select_cases(
        case_definitions=behavior_case_definitions(),
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
        total_cases=len(behavior_case_definitions()),
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


def _validate_filters(*, suites: tuple[str, ...], tags: tuple[str, ...]) -> None:
    available_suites = set(available_behavior_suites())
    available_tags = set(available_behavior_tags())

    unknown_suites = sorted(set(suites) - available_suites)
    if unknown_suites:
        msg = (
            "Unknown behavior suite(s): "
            + ", ".join(unknown_suites)
            + ". Available: "
            + ", ".join(sorted(available_suites))
        )
        raise ValueError(msg)

    unknown_tags = sorted(set(tags) - available_tags)
    if unknown_tags:
        msg = (
            "Unknown behavior tag(s): "
            + ", ".join(unknown_tags)
            + ". Available: "
            + ", ".join(sorted(available_tags))
        )
        raise ValueError(msg)


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
            "total_cases": len(behavior_case_definitions()),
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
