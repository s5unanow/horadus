from __future__ import annotations

import json
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed, _task_snapshot

pytestmark = pytest.mark.unit


def test_resolve_finish_context_rejects_task_mismatch(
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
            _completed(["git", "rev-parse"], stdout="codex/task-258-canonical-finish\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._resolve_finish_context("TASK-259", config)

    assert not isinstance(result, task_commands_module.FinishContext)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_task_id"] == "TASK-258"
    assert data["task_id"] == "TASK-259"
    assert "maps to TASK-258, not TASK-259" in lines[0]


def test_resolve_finish_context_blocks_for_branch_query_error_and_detached_head(
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
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], returncode=1, stderr="boom"),
    )

    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: boom"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="HEAD\n"),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: detached HEAD is not allowed."


def test_resolve_finish_context_blocks_for_main_recovery_edge_cases(
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
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )

    result = task_commands_module._resolve_finish_context(None, config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: refusing to run on 'main'."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.NOT_FOUND,
            {"task_id": "TASK-257"},
            ["not found"],
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: unable to recover task context from 'main'."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            branch_name=None,
            working_tree_clean=False,
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: working tree must be clean."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            branch_name=None,
            working_tree_clean=True,
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert "unable to resolve a task branch for TASK-257 from 'main'" in result[2][0]


def test_resolve_finish_context_allows_explicit_task_id_from_main(
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
    snapshot = _task_snapshot(
        current_branch="main",
        branch_name="codex/task-289-finish-branch-context-recovery",
        pr=task_commands_module.TaskPullRequest(
            number=289,
            url="https://example.invalid/pr/289",
            state="OPEN",
            is_draft=False,
            head_ref_name="codex/task-289-finish-branch-context-recovery",
            head_ref_oid="head-sha-289",
            merge_commit_oid=None,
            check_state="pass",
        ),
    )
    snapshot.task_id = "TASK-289"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: snapshot,
    )

    result = task_commands_module._resolve_finish_context("TASK-289", config)

    assert isinstance(result, task_commands_module.FinishContext)
    assert result.branch_name == "codex/task-289-finish-branch-context-recovery"
    assert result.branch_task_id == "TASK-289"
    assert result.task_id == "TASK-289"
    assert result.current_branch == "main"
    assert result.recovered_pr_url == "https://example.invalid/pr/289"
    assert result.recovered_pr_state == "OPEN"


def test_resolve_finish_context_blocks_for_noncanonical_or_dirty_branch(
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
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="feature/misc\n"),
    )

    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert "branch does not match the required task pattern" in result[2][0]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], returncode=1, stderr="status failed"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: status failed"

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], stdout=" M file.py\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: working tree must be clean."


def test_resolve_finish_context_accepts_canonical_branch_without_explicit_task_id(
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
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._resolve_finish_context(None, config)

    assert isinstance(result, task_commands_module.FinishContext)
    assert result.branch_name == "codex/task-257-coverage-hard-fail"
    assert result.branch_task_id == "TASK-257"
    assert result.task_id == "TASK-257"


def test_find_task_pull_request_handles_search_and_view_failures(
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
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], returncode=1),
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to query GitHub pull requests."]

    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(["gh", "pr", "view"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to read GitHub PR #259."]


def test_find_task_pull_request_parses_rollup_and_optional_merge_commit(
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
            _completed(["gh", "pr", "list"], stdout='[{"number":259},{"number":258}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": {},
                        "statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": ""}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.number == 259
    assert result.merge_commit_oid is None
    assert result.check_state == "pending"


def test_find_task_pull_request_handles_empty_results_and_merge_commit_oid(
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
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], stdout="[]"),
    )
    assert task_commands_module._find_task_pull_request(task_id="TASK-259", config=config) is None

    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": {"oid": "merge-sha"},
                        "statusCheckRollup": ["ignored", {"status": "COMPLETED", "conclusion": ""}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.merge_commit_oid == "merge-sha"
    assert result.check_state == "pending"


def test_find_task_pull_request_ignores_non_dict_merge_commit_payload(
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
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": "merge-sha",
                        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.merge_commit_oid is None


def test_find_task_pull_request_remains_task_id_recovery_not_branch_dedupe(
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
            _completed(["gh", "pr", "list"], stdout='[{"number":260},{"number":259}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 260,
                        "url": "https://example.invalid/pr/260",
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "codex/task-260-other-branch",
                        "headRefOid": "head-sha-260",
                        "mergeCommit": {"oid": "merge-sha-260"},
                        "statusCheckRollup": [],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.number == 260
    assert result.head_ref_name == "codex/task-260-other-branch"
