from __future__ import annotations

import argparse
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def test_assert_safe_worktree_data_passes_on_clean_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.assert_safe_worktree_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data == {
        "current_branch": "main",
        "tracked_dirty_paths": [],
        "watchdog_applicable": True,
        "working_tree_clean": True,
    }
    assert lines == ["Dirty-main watchdog passed: no tracked diffs on 'main'."]


def test_assert_safe_worktree_data_reports_branch_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], returncode=1, stderr="boom"),
    )

    exit_code, data, lines = task_commands_module.assert_safe_worktree_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data == {"branch_error": "boom"}
    assert lines == ["Dirty-main watchdog failed.", "boom"]


def test_assert_safe_worktree_data_fails_for_tracked_diffs_on_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=" M tasks/BACKLOG.md\nM  AGENTS.md\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.assert_safe_worktree_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {
        "current_branch": "main",
        "tracked_dirty_paths": ["tasks/BACKLOG.md", "AGENTS.md"],
        "watchdog_applicable": True,
        "working_tree_clean": False,
    }
    assert lines[0] == "Dirty-main watchdog failed."
    assert "Tracked diffs on 'main' are not allowed" in lines[1]
    assert "tasks/BACKLOG.md, AGENTS.md" in lines[2]
    assert "safe-start TASK-XXX --name short-name" in lines[3]


def test_assert_safe_worktree_data_reports_status_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], returncode=1, stderr="status boom"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.assert_safe_worktree_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data == {"current_branch": "main", "status_error": "status boom"}
    assert lines == ["Dirty-main watchdog failed.", "status boom"]


def test_assert_safe_worktree_data_skips_task_branch_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-390-dirty-main-watchdog\n"),
            _completed(["git", "status"], stdout=" M AGENTS.md\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.assert_safe_worktree_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data == {
        "current_branch": "codex/task-390-dirty-main-watchdog",
        "tracked_dirty_paths": ["AGENTS.md"],
        "watchdog_applicable": False,
        "working_tree_clean": False,
    }
    assert lines == [
        "Dirty-main watchdog skipped: current branch is codex/task-390-dirty-main-watchdog."
    ]


def test_handle_assert_safe_worktree_returns_wrapped_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_assert_safe_worktree_result",
        lambda: task_commands_module.CommandResult(lines=["watchdog ok"]),
    )

    result = task_commands_module.handle_assert_safe_worktree(argparse.Namespace())

    assert result.lines == ["watchdog ok"]


def test_assert_safe_worktree_result_wraps_watchdog_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "assert_safe_worktree_data",
        lambda: (task_commands_module.ExitCode.OK, {"branch": "main"}, ["watchdog ok"]),
    )

    result = task_commands_module._assert_safe_worktree_result()

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"branch": "main"}
    assert result.lines == ["watchdog ok"]


def test_handle_preflight_stays_bound_to_preflight_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_preflight_result",
        lambda: task_commands_module.CommandResult(lines=["preflight ok"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_assert_safe_worktree_result",
        lambda: task_commands_module.CommandResult(lines=["watchdog failed"]),
    )

    result = task_commands_module.handle_preflight(argparse.Namespace())

    assert result.lines == ["preflight ok"]
