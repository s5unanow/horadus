from __future__ import annotations

import json

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def test_required_checks_state_reports_failed_required_ci(
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    {
                        "bucket": "fail",
                        "name": "Test",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/test",
                    },
                    {"bucket": "pending", "name": "Build", "workflow": "CI", "link": ""},
                ]
            ),
        ),
    )

    state, lines = task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert state == "fail"
    assert lines == ["CI / Test: fail (https://example.invalid/checks/test)"]
    assert checks_ok is False
    assert check_lines == lines
    assert check_reason == "fail"


def test_required_checks_state_handles_unexpected_json_shapes(
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

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            stdout="{not-json",
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("error", ["Unable to parse required-check payload from `gh pr checks`."])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout="still pending",
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pending", ["still pending"])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            stdout='"pass"',
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("error", ["Unable to parse required-check payload from `gh pr checks`."])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout='"pending"',
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pending", ['"pending"'])


def test_required_checks_state_reports_pending_required_ci(
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    "ignore-me",
                    {
                        "bucket": "pending",
                        "name": "Build",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/build",
                    },
                    {"bucket": "pass", "name": "Lint", "workflow": "CI", "link": ""},
                ]
            ),
        ),
    )

    state, lines = task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert state == "pending"
    assert lines == ["CI / Build: pending (https://example.invalid/checks/build)"]


def test_required_checks_state_does_not_treat_unknown_nonzero_status_as_pass(
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    {
                        "bucket": "neutral",
                        "name": "Build",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/build",
                    }
                ]
            ),
        ),
    )

    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == (
        "pending",
        [
            (
                '[{"bucket": "neutral", "name": "Build", "workflow": "CI", "link": '
                '"https://example.invalid/checks/build"}]'
            )
        ],
    )


def test_current_required_checks_blocker_maps_check_states(
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

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("fail", ["CI / Test: fail"]),
    )
    assert task_commands_module._current_required_checks_blocker(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("required PR checks are failing on the current head.", ["CI / Test: fail"])

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("pending", ["CI / Build: pending"]),
    )
    assert task_commands_module._current_required_checks_blocker(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("required PR checks are still pending on the current head.", ["CI / Build: pending"])
    assert (
        task_commands_module._current_required_checks_blocker(
            pr_url="https://example.invalid/pr/257",
            config=config,
            block_pending=False,
        )
        is None
    )

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("pass", []),
    )
    assert (
        task_commands_module._current_required_checks_blocker(
            pr_url="https://example.invalid/pr/257",
            config=config,
        )
        is None
    )

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("error", ["bad payload"]),
    )
    assert task_commands_module._current_required_checks_blocker(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == (
        "required PR checks could not be determined on the current head.",
        ["bad payload"],
    )


def test_wait_for_required_checks_returns_error_reason(
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
    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("error", ["bad payload"]),
    )

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert checks_ok is False
    assert check_lines == ["bad payload"]
    assert check_reason == "error"


def test_current_head_finish_blocker_returns_first_blocker(
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
    context = task_commands_module.FinishContext(
        branch_name="codex/task-307-stateful-review-loop",
        branch_task_id="TASK-307",
        task_id="TASK-307",
    )

    head_blocker = ("heads differ", {"remote_branch_head": "abc"}, ["- local branch head: abc"])
    monkeypatch.setattr(
        task_commands_module, "_branch_head_alignment_blocker", lambda **_kwargs: head_blocker
    )
    assert (
        task_commands_module._current_head_finish_blocker(
            context=context,
            pr_url="https://example.invalid/pr/307",
            config=config,
        )
        == head_blocker
    )

    monkeypatch.setattr(
        task_commands_module, "_branch_head_alignment_blocker", lambda **_kwargs: None
    )
    closure_blocker = (
        "missing closure",
        {"task_closure": {}},
        ["- tasks/BACKLOG.md still contains the task as open."],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        lambda *_args, **_kwargs: closure_blocker,
    )
    assert (
        task_commands_module._current_head_finish_blocker(
            context=context,
            pr_url="https://example.invalid/pr/307",
            config=config,
        )
        == closure_blocker
    )

    monkeypatch.setattr(
        task_commands_module, "_pre_merge_task_closure_blocker", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: ("required checks pending", ["CI / build: pending"]),
    )
    assert task_commands_module._current_head_finish_blocker(
        context=context,
        pr_url="https://example.invalid/pr/307",
        config=config,
    ) == ("required checks pending", {}, ["CI / build: pending"])


def test_head_changed_review_gate_blocker_wraps_current_head_blocker(
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
    context = task_commands_module.FinishContext(
        branch_name="codex/task-309-finish-rerun-refresh",
        branch_task_id="TASK-309",
        task_id="TASK-309",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_head_finish_blocker",
        lambda **_kwargs: (
            "required checks pending",
            {},
            ["CI / build: pending"],
        ),
    )

    exit_code, data, lines = task_commands_module._head_changed_review_gate_blocker(
        context=context,
        pr_url="https://example.invalid/pr/309",
        config=config,
        review_lines=["review gate deferred: PR head changed from head-a to head-b"],
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["task_id"] == "TASK-309"
    assert data["branch_name"] == "codex/task-309-finish-rerun-refresh"
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert lines[0] == "Task finish blocked: required checks pending"
    assert any("PR head changed from head-a to head-b" in line for line in lines)
    assert "CI / build: pending" in lines
