"""Unit tests for scripts/check_pr_task_scope.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_pr_task_scope.sh"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_guard(*, pr_branch: str, pr_body: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PR_BRANCH"] = pr_branch
    env["PR_BODY"] = pr_body

    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_pr_task_scope_accepts_multiline_pr_body() -> None:
    result = _run_guard(
        pr_branch="codex/task-125-pr-scope-guard-hardening",
        pr_body=("## Summary\n- Harden PR scope parsing\n\nPrimary-Task: TASK-125\n"),
    )

    assert result.returncode == 0
    assert "PR scope guard passed: TASK-125" in result.stdout


def test_check_pr_task_scope_accepts_escaped_newline_pr_body() -> None:
    result = _run_guard(
        pr_branch="codex/task-125-pr-scope-guard-hardening",
        pr_body=("## Summary\\n- Harden PR scope parsing\\n\\nPrimary-Task: TASK-125"),
    )

    assert result.returncode == 0
    assert "PR scope guard passed: TASK-125" in result.stdout


def test_check_pr_task_scope_rejects_missing_primary_task() -> None:
    result = _run_guard(
        pr_branch="codex/task-125-pr-scope-guard-hardening",
        pr_body="## Summary\n- no primary task line\n",
    )

    assert result.returncode == 1
    assert "Missing canonical task metadata field in PR body" in result.stdout


def test_check_pr_task_scope_rejects_mismatched_primary_task() -> None:
    result = _run_guard(
        pr_branch="codex/task-125-pr-scope-guard-hardening",
        pr_body="Primary-Task: TASK-124",
    )

    assert result.returncode == 1
    assert "branch task ID and Primary-Task mismatch" in result.stdout


def test_check_pr_task_scope_rejects_multiple_primary_task_lines() -> None:
    result = _run_guard(
        pr_branch="codex/task-125-pr-scope-guard-hardening",
        pr_body="Primary-Task: TASK-125\nPrimary-Task: TASK-126\n",
    )

    assert result.returncode == 1
    assert "multiple Primary-Task fields found in PR body" in result.stdout
