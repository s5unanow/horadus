from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.eval.behavior as behavior_module
import tools.horadus.python.horadus_app_cli_runtime as runtime_module
from tools.horadus.python.horadus_cli.app import _build_parser
from tools.horadus.python.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit


def test_build_parser_accepts_eval_behavior_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "behavior",
            "--output-dir",
            "ai/eval/results",
            "--suite",
            "taxonomy-safety",
            "--suite",
            "report-grounding",
            "--tag",
            "grounding",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "behavior"
    assert args.output_dir == "ai/eval/results"
    assert args.suite == ["taxonomy-safety", "report-grounding"]
    assert args.tag == ["grounding"]


def test_collect_eval_behavior_returns_validation_error_for_bad_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        behavior_module,
        "run_behavior_evals",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad filter")),
    )

    data, lines, exit_code = runtime_module._collect_eval_behavior(
        SimpleNamespace(output_dir="ai/eval/results", suite=["bad"], tag=None)
    )

    assert data == {"error": "bad filter"}
    assert any("Behavior eval configuration error: bad filter" in line for line in lines)
    assert exit_code == ExitCode.VALIDATION_ERROR


def test_collect_eval_behavior_reports_run_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = behavior_module.BehaviorEvalRunResult(
        output_path=tmp_path / "behavior.json",
        passes_validation=True,
        total_cases=7,
        selected_cases=2,
        passed_cases=2,
        failed_cases=0,
        selected_suites=("taxonomy-safety",),
        selected_tags=("taxonomy",),
        case_results=(),
    )
    monkeypatch.setattr(behavior_module, "run_behavior_evals", lambda **_kwargs: result)

    data, lines, exit_code = runtime_module._collect_eval_behavior(
        SimpleNamespace(output_dir=str(tmp_path), suite=["taxonomy-safety"], tag=["taxonomy"])
    )

    assert data["output_path"].endswith("behavior.json")
    assert data["passes_validation"] is True
    assert any("Selected cases: 2/7" in line for line in lines)
    assert any("Suites: taxonomy-safety" in line for line in lines)
    assert any("Tags: taxonomy" in line for line in lines)
    assert exit_code == ExitCode.OK


def test_collect_eval_behavior_reports_failed_cases_without_optional_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = behavior_module.BehaviorEvalRunResult(
        output_path=tmp_path / "behavior.json",
        passes_validation=False,
        total_cases=7,
        selected_cases=1,
        passed_cases=0,
        failed_cases=1,
        selected_suites=(),
        selected_tags=(),
        case_results=(
            behavior_module.BehaviorEvalCaseResult(
                case_id="failing-case",
                title="Failing case",
                suite="taxonomy-safety",
                tags=("taxonomy",),
                production_contract="contract",
                expected_behavior="expected",
                surface_paths=("src/processing/trend_impact_mapping.py",),
                passed=False,
                duration_ms=1,
                evidence=None,
                failure_message="boom",
            ),
        ),
    )
    monkeypatch.setattr(behavior_module, "run_behavior_evals", lambda **_kwargs: result)

    data, lines, exit_code = runtime_module._collect_eval_behavior(
        SimpleNamespace(output_dir=str(tmp_path), suite=None, tag=None)
    )

    assert data["passes_validation"] is False
    assert "Failed cases:" in lines
    assert "- failing-case: boom" in lines
    assert exit_code == ExitCode.VALIDATION_ERROR


def test_action_eval_behavior_wraps_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_collect_eval_behavior",
        lambda _args: ({"value": "x"}, ["line"], ExitCode.OK),
    )

    result = runtime_module._action_eval_behavior({"value": "x"})

    assert result["exit_code"] == ExitCode.OK
    assert result["data"] == {"value": "x"}
    assert result["lines"] == ["line"]
