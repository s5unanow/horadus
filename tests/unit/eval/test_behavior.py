from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import src.eval.behavior as behavior_module
import src.eval.behavior_cases as behavior_cases_module
import src.eval.behavior_cases_retrieval as behavior_cases_retrieval_module

pytestmark = pytest.mark.unit


def test_run_behavior_evals_writes_contract_labeled_artifact(tmp_path: Path) -> None:
    result = behavior_module.run_behavior_evals(output_dir=tmp_path)

    assert result.passes_validation is True
    assert result.failed_cases == 0
    assert result.selected_cases == len(result.case_results)
    assert {
        "taxonomy-safety",
        "degraded-mode-safety",
        "report-grounding",
        "context-retrieval",
    }.issubset(set(behavior_module.available_behavior_suites()))

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["passes_validation"] is True
    assert payload["summary"]["selected_cases"] == result.selected_cases
    assert all(case["production_contract"] for case in payload["cases"])
    assert all(case["expected_behavior"] for case in payload["cases"])


def test_run_behavior_evals_can_filter_by_suite_and_tag(tmp_path: Path) -> None:
    result = behavior_module.run_behavior_evals(
        output_dir=tmp_path,
        suites=["taxonomy-safety"],
        tags=["taxonomy"],
    )

    assert result.selected_suites == ("taxonomy-safety",)
    assert result.selected_tags == ("taxonomy",)
    assert result.selected_cases == 2
    assert all(case.suite == "taxonomy-safety" for case in result.case_results)
    assert all("taxonomy" in case.tags for case in result.case_results)


def test_context_retrieval_behavior_suite_records_phase_and_basis(tmp_path: Path) -> None:
    result = behavior_module.run_behavior_evals(
        output_dir=tmp_path,
        suites=["context-retrieval"],
    )

    assert result.passes_validation is True
    assert result.selected_suites == ("context-retrieval",)
    assert result.selected_cases == 2

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["suites"] == [
        {
            "failed_cases": 0,
            "selected_cases": 2,
            "suite": "context-retrieval",
        }
    ]

    for case in payload["cases"]:
        assert case["suite"] == "context-retrieval"
        evidence = case["evidence"]
        assert evidence["retrieval_mode"] == "implement"
        assert evidence["retrieval_phase"] == "phase-1-cli-first"
        assert evidence["authoritative_source_basis"]["policy_registry_id"] == (
            "implement-mode-legacy-policy-v1"
        )


def test_run_case_and_suite_summary_record_failures() -> None:
    case = behavior_module.BehaviorEvalCaseDefinition(
        case_id="failing-case",
        title="Failing case",
        suite="taxonomy-safety",
        tags=("taxonomy",),
        production_contract="contract",
        expected_behavior="expected",
        surface_paths=("src/processing/trend_impact_mapping.py",),
        runner=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = behavior_module._run_case(case)
    summary = behavior_module._suite_summary((result,))

    assert result.passed is False
    assert result.failure_message == "boom"
    assert summary == [
        {
            "suite": "taxonomy-safety",
            "selected_cases": 1,
            "failed_cases": 1,
        }
    ]


def test_behavior_cases_require_raises_on_false_condition() -> None:
    with pytest.raises(ValueError, match="boom"):
        behavior_cases_module._require(False, "boom")


def test_retrieval_behavior_cases_require_raises_on_false_condition() -> None:
    with pytest.raises(ValueError, match="boom"):
        behavior_cases_retrieval_module._require(False, "boom")


def test_degraded_behavior_case_checks_full_restore_contract() -> None:
    evidence = behavior_cases_module._eval_degraded_hold_preserves_canonical_extraction()

    assert evidence["restored_fields_checked"] == [
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
    ]
    assert evidence["provisional_fields_checked"] == [
        "summary",
        "extracted_claims",
        "provenance",
        "extracted_when",
        "replay_enqueued",
        "policy",
    ]


def test_semantic_cache_behavior_case_tracks_api_mode_and_other_basis_inputs() -> None:
    evidence = behavior_cases_module._eval_semantic_cache_basis_changes_invalidate_keys()

    assert evidence["invalidated_inputs"] == [
        "provider",
        "model",
        "reasoning_effort",
        "api_mode",
        "prompt_template",
        "schema_payload",
        "request_overrides",
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"suites": ["unknown"]}, "Unknown behavior suite(s): unknown"),
        ({"tags": ["unknown"]}, "Unknown behavior tag(s): unknown"),
        (
            {"suites": ["taxonomy-safety"], "tags": ["grounding"]},
            "No behavior eval cases matched the requested suite/tag filters.",
        ),
    ],
)
def test_run_behavior_evals_rejects_invalid_filters(
    tmp_path: Path,
    kwargs: dict[str, list[str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        behavior_module.run_behavior_evals(output_dir=tmp_path, **kwargs)
