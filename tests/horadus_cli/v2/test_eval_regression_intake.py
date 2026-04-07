from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.eval.regression_intake as intake_module
import tools.horadus.python.horadus_app_cli_runtime as runtime_module
from tools.horadus.python.horadus_cli.app import _build_parser
from tools.horadus.python.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit


def test_build_parser_accepts_eval_regression_intake_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "regression-intake",
            "--source-surface",
            "taxonomy-gap",
            "--input",
            "artifacts/taxonomy-gaps.json",
            "--output-dir",
            "ai/eval/results",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "regression-intake"
    assert args.source_surface == "taxonomy-gap"
    assert args.input == "artifacts/taxonomy-gaps.json"
    assert args.output_dir == "ai/eval/results"


def test_collect_eval_regression_intake_returns_validation_error_for_bad_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        intake_module,
        "run_regression_intake",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad input")),
    )

    data, lines, exit_code = runtime_module._collect_eval_regression_intake(
        SimpleNamespace(
            source_surface="taxonomy-gap",
            input="artifacts/taxonomy-gaps.json",
            output_dir="ai/eval/results",
        )
    )

    assert data == {"error": "bad input"}
    assert any("Regression intake configuration error: bad input" in line for line in lines)
    assert exit_code == ExitCode.VALIDATION_ERROR


def test_collect_eval_regression_intake_reports_run_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = intake_module.RegressionIntakeRunResult(
        output_path=tmp_path / "regression-intake.json",
        source_surface="report-grounding",
        total_records=3,
        emitted_cases=2,
    )
    monkeypatch.setattr(intake_module, "run_regression_intake", lambda **_kwargs: result)

    data, lines, exit_code = runtime_module._collect_eval_regression_intake(
        SimpleNamespace(
            source_surface="report-grounding",
            input="artifacts/reports.json",
            output_dir=str(tmp_path),
        )
    )

    assert data["output_path"].endswith("regression-intake.json")
    assert data["source_surface"] == "report-grounding"
    assert data["total_records"] == 3
    assert data["emitted_cases"] == 2
    assert any("Source surface: report-grounding" in line for line in lines)
    assert any("Emitted cases: 2" in line for line in lines)
    assert exit_code == ExitCode.OK


def test_action_eval_regression_intake_wraps_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_collect_eval_regression_intake",
        lambda _args: ({"value": "x"}, ["line"], ExitCode.OK),
    )

    result = runtime_module._action_eval_regression_intake({"value": "x"})

    assert result["exit_code"] == ExitCode.OK
    assert result["data"] == {"value": "x"}
    assert result["lines"] == ["line"]


def test_action_eval_regression_intake_omits_lines_for_empty_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_collect_eval_regression_intake",
        lambda _args: ({"value": "x"}, [], ExitCode.OK),
    )

    result = runtime_module._action_eval_regression_intake({"value": "x"})

    assert result["exit_code"] == ExitCode.OK
    assert result["data"] == {"value": "x"}
    assert "lines" not in result
