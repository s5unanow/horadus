from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import src.eval.behavior as behavior_module

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
