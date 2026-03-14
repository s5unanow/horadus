from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.horadus.python.horadus_workflow.code_shape import (
    measure_python_file,
    render_code_shape_issues,
    run_code_shape_check,
)

pytestmark = pytest.mark.unit


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Code Shape Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "code-shape-tests@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _track_paths(repo_root: Path, *relative_paths: str) -> None:
    subprocess.run(
        ["git", "add", *relative_paths],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_policy(repo_root: Path, body: str) -> Path:
    policy_path = repo_root / "config" / "quality" / "code_shape.toml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(body, encoding="utf-8")
    return policy_path


def test_run_code_shape_check_passes_for_files_within_budget(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "def ok() -> int:\n    return 1\n",
    )
    _track_paths(tmp_path, "src/app.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 20
test_module_lines = 30
production_function_lines = 10
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()
    assert render_code_shape_issues(result) == ()


def test_run_code_shape_check_flags_new_module_and_member_budget_violations(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_long() -> int:",
                "    value = 0",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    return value",
            ]
        )
        + "\n",
    )
    _track_paths(tmp_path, "src/app.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 4
test_module_lines = 30
production_function_lines = 4
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any("module has 6 lines; budget is 4" in line for line in lines)
    assert any("too_long spans 6 lines; budget is 4" in line for line in lines)


def test_run_code_shape_check_allows_legacy_limits_but_blocks_regressions(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_long() -> int:",
                "    value = 0",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    return value",
            ]
        )
        + "\n",
    )
    _track_paths(tmp_path, "src/app.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 4
test_module_lines = 30
production_function_lines = 4
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
max_lines = 7
[legacy_files.member_max_lines]
"too_long" = 7
""".strip(),
    )

    first_result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    assert first_result.issues == ()

    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_long() -> int:",
                "    value = 0",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    return value",
            ]
        )
        + "\n",
    )

    regressed = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(regressed)

    assert any("module has 8 lines; allowlisted maximum is 7" in line for line in lines)
    assert any("too_long spans 8 lines; allowlisted maximum is 7" in line for line in lines)


def test_run_code_shape_check_flags_stale_overrides(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "def ok() -> int:\n    return 1\n",
    )
    _track_paths(tmp_path, "src/app.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 20
test_module_lines = 30
production_function_lines = 10
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
max_lines = 25
[legacy_files.member_max_lines]
"ok" = 12
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any("module override is stale" in line for line in lines)
    assert any(
        "member override is stale: ok now fits the default member budget" in line for line in lines
    )


def test_run_code_shape_check_ignores_untracked_python_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(tmp_path, "src/app.py", "def ok() -> int:\n    return 1\n")
    _write_file(
        tmp_path,
        "src/debug_tmp.py",
        "\n".join(
            [
                "def too_long() -> int:",
                "    value = 0",
                "    value += 1",
                "    value += 1",
                "    value += 1",
                "    return value",
            ]
        )
        + "\n",
    )
    _track_paths(tmp_path, "src/app.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 4
test_module_lines = 30
production_function_lines = 4
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()


def test_run_code_shape_check_ignores_tracked_non_python_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(tmp_path, "src/app.py", "def ok() -> int:\n    return 1\n")
    _write_file(tmp_path, "src/notes.txt", "tracked but not python\n")
    _track_paths(tmp_path, "src/app.py", "src/notes.txt")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 4
test_module_lines = 30
production_function_lines = 4
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()


def test_measure_python_file_tracks_nested_class_members(tmp_path: Path) -> None:
    _write_file(
        tmp_path,
        "src/nested.py",
        "\n".join(
            [
                "class Outer:",
                "    class Inner:",
                "        def run(self) -> int:",
                "            return 1",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "nested.py")

    assert measurement.member_lines["Outer.Inner.run"] == 2


def test_measure_python_file_counts_decorator_lines_in_member_span(tmp_path: Path) -> None:
    _write_file(
        tmp_path,
        "src/decorated.py",
        "\n".join(
            [
                "def deco(func):",
                "    return func",
                "",
                "@deco",
                "def run() -> int:",
                "    return 1",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "decorated.py")

    assert measurement.member_lines["run"] == 3


def test_measure_python_file_keeps_max_span_for_duplicate_member_names(tmp_path: Path) -> None:
    _write_file(
        tmp_path,
        "src/duplicate.py",
        "\n".join(
            [
                "class Example:",
                "    @property",
                "    def value(self) -> int:",
                "        return 1",
                "",
                "    @value.setter",
                "    def value(self, new_value: int) -> None:",
                "        pass",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "duplicate.py")

    assert measurement.member_lines["Example.value"] == 3


def test_run_code_shape_check_honors_excludes_and_flags_missing_override_targets(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_file(tmp_path, "src/app.py", "def ok() -> int:\n    return 1\n")
    _write_file(tmp_path, "src/__pycache__/ignored.py", "def ignored() -> int:\n    return 1\n")
    _track_paths(tmp_path, "src/app.py", "src/__pycache__/ignored.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 20
test_module_lines = 30
production_function_lines = 10
test_function_lines = 12

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
[legacy_files.member_max_lines]
"missing_member" = 12

[[legacy_files]]
path = "src/missing.py"
max_lines = 25
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any(
        "member override is stale: missing_member no longer exists" in line for line in lines
    )
    assert any("legacy override is stale: file no longer exists" in line for line in lines)
    assert result.errors == result.issues


def test_run_code_shape_check_skips_pycache_without_glob_and_ignores_plain_statements(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/plain.py",
        "VALUE = 1\n\ndef ok() -> int:\n    return VALUE\n",
    )
    _write_file(tmp_path, "src/__pycache__/ignored.py", "def ignored() -> int:\n    return 1\n")
    _track_paths(tmp_path, "src/plain.py", "src/__pycache__/ignored.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 20
test_module_lines = 30
production_function_lines = 10
test_function_lines = 12

[paths]
include_roots = ["src"]
exclude_globs = []
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()
