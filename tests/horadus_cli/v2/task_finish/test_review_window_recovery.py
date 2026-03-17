from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed
from tests.horadus_cli.v2.task_finish.helpers import (
    _disable_outdated_thread_auto_resolution,
    _review_gate_process,
)

pytestmark = pytest.mark.unit

TASK_ID = "TASK-348"
BRANCH_NAME = "codex/task-348-finish-review-window-recovery"
PR_URL = "https://example.invalid/pr/348"
HEAD_SHA = "head-sha-348"


def _finish_config(*, review_poll_seconds: int = 0) -> task_commands_module.FinishConfig:
    return task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=600,
        review_poll_seconds=review_poll_seconds,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )


def _install_finish_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    review_poll_seconds: int = 0,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda **_kwargs: _finish_config(review_poll_seconds=review_poll_seconds),
    )
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name=BRANCH_NAME,
            branch_task_id=TASK_ID,
            task_id=TASK_ID,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout=f"PR scope guard passed: {TASK_ID} (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)
    monkeypatch.setattr(
        task_commands_module,
        "_find_open_branch_pull_request",
        lambda **_kwargs: task_commands_module.BranchPullRequest(
            number=348,
            url=PR_URL,
            head_ref_name=BRANCH_NAME,
        ),
    )


def _pr_open_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if args[:2] == ["git", "ls-remote"]:
        return _completed(args)
    if (
        args[:3] == ["gh", "pr", "view"]
        and len(args) >= 6
        and args[3] == BRANCH_NAME
        and "--json" in args
        and "url" in args
    ):
        return _completed(args, stdout=f"{PR_URL}\n")
    if args[:4] == ["gh", "pr", "view", PR_URL]:
        if "--json" in args and "title,body" in args:
            return _completed(
                args,
                stdout='{"title":"TASK-348: review window recovery","body":"Primary-Task: TASK-348\\n"}\n',
            )
        if "--json" in args and "state" in args:
            return _completed(args, stdout="OPEN\n")
        if "--json" in args and "isDraft" in args:
            return _completed(args, stdout="false\n")
    raise AssertionError(args)


def _pr_merge_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if args[:2] == ["git", "ls-remote"]:
        return _completed(args)
    if (
        args[:3] == ["gh", "pr", "view"]
        and len(args) >= 6
        and args[3] == BRANCH_NAME
        and "--json" in args
        and "url" in args
    ):
        return _completed(args, stdout=f"{PR_URL}\n")
    if args[:4] == ["gh", "pr", "view", PR_URL]:
        if "--json" in args and "title,body" in args:
            return _completed(
                args,
                stdout='{"title":"TASK-348: review window recovery","body":"Primary-Task: TASK-348\\n"}\n',
            )
        if "--json" in args and "state" in args:
            return _completed(args, stdout="OPEN\n")
        if "--json" in args and "isDraft" in args:
            return _completed(args, stdout="false\n")
        if "--json" in args and "mergeCommit" in args:
            return _completed(args, stdout="merge-commit-348\n")
    if args[:4] == ["gh", "pr", "merge", PR_URL]:
        return _completed(args)
    if args[:3] == ["git", "switch", "main"]:
        return _completed(args)
    if args[:3] == ["git", "pull", "--ff-only"]:
        return _completed(args, stdout="Already up to date.\n")
    if args[:3] == ["git", "cat-file", "-e"]:
        return _completed(args)
    if args[:4] == ["git", "show-ref", "--verify", f"refs/heads/{BRANCH_NAME}"]:
        return _completed(args, returncode=1)
    raise AssertionError(args)


def test_finish_blocks_before_review_window_for_current_head_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    _install_finish_context(monkeypatch)
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- tools/horadus/python/horadus_workflow/pr_review_gate.py:412 https://example.invalid/comment/348 (chatgpt-codex-connector[bot])",
            "  Please resolve this before merge.",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("review gate should not start while unresolved threads exist")
        ),
    )
    monkeypatch.setattr(task_commands_module, "_run_command", _pr_open_run_command)

    exit_code, _data, lines = task_commands_module.finish_task_data(TASK_ID, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert any("Please resolve this before merge." in line for line in lines)
    assert not any(line.startswith("Waiting for review gate ") for line in lines)


def test_finish_marks_stale_current_threads_for_manual_inspection_before_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    _install_finish_context(monkeypatch)
    monkeypatch.setattr(
        task_commands_module,
        "_needs_pre_review_fresh_review_request",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_fresh_review_request_blocker",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "fresh review should not be requested before stale-current threads are handled"
            )
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- tools/horadus/python/horadus_workflow/pr_review_gate.py:444 https://example.invalid/comment/stale-current (chatgpt-codex-connector[bot])",
            "  This is fixed but GitHub still marks the thread current.",
        ],
    )
    monkeypatch.setattr(task_commands_module, "_run_command", _pr_open_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data(TASK_ID, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["manual_thread_inspection_required"] is True
    assert (
        lines[0]
        == "Task finish blocked: PR still has unresolved review threads marked current on GitHub."
    )
    assert any("manual resolution" in line for line in lines)
    assert not any(line.startswith("Waiting for review gate ") for line in lines)


def test_finish_emits_periodic_wait_status_before_terminal_review_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    _install_finish_context(monkeypatch, review_poll_seconds=0)
    poll_results = iter(
        [
            _review_gate_process(
                status="waiting",
                reason="waiting",
                reviewed_head_oid=HEAD_SHA,
                summary=(
                    "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], "
                    "head=head-sha-348, remaining=540s, "
                    "deadline=2026-03-17T12:30:00+00:00)..."
                ),
                wait_window_started_at="2026-03-17T12:21:00+00:00",
                deadline_at="2026-03-17T12:30:00+00:00",
                remaining_seconds=540,
            ),
            _review_gate_process(
                reason="silent_timeout_allow",
                reviewed_head_oid=HEAD_SHA,
                timed_out=True,
                summary=(
                    "review gate timeout: no actionable current-head review feedback from "
                    "chatgpt-codex-connector[bot] for head-sha-348 within 600s. "
                    "Continuing due to timeout policy=allow."
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: next(poll_results),
    )
    monkeypatch.setattr(
        task_commands_module, "_unresolved_review_thread_lines", lambda **_kwargs: []
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-348", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )
    monkeypatch.setattr(task_commands_module, "_run_command", _pr_merge_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data(TASK_ID, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-348"
    assert any(
        line.startswith(
            "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], head=head-sha-348"
        )
        for line in lines
    )
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-348 and synced main."


def test_finish_can_continue_after_same_head_thread_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    _install_finish_context(monkeypatch, review_poll_seconds=0)
    unresolved_state = {"open": True}
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid=HEAD_SHA,
            timed_out=True,
            summary=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-348 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: (
            [
                "- tools/horadus/python/horadus_workflow/pr_review_gate.py:488 https://example.invalid/comment/348-thread (chatgpt-codex-connector[bot])",
                "  Resolve this thread before finish can continue.",
            ]
            if unresolved_state["open"]
            else []
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-348", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )
    monkeypatch.setattr(task_commands_module, "_run_command", _pr_merge_run_command)

    first_exit_code, _first_data, first_lines = task_commands_module.finish_task_data(
        TASK_ID, dry_run=False
    )

    assert first_exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert first_lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."

    unresolved_state["open"] = False

    second_exit_code, second_data, second_lines = task_commands_module.finish_task_data(
        TASK_ID, dry_run=False
    )

    assert second_exit_code == task_commands_module.ExitCode.OK
    assert second_data["merge_commit"] == "merge-commit-348"
    assert not any("wait for a fresh current-head review" in line for line in second_lines)
    assert second_lines[-1] == "Task finish passed: merged merge-commit-348 and synced main."
