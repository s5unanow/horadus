from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.horadus.python.horadus_workflow.code_health as code_health_module
from tools.horadus.python.horadus_workflow.code_health import run_code_health_eval
from tools.horadus.python.horadus_workflow.code_shape import load_code_shape_policy

pytestmark = pytest.mark.unit


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.name", "Code Health Tests")
    _git(repo_root, "config", "user.email", "code-health-tests@example.com")


def _write_policy(repo_root: Path) -> None:
    _write_file(
        repo_root,
        "config/quality/code_shape.toml",
        """
[budgets]
production_module_lines = 50
test_module_lines = 80
production_function_lines = 20
test_function_lines = 30
production_member_complexity = 10
test_member_complexity = 12

[paths]
include_roots = ["src", "tests", "tools", "scripts"]
exclude_globs = ["**/__pycache__/**"]
""".strip()
        + "\n",
    )


def _commit_all(repo_root: Path, message: str) -> str:
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", message)
    return _git(repo_root, "rev-parse", "HEAD")


def test_run_code_health_eval_flags_statement_growth_without_line_or_complexity_growth(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    base_ref = _commit_all(tmp_path, "base")

    _git(tmp_path, "checkout", "-b", "feature")
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    value = 1; return value\n")
    head_ref = _commit_all(tmp_path, "head")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )

    assert result.passes_validation is False
    assert result.compared_files == 1
    assert result.flagged_files == 1
    file_result = result.file_results[0]
    assert file_result.path == "src/app.py"
    assert file_result.worsened_metrics == ("statement_count",)
    assert file_result.base_metrics is not None
    assert file_result.head_metrics is not None
    assert file_result.base_metrics.module_lines == file_result.head_metrics.module_lines == 2
    assert (
        file_result.base_metrics.max_member_complexity
        == file_result.head_metrics.max_member_complexity
        == 1
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["passes_validation"] is False
    assert payload["summary"]["flagged_files"] == 1


def test_run_code_health_eval_reports_flat_modified_files_without_regressions(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    base_ref = _commit_all(tmp_path, "base")

    _git(tmp_path, "checkout", "-b", "feature")
    _write_file(tmp_path, "src/app.py", "def keep() -> int:\n    return 1\n")
    head_ref = _commit_all(tmp_path, "head")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )

    assert result.passes_validation is True
    assert result.flagged_files == 0
    assert result.file_results[0].change_type == "modified"
    assert result.file_results[0].worsened_metrics == ()
    assert result.file_results[0].improved_metrics == ()


def test_run_code_health_eval_reports_noop_diff_without_failures(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    base_ref = _commit_all(tmp_path, "base")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
        base_ref=base_ref,
        head_ref=base_ref,
    )

    assert result.passes_validation is True
    assert result.compared_files == 0
    assert result.flagged_files == 0
    assert result.file_results == ()


def test_run_code_health_eval_ignores_unaffected_non_python_diffs(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    base_ref = _commit_all(tmp_path, "base")

    _git(tmp_path, "checkout", "-b", "feature")
    _write_file(tmp_path, "README.md", "# Updated docs\n")
    head_ref = _commit_all(tmp_path, "docs-only")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )

    assert result.passes_validation is True
    assert result.compared_files == 0
    assert result.flagged_files == 0
    assert result.file_results == ()


def test_run_code_health_eval_defaults_to_merge_base_against_main(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    value = 1; return value\n")
    _commit_all(tmp_path, "base")

    _git(tmp_path, "checkout", "-b", "feature")
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    _commit_all(tmp_path, "head")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
    )

    assert result.comparison_mode == "merge-base"
    assert result.base_ref == "merge-base(main, HEAD)"
    assert result.head_ref == "HEAD"
    assert result.passes_validation is True
    assert result.flagged_files == 0
    assert result.file_results[0].improved_metrics == ("statement_count",)


def test_run_code_health_eval_treats_rename_with_edits_as_modified(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    _write_file(tmp_path, "src/app.py", "def run() -> int:\n    return 1\n")
    base_ref = _commit_all(tmp_path, "base")

    _git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "src" / "app.py").unlink()
    _write_file(tmp_path, "src/refined.py", "def run() -> int:\n    value = 1; return value\n")
    head_ref = _commit_all(tmp_path, "head")

    result = run_code_health_eval(
        output_dir=tmp_path / "artifacts",
        repo_root=tmp_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )

    assert result.flagged_files == 1
    assert result.file_results[0].path == "src/refined.py"
    assert result.file_results[0].change_type == "modified"
    assert result.file_results[0].worsened_metrics == ("statement_count",)


def test_code_health_helpers_cover_filtered_records_and_non_modified_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_repo(tmp_path)
    _write_policy(tmp_path)
    policy = load_code_shape_policy(tmp_path / "config/quality/code_shape.toml")
    monkeypatch.setattr(
        code_health_module,
        "_run_git_command",
        lambda *_args, **_kwargs: (
            "\nR100\tsrc/old.py\tsrc/new.py\nD\tsrc/deleted.py\nM\tREADME.md\nbroken\nM\tnot_tracked/app.py\n"
        ),
    )

    records = code_health_module._changed_python_records(
        repo_root=tmp_path,
        policy=policy,
        base_ref="base",
        head_ref="head",
    )

    assert records == (
        ("src/deleted.py", "src/deleted.py", None),
        ("src/new.py", "src/old.py", "src/new.py"),
    )

    measurement = SimpleNamespace(
        module_lines=2,
        callable_count=1,
        statement_count=1,
        member_lines={"run": 2},
        member_complexities={"run": 1},
    )
    sequence = iter((None, measurement))
    monkeypatch.setattr(
        code_health_module,
        "_measurement_for_ref",
        lambda **_kwargs: next(sequence),
    )
    added = code_health_module._build_file_result(
        repo_root=tmp_path,
        record=("src/new.py", None, "src/new.py"),
        base_ref="base",
        head_ref="head",
    )

    assert added.change_type == "added"
    assert added.worsened_metrics == ()
    assert added.improved_metrics == ()


def test_code_health_helpers_cover_missing_refs_and_git_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        code_health_module._measurement_for_ref(
            repo_root=tmp_path,
            ref_path=None,
            display_path="src/app.py",
            ref="HEAD",
        )
        is None
    )

    monkeypatch.setattr(
        code_health_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="missing"),
    )

    assert code_health_module._read_blob(repo_root=tmp_path, ref="HEAD", path="src/app.py") is None
    assert code_health_module._git_metadata(tmp_path, ("rev-parse", "HEAD")) is None
    assert (
        code_health_module._measurement_for_ref(
            repo_root=tmp_path,
            ref_path="src/app.py",
            display_path="src/app.py",
            ref="HEAD",
        )
        is None
    )

    with pytest.raises(ValueError, match="boom"):
        code_health_module._run_git_command(
            tmp_path,
            ("status",),
            error_context="boom",
        )

    measurement = SimpleNamespace(
        module_lines=2,
        callable_count=1,
        statement_count=1,
        member_lines={"run": 2},
        member_complexities={"run": 1},
    )
    assert (
        code_health_module._change_type(base_measurement=None, head_measurement=measurement)
        == "added"
    )
    assert (
        code_health_module._change_type(base_measurement=measurement, head_measurement=None)
        == "removed"
    )
    assert code_health_module._metrics_from_measurement(None) is None
    assert code_health_module._metric_delta(base_metrics=None, head_metrics=None) == {}
