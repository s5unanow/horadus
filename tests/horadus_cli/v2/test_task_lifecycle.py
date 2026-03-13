from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed, _task_snapshot
from tests.horadus_cli.v2.task_finish.helpers import _closed_task_closure_state

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _default_task_closure_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda task_id: _closed_task_closure_state(task_id),
    )


@pytest.mark.parametrize(
    ("snapshot", "expected_state"),
    [
        (_task_snapshot(), "local-only"),
        (_task_snapshot(remote_branch_exists=True), "pushed"),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="OPEN",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid=None,
                    check_state="pending",
                )
            ),
            "pr-open",
        ),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="OPEN",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid=None,
                    check_state="pass",
                )
            ),
            "ci-green",
        ),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="MERGED",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid="merge-sha",
                    check_state="pass",
                ),
                local_main_synced=False,
                merge_commit_on_main=False,
            ),
            "merged",
        ),
        (
            _task_snapshot(
                current_branch="main",
                branch_name="codex/task-259-done-state-verifier",
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="MERGED",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid="merge-sha",
                    check_state="pass",
                ),
                local_main_synced=True,
                merge_commit_on_main=True,
            ),
            "local-main-synced",
        ),
    ],
)
def test_task_lifecycle_state_distinguishes_required_states(
    snapshot: task_commands_module.TaskLifecycleSnapshot,
    expected_state: str,
) -> None:
    assert task_commands_module.task_lifecycle_state(snapshot) == expected_state


def test_task_lifecycle_data_strict_mode_fails_before_local_main_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            pr=task_commands_module.TaskPullRequest(
                number=259,
                url="https://example.invalid/pr/259",
                state="MERGED",
                is_draft=False,
                head_ref_name="codex/task-259-done-state-verifier",
                head_ref_oid="head-sha",
                merge_commit_oid="merge-sha",
                check_state="pass",
            ),
            local_main_synced=False,
            merge_commit_on_main=False,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=True,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["lifecycle_state"] == "merged"
    assert data["strict_complete"] is False
    assert lines[-1] == (
        "Strict verification failed: repo-policy completion requires state `local-main-synced` with the task removed from live ledgers and recorded in tasks/COMPLETED.md plus archive/closed_tasks/."
    )


def test_task_lifecycle_data_strict_mode_passes_when_repo_policy_is_fully_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            pr=task_commands_module.TaskPullRequest(
                number=259,
                url="https://example.invalid/pr/259",
                state="MERGED",
                is_draft=False,
                head_ref_name="codex/task-259-done-state-verifier",
                head_ref_oid="head-sha",
                merge_commit_oid="merge-sha",
                check_state="pass",
            ),
            local_main_synced=True,
            merge_commit_on_main=True,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=True,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["lifecycle_state"] == "local-main-synced"
    assert data["strict_complete"] is True
    assert lines[-1] == "- strict complete: yes"


def test_task_lifecycle_data_strict_mode_requires_closed_ledgers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            pr=task_commands_module.TaskPullRequest(
                number=295,
                url="https://example.invalid/pr/295",
                state="MERGED",
                is_draft=False,
                head_ref_name="codex/task-295-enforce-pre-merge-task-closure",
                head_ref_oid="head-sha",
                merge_commit_oid="merge-sha",
                check_state="pass",
            ),
            local_main_synced=True,
            merge_commit_on_main=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_closure_state",
        lambda _task_id: task_repo_module.TaskClosureState(
            task_id="TASK-295",
            present_in_backlog=False,
            active_sprint_lines=[],
            present_in_completed=True,
            present_in_closed_archive=False,
            closed_archive_path=None,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-295",
        strict=True,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["lifecycle_state"] == "local-main-synced"
    assert data["strict_complete"] is False
    assert data["task_closure"]["present_in_closed_archive"] is False
    assert "- archive/closed_tasks/*.md is missing the full archived task body." in lines


def test_task_lifecycle_data_reports_missing_required_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "_ensure_command_available", lambda _name: None)

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert lines == ["Task lifecycle failed: missing required command 'gh'."]


def test_task_lifecycle_data_dry_run_reports_live_state_without_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(pr=None),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["lifecycle_state"] == "local-only"
    assert "- PR: none" in lines
    assert lines[-1] == "Dry run: lifecycle inspection is read-only; returned live state."


def test_task_lifecycle_state_allows_detached_head_when_main_is_synced() -> None:
    snapshot = _task_snapshot(
        current_branch="HEAD",
        pr=task_commands_module.TaskPullRequest(
            number=268,
            url="https://example.invalid/pr/268",
            state="MERGED",
            is_draft=False,
            head_ref_name="codex/task-268-detached-head-lifecycle",
            head_ref_oid="head-sha",
            merge_commit_oid="merge-sha",
            check_state="pass",
        ),
        local_main_synced=True,
        merge_commit_on_main=True,
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "local-main-synced"


def test_task_lifecycle_state_keeps_open_prs_without_green_checks_in_pr_open() -> None:
    snapshot = _task_snapshot(
        pr=task_commands_module.TaskPullRequest(
            number=259,
            url="https://example.invalid/pr/259",
            state="OPEN",
            is_draft=True,
            head_ref_name="codex/task-259-done-state-verifier",
            head_ref_oid="head-sha",
            merge_commit_oid=None,
            check_state="pass",
        )
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "pr-open"


def test_task_lifecycle_state_treats_closed_prs_as_pushed_when_remote_branch_exists() -> None:
    snapshot = _task_snapshot(
        remote_branch_exists=True,
        pr=task_commands_module.TaskPullRequest(
            number=259,
            url="https://example.invalid/pr/259",
            state="CLOSED",
            is_draft=False,
            head_ref_name="codex/task-259-done-state-verifier",
            head_ref_oid="head-sha",
            merge_commit_oid=None,
            check_state="fail",
        ),
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "pushed"


def test_resolve_task_lifecycle_allows_explicit_task_id_from_detached_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="HEAD\n"),
            _completed(
                ["git", "branch", "--list"], stdout="  codex/task-268-detached-head-lifecycle\n"
            ),
            _completed(["git", "ls-remote", "--heads"], stdout=""),
            _completed(["git", "status", "--porcelain"], stdout=""),
            _completed(["git", "fetch", "origin", "main", "--quiet"]),
            _completed(["git", "rev-parse", "main"], stdout="main-sha\n"),
            _completed(["git", "rev-parse", "origin/main"], stdout="main-sha\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: None,
    )

    snapshot = task_commands_module.resolve_task_lifecycle("TASK-268", config=config)

    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.task_id == "TASK-268"
    assert snapshot.current_branch == "HEAD"
    assert snapshot.branch_name == "codex/task-268-detached-head-lifecycle"
    assert snapshot.local_main_synced is True


def test_resolve_task_lifecycle_reports_environment_and_lookup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], returncode=1),
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to determine current branch."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )
    result = task_commands_module.resolve_task_lifecycle("bad-task", config=config)
    assert isinstance(result, tuple)
    assert "Invalid task id" in result[2][0]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: (
            task_commands_module.ExitCode.ENVIRONMENT_ERROR,
            {"task_id": "TASK-257"},
            ["Task lifecycle failed.", "Unable to query GitHub pull requests."],
        ),
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to query GitHub pull requests."]


def test_resolve_task_lifecycle_covers_branch_lookup_and_git_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect local task branches."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect remote task branches."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["No local, remote, or PR lifecycle state found for TASK-257."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="feature/misc\n"),
    )
    result = task_commands_module.resolve_task_lifecycle(None, config=config)
    assert isinstance(result, tuple)
    assert result[2] == [
        "Task lifecycle failed.",
        "A task id is required when the current branch is not a canonical task branch.",
    ]


def test_resolve_task_lifecycle_covers_status_fetch_and_merge_commit_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    pr = task_commands_module.TaskPullRequest(
        number=257,
        url="https://example.invalid/pr/257",
        state="MERGED",
        is_draft=False,
        head_ref_name="codex/task-257-coverage-hard-fail",
        head_ref_oid="head-sha",
        merge_commit_oid="merge-sha",
        check_state="pass",
    )

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: pr)
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect working tree state."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == [
        "Task lifecycle failed.",
        "Unable to refresh origin/main before verification.",
    ]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "cat-file"], stdout=""),
            _completed(["git", "merge-base"], returncode=0),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    snapshot = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"
    assert snapshot.merge_commit_available_locally is True
    assert snapshot.merge_commit_on_main is True

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(
                ["git", "branch"],
                stdout="* codex/task-257-coverage-hard-fail\n  codex/task-257-other\n",
            ),
            _completed(["git", "ls-remote"], stdout=""),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], returncode=1),
            _completed(["git", "rev-parse"], stdout="remote-main-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)
    snapshot = task_commands_module.resolve_task_lifecycle(None, config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"
    assert snapshot.local_main_synced is None

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"],
                stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n",
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "rev-parse"], stdout="remote-main-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    snapshot = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"


def test_resolve_task_lifecycle_requires_explicit_task_id_from_detached_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="HEAD\n"),
    )

    result = task_commands_module.resolve_task_lifecycle(None, config=config)

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {"current_branch": "HEAD"}
    assert lines == [
        "Task lifecycle failed.",
        "A task id is required when running from detached HEAD.",
    ]


def test_task_lifecycle_data_does_not_enforce_finish_timeout_override_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: task_commands_module.TaskLifecycleSnapshot(
            task_id="TASK-283",
            current_branch="codex/task-283-finish-review-thumbs-up",
            branch_name="codex/task-283-finish-review-thumbs-up",
            local_branch_names=["codex/task-283-finish-review-thumbs-up"],
            remote_branch_names=["origin/codex/task-283-finish-review-thumbs-up"],
            remote_branch_exists=True,
            working_tree_clean=True,
            pr=task_commands_module.TaskPullRequest(
                number=217,
                url="https://example.invalid/pr/283",
                state="OPEN",
                is_draft=False,
                head_ref_name="codex/task-283-finish-review-thumbs-up",
                head_ref_oid="head-sha-283",
                merge_commit_oid=None,
                check_state="pass",
            ),
            local_main_sha="main-sha",
            remote_main_sha="main-sha",
            local_main_synced=True,
            merge_commit_available_locally=None,
            merge_commit_on_main=None,
            lifecycle_state="ci-green",
            strict_complete=False,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-283",
        strict=False,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["task_id"] == "TASK-283"
    assert lines[0] == "Task lifecycle: TASK-283"


def test_task_lifecycle_data_handles_finish_config_and_resolution_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad config")),
    )
    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data == {}
    assert lines == ["bad config"]

    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda **_kwargs: task_commands_module.FinishConfig(
            gh_bin="gh",
            git_bin="git",
            python_bin="python3",
            checks_timeout_seconds=1,
            checks_poll_seconds=0,
            review_timeout_seconds=1,
            review_poll_seconds=0,
            review_bot_login="bot",
            review_timeout_policy="allow",
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    expected = (
        task_commands_module.ExitCode.NOT_FOUND,
        {"task_id": "TASK-259"},
        ["No local, remote, or PR lifecycle state found for TASK-259."],
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: expected,
    )

    assert (
        task_commands_module.task_lifecycle_data("TASK-259", strict=False, dry_run=False)
        == expected
    )

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(branch_name=None, pr=None),
    )
    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] is None
    assert "- task branch:" not in "\n".join(lines)
