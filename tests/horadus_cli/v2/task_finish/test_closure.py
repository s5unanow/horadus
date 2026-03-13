from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed
from tests.horadus_cli.v2.task_finish.helpers import (
    _REAL_BRANCH_HEAD_ALIGNMENT_BLOCKER,
    _REAL_PRE_MERGE_TASK_CLOSURE_BLOCKER,
)

pytestmark = pytest.mark.unit


def test_pre_merge_task_closure_blocker_reports_open_ledger_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        _REAL_PRE_MERGE_TASK_CLOSURE_BLOCKER,
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda _task_id: task_repo_module.TaskClosureState(
            task_id="TASK-295",
            present_in_backlog=True,
            active_sprint_lines=["- `TASK-295` Enforce Pre-Merge Task Closure State"],
            present_in_completed=False,
            present_in_closed_archive=False,
            closed_archive_path=None,
        ),
    )

    blocker = task_commands_module._pre_merge_task_closure_blocker("TASK-295")

    assert blocker is not None
    message, data, lines = blocker
    assert message == "primary task closure state is not present on the PR head."
    assert data["task_closure"]["present_in_backlog"] is True
    assert "- tasks/BACKLOG.md still contains the task as open." in lines


def test_pre_merge_task_closure_blocker_returns_none_when_task_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        _REAL_PRE_MERGE_TASK_CLOSURE_BLOCKER,
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda _task_id: task_repo_module.TaskClosureState(
            task_id="TASK-295",
            present_in_backlog=False,
            active_sprint_lines=[],
            present_in_completed=True,
            present_in_closed_archive=True,
            closed_archive_path="archive/closed_tasks/2026-Q1.md",
        ),
    )

    assert task_commands_module._pre_merge_task_closure_blocker("TASK-295") is None


def test_task_closure_blocker_lines_omit_archive_warning_when_archive_exists() -> None:
    lines = task_commands_module._task_closure_blocker_lines(
        task_repo_module.TaskClosureState(
            task_id="TASK-295",
            present_in_backlog=False,
            active_sprint_lines=[],
            present_in_completed=False,
            present_in_closed_archive=True,
            closed_archive_path="archive/closed_tasks/2026-Q1.md",
        )
    )

    assert "- tasks/COMPLETED.md is missing the compact completion entry." in lines
    assert all("archive/closed_tasks" not in line for line in lines)


def test_task_closure_state_for_ref_reads_task_branch_instead_of_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "show", "codex/task-295:tasks/BACKLOG.md"]:
            return _completed(args, stdout="# Backlog\n\n### TASK-296: Keep me live\n")
        if args[:3] == ["git", "show", "codex/task-295:tasks/CURRENT_SPRINT.md"]:
            return _completed(
                args,
                stdout=(
                    "# Current Sprint\n\n**Sprint Number**: 4\n\n## Active Tasks\n"
                    "- `TASK-296` Keep me live\n"
                ),
            )
        if args[:3] == ["git", "show", "codex/task-295:tasks/COMPLETED.md"]:
            return _completed(
                args,
                stdout="# Completed Tasks\n\n## Sprint 4\n- TASK-295: Enforce closure ✅\n",
            )
        if args[:6] == [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "codex/task-295",
            "archive/closed_tasks",
        ]:
            return _completed(args, stdout="archive/closed_tasks/2026-Q1.md\n")
        if args[:3] == ["git", "show", "codex/task-295:archive/closed_tasks/2026-Q1.md"]:
            return _completed(
                args,
                stdout="### TASK-295: Enforce closure\n**Priority**: P1\n**Estimate**: 1d\n",
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda _task_id: task_repo_module.TaskClosureState(
            task_id="TASK-295",
            present_in_backlog=True,
            active_sprint_lines=["- `TASK-295` Still open on main"],
            present_in_completed=False,
            present_in_closed_archive=False,
            closed_archive_path=None,
        ),
    )

    closure_state = task_commands_module._task_closure_state_for_ref(
        task_id="TASK-295",
        git_ref="codex/task-295",
        config=config,
    )

    assert closure_state.ready_for_merge is True
    assert closure_state.closed_archive_path == "archive/closed_tasks/2026-Q1.md"


def test_git_file_text_at_ref_reports_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "show"], returncode=128),
    )

    assert task_commands_module._git_file_text_at_ref(
        git_ref="codex/task-295",
        relative_path="tasks/BACKLOG.md",
        config=config,
    ) == (False, "")


def test_task_closure_state_for_ref_handles_sparse_branch_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "show", "codex/task-295:tasks/BACKLOG.md"]:
            return _completed(args, returncode=128)
        if args[:3] == ["git", "show", "codex/task-295:tasks/CURRENT_SPRINT.md"]:
            return _completed(args, stdout="# Current Sprint\n\n## Completed This Sprint\n- none\n")
        if args[:3] == ["git", "show", "codex/task-295:tasks/COMPLETED.md"]:
            return _completed(args, returncode=128)
        if args[:6] == [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "codex/task-295",
            "archive/closed_tasks",
        ]:
            return _completed(
                args,
                stdout="archive/closed_tasks/2026-Q1.md\narchive/closed_tasks/2026-Q2.md\n",
            )
        if args[:3] == ["git", "show", "codex/task-295:archive/closed_tasks/2026-Q1.md"]:
            return _completed(args, stdout="### TASK-296: Different task\n")
        if args[:3] == ["git", "show", "codex/task-295:archive/closed_tasks/2026-Q2.md"]:
            return _completed(args, returncode=128)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    closure_state = task_commands_module._task_closure_state_for_ref(
        task_id="TASK-295",
        git_ref="codex/task-295",
        config=config,
    )

    assert closure_state.present_in_backlog is False
    assert closure_state.active_sprint_lines == []
    assert closure_state.present_in_completed is False
    assert closure_state.present_in_closed_archive is False


def test_task_closure_state_for_ref_handles_missing_sprint_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "show", "codex/task-295:tasks/BACKLOG.md"]:
            return _completed(args, stdout="# Backlog\n")
        if args[:3] == ["git", "show", "codex/task-295:tasks/CURRENT_SPRINT.md"]:
            return _completed(args, returncode=128)
        if args[:3] == ["git", "show", "codex/task-295:tasks/COMPLETED.md"]:
            return _completed(args, stdout="# Completed Tasks\n")
        if args[:6] == [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "codex/task-295",
            "archive/closed_tasks",
        ]:
            return _completed(args, stdout="")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    closure_state = task_commands_module._task_closure_state_for_ref(
        task_id="TASK-295",
        git_ref="codex/task-295",
        config=config,
    )

    assert closure_state.active_sprint_lines == []


def test_branch_head_alignment_blocker_ignores_matching_shas_and_reports_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_branch_head_alignment_blocker",
        _REAL_BRANCH_HEAD_ALIGNMENT_BLOCKER,
    )
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="same-sha\n"),
            _completed(["git", "ls-remote"], stdout="same-sha\trefs/heads/codex/task-295\n"),
            _completed(["gh", "pr", "view"], stdout="same-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    assert (
        task_commands_module._branch_head_alignment_blocker(
            branch_name="codex/task-295-enforce-pre-merge-task-closure",
            pr_url="https://example.invalid/pr/295",
            config=config,
        )
        is None
    )

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="local-sha\n"),
            _completed(["git", "ls-remote"], stdout="remote-sha\trefs/heads/codex/task-295\n"),
            _completed(["gh", "pr", "view"], stdout="pr-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    blocker = task_commands_module._branch_head_alignment_blocker(
        branch_name="codex/task-295-enforce-pre-merge-task-closure",
        pr_url="https://example.invalid/pr/295",
        config=config,
    )

    assert blocker is not None
    message, data, lines = blocker
    assert message == "task branch head, pushed branch head, and PR head are not aligned."
    assert data["local_branch_head"] == "local-sha"
    assert lines[-1] == "- PR head: pr-sha"

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="local-sha\n"),
            _completed(["git", "ls-remote"], returncode=2),
            _completed(["gh", "pr", "view"], stdout="pr-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    blocker = task_commands_module._branch_head_alignment_blocker(
        branch_name="codex/task-295-enforce-pre-merge-task-closure",
        pr_url="https://example.invalid/pr/295",
        config=config,
    )

    assert blocker is not None
    assert blocker[2][1] == "- remote branch head: <missing>"
