from __future__ import annotations

import json
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

_REAL_PRE_MERGE_TASK_CLOSURE_BLOCKER = task_commands_module._pre_merge_task_closure_blocker
_REAL_BRANCH_HEAD_ALIGNMENT_BLOCKER = task_commands_module._branch_head_alignment_blocker


def _closed_task_closure_state(task_id: str) -> task_repo_module.TaskClosureState:
    return task_repo_module.TaskClosureState(
        task_id=task_repo_module.normalize_task_id(task_id),
        present_in_backlog=False,
        active_sprint_lines=[],
        present_in_completed=True,
        present_in_closed_archive=True,
        closed_archive_path="archive/closed_tasks/2026-Q1.md",
    )


def _disable_outdated_thread_auto_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("should not resolve outdated review threads")
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda task_id: _closed_task_closure_state(task_id),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_needs_pre_review_fresh_review_request",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_branch_head_alignment_blocker",
        lambda **_kwargs: None,
    )


def _review_gate_process(
    *,
    status: str = "pass",
    reason: str = "silent_timeout_allow",
    reviewed_head_oid: str = "head-sha",
    current_head_oid: str | None = None,
    summary: str | None = None,
    clean_current_head_review: bool = False,
    summary_thumbs_up: bool = False,
    actionable_lines: list[str] | None = None,
    timed_out: bool = False,
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    payload = {
        "status": status,
        "reason": reason,
        "reviewer_login": "chatgpt-codex-connector[bot]",
        "reviewed_head_oid": reviewed_head_oid,
        "current_head_oid": current_head_oid or reviewed_head_oid,
        "clean_current_head_review": clean_current_head_review,
        "summary_thumbs_up": summary_thumbs_up,
        "actionable_comment_count": 1 if reason == "actionable_comments" else 0,
        "actionable_review_count": 1 if reason == "actionable_reviews" else 0,
        "timeout_seconds": 600,
        "timed_out": timed_out,
        "summary": summary
        or (
            "review gate timeout: no actionable current-head review feedback from "
            f"chatgpt-codex-connector[bot] for {reviewed_head_oid} within 600s. "
            "Continuing due to timeout policy=allow."
            if reason == "silent_timeout_allow"
            else "review gate passed"
        ),
        "actionable_lines": actionable_lines or [],
    }
    return _completed(["review"], returncode=returncode, stdout=json.dumps(payload))
