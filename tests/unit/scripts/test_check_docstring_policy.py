from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_docstring_policy.py"

pytestmark = pytest.mark.unit


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_policy(repo_root: Path, body: str) -> Path:
    policy_path = repo_root / "config" / "quality" / "docstring_policy.toml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(body.strip(), encoding="utf-8")
    return policy_path


def test_check_docstring_policy_script_passes_for_compliant_targets(tmp_path: Path) -> None:
    _write_file(
        tmp_path,
        "src/app.py",
        "\n".join(
            [
                '"""Application surface."""',
                "",
                "def public_api() -> None:",
                '    """Run the public API."""',
                "    return None",
            ]
        )
        + "\n",
    )
    policy_path = _write_policy(
        tmp_path,
        """
[policy]
require_module_docstrings = true
require_public_class_docstrings = true
require_public_function_docstrings = true
require_public_method_docstrings = true
complex_member_min_lines = 10

[[targets]]
path = "src/app.py"
reason = "Application surface"
""",
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
    assert result.stdout.strip() == "Docstring policy check passed."


def test_check_docstring_policy_script_reports_failure_details(tmp_path: Path) -> None:
    _write_file(tmp_path, "src/app.py", "def public_api() -> None:\n    return None\n")
    policy_path = _write_policy(
        tmp_path,
        """
[policy]
require_module_docstrings = true
require_public_class_docstrings = true
require_public_function_docstrings = true
require_public_method_docstrings = true
complex_member_min_lines = 10

[[targets]]
path = "src/app.py"
reason = "Application surface"
""",
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
        "ERROR [member-docstring] src/app.py: public_api is missing a docstring "
        "(public function on selected high-value path)" in result.stdout
    )
    assert (
        "ERROR [module-docstring] src/app.py: module docstring required for selected "
        "high-value path (Application surface)" in result.stdout
    )
