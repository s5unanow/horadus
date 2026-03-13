from __future__ import annotations

import subprocess
from pathlib import Path

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module

LIVE_TASK_ID = "TASK-901"
ARCHIVED_TASK_ID = "TASK-902"
BACKLOG_ONLY_TASK_ID = "TASK-903"
NON_APPLICABLE_TASK_ID = "TASK-904"
EXEC_PLAN_TASK_ID = "TASK-905"
EXEC_PLAN_NO_MARKER_TASK_ID = "TASK-906"


def _completed(
    args: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr=stderr
    )


def _task_snapshot(
    *,
    current_branch: str = "codex/task-259-done-state-verifier",
    branch_name: str | None = "codex/task-259-done-state-verifier",
    remote_branch_exists: bool = False,
    pr: task_commands_module.TaskPullRequest | None = None,
    working_tree_clean: bool = True,
    local_main_synced: bool | None = None,
    merge_commit_on_main: bool | None = None,
) -> task_commands_module.TaskLifecycleSnapshot:
    local_main_sha = None
    remote_main_sha = None
    if local_main_synced is not None:
        local_main_sha = "main-sha"
        remote_main_sha = "main-sha" if local_main_synced else "remote-sha"

    merge_commit_available_locally = None
    if pr is not None and pr.merge_commit_oid is not None:
        merge_commit_available_locally = merge_commit_on_main

    return task_commands_module.TaskLifecycleSnapshot(
        task_id="TASK-259",
        current_branch=current_branch,
        branch_name=branch_name,
        local_branch_names=[branch_name] if branch_name else [],
        remote_branch_names=[branch_name] if remote_branch_exists and branch_name else [],
        remote_branch_exists=remote_branch_exists,
        working_tree_clean=working_tree_clean,
        pr=pr,
        local_main_sha=local_main_sha,
        remote_main_sha=remote_main_sha,
        local_main_synced=local_main_synced,
        merge_commit_available_locally=merge_commit_available_locally,
        merge_commit_on_main=merge_commit_on_main,
        lifecycle_state="",
        strict_complete=False,
    )


def _seed_close_ledgers_repo(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-294: Archive closure",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Archive the closed task.",
                "",
                "**Files**: `tasks/BACKLOG.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] archive it",
                "",
                "---",
                "",
                "### TASK-295: Keep me live",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Still open.",
                "",
                "**Files**: `tasks/CURRENT_SPRINT.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] stay open",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Number**: 4",
                "",
                "## Active Tasks",
                "- `TASK-294` Archive closure",
                "- `TASK-295` Keep me live",
                "",
                "## Human Blocker Metadata",
                "- TASK-294 | owner=ops | last_touched=2026-03-10 | next_action=2026-03-11 | escalate_after_days=7",
                "- TASK-999 | owner=ops | last_touched=2026-03-10 | next_action=2026-03-11 | escalate_after_days=7",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
                "## Completed This Sprint",
                "- Sprint opened on 2026-03-10 with carry-over work only; no Sprint 4 tasks are complete yet.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 3\n- TASK-292: Already done ✅\n",
        encoding="utf-8",
    )
