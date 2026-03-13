from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_code_shape.py"


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_policy(repo_root: Path, body: str) -> Path:
    policy_path = repo_root / "config" / "quality" / "code_shape.toml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(body, encoding="utf-8")
    return policy_path


def test_check_code_shape_script_passes_for_clean_repo(tmp_path: Path) -> None:
    _write_file(tmp_path, "src/app.py", "def ok() -> int:\n    return 1\n")
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
    assert "ERROR [module-lines] src/app.py: module has 7 lines; budget is 4" in result.stdout
    assert "ERROR [member-lines] src/app.py: too_long spans 6 lines; budget is 4" in result.stdout
