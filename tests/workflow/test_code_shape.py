from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from tools.horadus.python.horadus_workflow.code_shape import (
    _is_irrefutable_match_pattern,
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
production_member_complexity = 18
test_member_complexity = 20

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
production_member_complexity = 18
test_member_complexity = 20

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
production_member_complexity = 18
test_member_complexity = 20

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
production_member_complexity = 4
test_member_complexity = 20

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
max_lines = 25
[legacy_files.member_max_lines]
"ok" = 12
[legacy_files.member_max_complexity]
"ok" = 8
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any("module override is stale" in line for line in lines)
    assert any(
        "member override is stale: ok now fits the default member budget" in line for line in lines
    )
    assert any("member complexity override is stale: ok now fits" in line for line in lines)


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
production_member_complexity = 18
test_member_complexity = 20

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
production_member_complexity = 18
test_member_complexity = 20

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
                "        if True:",
                "            return 1",
                "        return 0",
                "",
                "    @value.setter",
                "    def value(self, new_value: int) -> None:",
                "        pass",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "duplicate.py")

    assert measurement.member_lines["Example.value"] == 5
    assert measurement.member_complexities["Example.value"] == 2


def test_measure_python_file_tracks_member_complexity_without_nested_defs(
    tmp_path: Path,
) -> None:
    _write_file(
        tmp_path,
        "src/complexity.py",
        "\n".join(
            [
                "def outer(flag: bool, items: list[int]) -> int:",
                "    def inner(value: int) -> int:",
                "        if value > 0:",
                "            return value",
                "        return 0",
                "",
                "    if flag and items:",
                "        return sum(item for item in items if item % 2 == 0)",
                "    return inner(0)",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "complexity.py")

    assert measurement.member_complexities["outer"] == 4
    assert measurement.member_complexities["outer.inner"] == 2


def test_measure_python_file_tracks_supported_complexity_branch_nodes(tmp_path: Path) -> None:
    _write_file(
        tmp_path,
        "src/branch_nodes.py",
        "\n".join(
            [
                "class Wrapper:",
                "    def run(self, items, stream, flag: bool) -> int:",
                "        class Local:",
                "            def branch(self) -> int:",
                "                return 1",
                "",
                "        def helper(value: int) -> int:",
                "            return value",
                "",
                "        async def async_helper() -> int:",
                "            return 1",
                "",
                "        formatter = lambda value: value",
                "        result = 1 if flag else 0",
                "        values = [item for item in items if item % 2 == 0]",
                "        pairs = {item for item in items if item % 3 == 0}",
                "        lookup = {str(item): item for item in items if item > 1}",
                "        total = sum(item for item in items if item > 2)",
                "        for item in items:",
                "            if item > 5:",
                "                result += item",
                "        while result < 3:",
                "            result += 1",
                "        try:",
                "            result += formatter(helper(total))",
                "        except ValueError:",
                "            result = 0",
                "        else:",
                "            result += 1",
                "        match result:",
                "            case 0:",
                "                return len(values)",
                "            case other if other > 1:",
                "                return len(pairs) + len(lookup) + total",
                "        return Local().branch() + async_helper().send(None)",
                "",
                "async def iterate(stream) -> int:",
                "    async for item in stream:",
                "        if item > 0:",
                "            return item",
                "    return 0",
                "",
                "def try_only(value: int) -> int:",
                "    try:",
                "        return value",
                "    except ValueError:",
                "        return 0",
                "",
                "def try_star_only(value: int) -> int:",
                "    try:",
                "        result = value",
                "    except* ValueError:",
                "        result = 0",
                "    return result",
                "",
                "def match_with_default(value: int) -> int:",
                "    match value:",
                "        case 0:",
                "            return 0",
                "        case _:",
                "            return 1",
                "",
                "def match_with_capture_default(value: int) -> int:",
                "    match value:",
                "        case 0:",
                "            return 0",
                "        case other:",
                "            return other",
                "",
                "def assertive(flag: bool) -> None:",
                "    assert flag",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "branch_nodes.py")

    assert measurement.member_complexities["Wrapper.run"] == 13
    assert measurement.member_complexities["iterate"] == 3
    assert measurement.member_complexities["try_only"] == 2
    assert measurement.member_complexities["try_star_only"] == 2
    assert measurement.member_complexities["match_with_default"] == 2
    assert measurement.member_complexities["match_with_capture_default"] == 2
    assert measurement.member_complexities["assertive"] == 2


def test_measure_python_file_counts_lambda_branches_toward_enclosing_complexity(
    tmp_path: Path,
) -> None:
    _write_file(
        tmp_path,
        "src/lambda_complexity.py",
        "\n".join(
            [
                "def outer(flag: bool, items: list[int]) -> int:",
                "    picker = lambda value: 0 if flag and value else 1",
                "    return sum(picker(item) for item in items)",
            ]
        )
        + "\n",
    )

    measurement = measure_python_file(tmp_path, tmp_path / "src" / "lambda_complexity.py")

    assert measurement.member_complexities["outer"] == 4


def test_irrefutable_match_pattern_helper_recognizes_alias_and_or_defaults() -> None:
    alias_pattern = (
        ast.parse("match value:\n    case _ as other:\n        pass\n").body[0].cases[0].pattern
    )
    or_pattern = (
        ast.parse("match value:\n    case 0 | other:\n        pass\n").body[0].cases[0].pattern
    )

    assert _is_irrefutable_match_pattern(alias_pattern) is True
    assert _is_irrefutable_match_pattern(or_pattern) is True


def test_run_code_shape_check_flags_member_complexity_budget_violations(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_branchy(flag: bool, items: list[int]) -> int:",
                "    if flag and items:",
                "        return 1",
                "    if items:",
                "        return sum(item for item in items if item % 2 == 0)",
                "    return 0",
            ]
        )
        + "\n",
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
production_member_complexity = 4
test_member_complexity = 20

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any("too_branchy has cyclomatic complexity 5; budget is 4" in line for line in lines)


def test_run_code_shape_check_uses_test_member_complexity_budget(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_branchy.py",
        "\n".join(
            [
                "def too_branchy(flag: bool, items: list[int]) -> int:",
                "    if flag and items:",
                "        return 1",
                "    if items:",
                "        return sum(item for item in items if item % 2 == 0)",
                "    return 0",
            ]
        )
        + "\n",
    )
    _track_paths(tmp_path, "tests/test_branchy.py")
    policy_path = _write_policy(
        tmp_path,
        """
[budgets]
production_module_lines = 20
test_module_lines = 30
production_function_lines = 10
test_function_lines = 12
production_member_complexity = 99
test_member_complexity = 4

[paths]
include_roots = ["tests"]
exclude_globs = ["**/__pycache__/**"]
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(result)

    assert any("too_branchy has cyclomatic complexity 5; budget is 4" in line for line in lines)


def test_run_code_shape_check_allows_legacy_member_complexity_but_blocks_regressions(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_branchy(flag: bool, items: list[int]) -> int:",
                "    if flag and items:",
                "        return 1",
                "    if items:",
                "        return sum(item for item in items if item % 2 == 0)",
                "    return 0",
            ]
        )
        + "\n",
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
production_member_complexity = 4
test_member_complexity = 20

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
[legacy_files.member_max_complexity]
"too_branchy" = 5
""".strip(),
    )

    first_result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    assert first_result.issues == ()

    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_branchy(flag: bool, items: list[int], fallback: int) -> int:",
                "    if flag and items:",
                "        return 1",
                "    if items:",
                "        return sum(item for item in items if item % 2 == 0)",
                "    if fallback > 0:",
                "        return fallback",
                "    return 0",
            ]
        )
        + "\n",
    )

    regressed = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)
    lines = render_code_shape_issues(regressed)

    assert any(
        "too_branchy has cyclomatic complexity 6; allowlisted maximum is 5" in line
        for line in lines
    )


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
production_member_complexity = 18
test_member_complexity = 20

[paths]
include_roots = ["src", "tests"]
exclude_globs = ["**/__pycache__/**"]

[[legacy_files]]
path = "src/app.py"
[legacy_files.member_max_lines]
"missing_member" = 12
[legacy_files.member_max_complexity]
"missing_complexity_member" = 6

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
    assert any(
        "member complexity override is stale: missing_complexity_member no longer exists" in line
        for line in lines
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
production_member_complexity = 18
test_member_complexity = 20

[paths]
include_roots = ["src"]
exclude_globs = []
""".strip(),
    )

    result = run_code_shape_check(repo_root=tmp_path, policy_path=policy_path)

    assert result.issues == ()
