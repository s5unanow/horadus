"""Unit tests for scripts/task_context_pack.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "task_context_pack.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_task_context_pack_prints_task_context() -> None:
    result = _run("TASK-292")
    assert result.returncode == 0
    assert "# Context Pack: TASK-292" in result.stdout
    assert "## Suggested Validation Commands" in result.stdout
    assert "make agent-check" in result.stdout


def test_task_context_pack_supports_explicit_archive_lookup() -> None:
    result = _run("TASK-164", "--include-archive")
    assert result.returncode == 0
    assert "# Context Pack: TASK-164" in result.stdout


def test_task_context_pack_rejects_invalid_task_id() -> None:
    result = _run("invalid")
    assert result.returncode == 1
    assert "Invalid task id" in result.stdout
