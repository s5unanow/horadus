from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_code_shape.py"


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Code Shape Tests"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "code-shape-tests@example.com"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )


def _track_paths(repo_root: Path, *relative_paths: str) -> None:
    subprocess.run(
        ["git", "add", *relative_paths],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_policy(repo_root: Path, body: str) -> Path:
    policy_path = repo_root / "config" / "quality" / "code_shape.toml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(body, encoding="utf-8")
    return policy_path


def test_check_code_shape_script_passes_for_clean_repo(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(tmp_path, "src/app.py", "def ok() -> int:\n    return 1\n")
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

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--repo-root",
            str(tmp_path),
            "--policy-file",
            str(policy_path.relative_to(tmp_path)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "Code shape check passed."


def test_check_code_shape_script_reports_failure_details(tmp_path: Path) -> None:
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

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--repo-root",
            str(tmp_path),
            "--policy-file",
            str(policy_path.relative_to(tmp_path)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "ERROR [module-lines] src/app.py: module has 6 lines; budget is 4" in result.stdout
    assert "ERROR [member-lines] src/app.py: too_long spans 6 lines; budget is 4" in result.stdout


def test_check_code_shape_script_reports_member_complexity_failures(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                "def too_branchy(flag: bool, items: list[int]) -> int:",
                "    if flag:",
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

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--repo-root",
            str(tmp_path),
            "--policy-file",
            str(policy_path.relative_to(tmp_path)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert (
        "ERROR [member-complexity] src/app.py: too_branchy has cyclomatic complexity 5; "
        "budget is 4" in result.stdout
    )


def test_check_code_shape_script_ignores_untracked_python_files(tmp_path: Path) -> None:
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

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--repo-root",
            str(tmp_path),
            "--policy-file",
            str(policy_path.relative_to(tmp_path)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "Code shape check passed."
