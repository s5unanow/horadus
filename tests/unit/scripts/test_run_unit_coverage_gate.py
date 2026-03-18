"""Unit tests for scripts/run_unit_coverage_gate.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_unit_coverage_gate.sh"


def _run(*, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_run_unit_coverage_gate_accepts_override_command() -> None:
    result = _run(extra_env={"HORADUS_UNIT_COVERAGE_GATE_CMD": "printf 'coverage-ok\\n'"})

    assert result.returncode == 0
    assert "running overridden coverage gate command" in result.stdout
    assert "coverage-ok" in result.stdout


def test_run_unit_coverage_gate_propagates_failures_from_override_command() -> None:
    result = _run(extra_env={"HORADUS_UNIT_COVERAGE_GATE_CMD": "printf 'missing lines\\n'; false"})

    assert result.returncode != 0
    assert "running overridden coverage gate command" in result.stdout
    assert "missing lines" in result.stdout


def test_run_unit_coverage_gate_default_command_measures_scripts_scope() -> None:
    script_text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "src/, tools/, and scripts/" in script_text
    assert "--cov=scripts" in script_text
