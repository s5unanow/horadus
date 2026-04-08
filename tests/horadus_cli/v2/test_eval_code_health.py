from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.horadus.python.horadus_cli.app import _build_parser
from tools.horadus.python.horadus_cli.ops_commands import _handle_eval_code_health
from tools.horadus.python.horadus_cli.result import ExitCode
from tools.horadus.python.horadus_workflow.code_health import (
    CodeHealthFileResult,
    CodeHealthMetrics,
    CodeHealthRunResult,
)

pytestmark = pytest.mark.unit


def test_build_parser_accepts_eval_code_health_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "code-health",
            "--base-ref",
            "origin/main",
            "--head-ref",
            "HEAD",
            "--merge-base-target",
            "main",
            "--output-dir",
            "ai/eval/results",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "code-health"
    assert args.base_ref == "origin/main"
    assert args.head_ref == "HEAD"
    assert args.merge_base_target == "main"
    assert args.output_dir == "ai/eval/results"


def test_handle_eval_code_health_returns_validation_error_for_bad_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.run_code_health_eval",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad refs")),
    )

    result = _handle_eval_code_health(
        SimpleNamespace(
            output_dir="ai/eval/results",
            base_ref="bad",
            head_ref="HEAD",
            merge_base_target="main",
        )
    )

    assert result.data == {"error": "bad refs"}
    assert any("Code-health eval configuration error: bad refs" in line for line in result.lines)
    assert result.exit_code == ExitCode.VALIDATION_ERROR


def test_handle_eval_code_health_returns_environment_error_when_repo_root_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.workflow_task_repo.repo_root",
        lambda: (_ for _ in ()).throw(RuntimeError("missing repo")),
    )

    result = _handle_eval_code_health(
        SimpleNamespace(
            output_dir="ai/eval/results",
            base_ref="HEAD~1",
            head_ref="HEAD",
            merge_base_target="main",
        )
    )

    assert result.data == {"error": "missing repo"}
    assert result.error_lines == ["Code-health eval environment error: missing repo"]
    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR


def test_handle_eval_code_health_reports_run_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = CodeHealthRunResult(
        output_path=tmp_path / "code-health.json",
        passes_validation=False,
        comparison_mode="explicit",
        base_ref="HEAD~1",
        resolved_base_ref="abc123",
        head_ref="HEAD",
        resolved_head_ref="def456",
        merge_base_target=None,
        compared_files=2,
        flagged_files=1,
        file_results=(
            CodeHealthFileResult(
                path="src/app.py",
                change_type="modified",
                base_metrics=CodeHealthMetrics(2, 1, 1, 2, 2, 1, 1),
                head_metrics=CodeHealthMetrics(2, 1, 2, 2, 2, 1, 1),
                delta={"statement_count": 1},
                worsened_metrics=("statement_count",),
                improved_metrics=(),
            ),
        ),
    )
    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.run_code_health_eval",
        lambda **_kwargs: result,
    )

    command_result = _handle_eval_code_health(
        SimpleNamespace(
            output_dir=str(tmp_path),
            base_ref="HEAD~1",
            head_ref="HEAD",
            merge_base_target="main",
        )
    )

    assert command_result.data["output_path"].endswith("code-health.json")
    assert command_result.data["passes_validation"] is False
    assert command_result.data["flagged_files"] == 1
    assert command_result.data["regressions"] == [
        {
            "path": "src/app.py",
            "change_type": "modified",
            "worsened_metrics": ["statement_count"],
        }
    ]
    assert any("Flagged regressions: 1" in line for line in command_result.lines)
    assert any("src/app.py: statement_count" in line for line in command_result.lines)
    assert command_result.exit_code == ExitCode.VALIDATION_ERROR


def test_handle_eval_code_health_resolves_repo_root_instead_of_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    subdir = repo_root / "tools" / "nested"
    subdir.mkdir(parents=True)
    captured: dict[str, object] = {}
    result = CodeHealthRunResult(
        output_path=tmp_path / "code-health.json",
        passes_validation=True,
        comparison_mode="explicit",
        base_ref="HEAD~1",
        resolved_base_ref="abc123",
        head_ref="HEAD",
        resolved_head_ref="def456",
        merge_base_target=None,
        compared_files=0,
        flagged_files=0,
        file_results=(),
    )

    monkeypatch.chdir(subdir)
    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.workflow_task_repo.repo_root",
        lambda: repo_root,
    )

    def fake_run_code_health_eval(**kwargs: object) -> CodeHealthRunResult:
        captured.update(kwargs)
        return result

    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.run_code_health_eval",
        fake_run_code_health_eval,
    )

    command_result = _handle_eval_code_health(
        SimpleNamespace(
            output_dir=str(tmp_path),
            base_ref="HEAD~1",
            head_ref="HEAD",
            merge_base_target="main",
        )
    )

    assert command_result.exit_code == ExitCode.OK
    assert captured["repo_root"] == repo_root
    assert captured["repo_root"] != Path.cwd()


def test_handle_eval_code_health_omits_regression_section_when_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = CodeHealthRunResult(
        output_path=tmp_path / "code-health.json",
        passes_validation=True,
        comparison_mode="merge-base",
        base_ref="merge-base(main, HEAD)",
        resolved_base_ref="abc123",
        head_ref="HEAD",
        resolved_head_ref="def456",
        merge_base_target="main",
        compared_files=1,
        flagged_files=0,
        file_results=(),
    )
    monkeypatch.setattr(
        "tools.horadus.python.horadus_cli.ops_commands.run_code_health_eval",
        lambda **_kwargs: result,
    )

    command_result = _handle_eval_code_health(
        SimpleNamespace(
            output_dir=str(tmp_path),
            base_ref=None,
            head_ref="HEAD",
            merge_base_target="main",
        )
    )

    assert command_result.exit_code == ExitCode.OK
    assert command_result.data["regressions"] == []
    assert all(line != "Regressions:" for line in command_result.lines)


def test_build_parser_sets_code_health_handler() -> None:
    parser = _build_parser()
    args = parser.parse_args(["eval", "code-health"])

    assert args.handler is _handle_eval_code_health
