from __future__ import annotations

import json
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _default_lifecycle_pr_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)


def _finish_config() -> task_commands_module.FinishConfig:
    return task_commands_module.FinishConfig(
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


def _finish_context(
    *,
    task_id: str = "TASK-326",
    branch_name: str = "codex/task-326-finish-pr-bootstrap",
    current_branch: str | None = None,
) -> task_commands_module.FinishContext:
    return task_commands_module.FinishContext(
        branch_name=branch_name,
        branch_task_id=task_id,
        task_id=task_id,
        current_branch=current_branch,
    )


def _patch_generated_pr_metadata(
    monkeypatch: pytest.MonkeyPatch,
    *,
    task_id: str,
    title: str | None = None,
    body: str | None = None,
) -> None:
    resolved_title = title or f"{task_id}: canonical finish"
    resolved_body = body or f"Primary-Task: {task_id}\n"
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_title",
        lambda **_kwargs: resolved_title,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_body",
        lambda **_kwargs: resolved_body,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout=f"PR scope guard passed: {task_id} (Primary-Task)"
        ),
    )


def test_ensure_finish_pull_request_pushes_missing_branch_and_creates_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    docker_calls: list[str] = []
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: (
            docker_calls.append("called")
            or task_commands_module.DockerReadiness(
                ready=True,
                attempted_start=False,
                supported_auto_start=True,
                lines=["Docker is ready."],
            )
        ),
    )

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["git", "push", "-u"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/326\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.remote_branch_exists is True
    assert result.pushed_branch is True
    assert result.created_pr is True
    assert docker_calls == ["called"]
    assert result.lines == [
        "Pushing branch `codex/task-326-finish-pr-bootstrap` to `origin`...",
        "Creating canonical PR for `codex/task-326-finish-pr-bootstrap`...",
    ]


def test_resolve_finish_pr_title_falls_back_for_noncanonical_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_repo_module, "task_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(task_repo_module, "closed_task_archive_record", lambda _task_id: None)

    assert (
        task_commands_module._resolve_finish_pr_title(
            task_id="TASK-326",
            branch_name="feature/misc",
        )
        == "TASK-326: short summary"
    )


def test_ensure_finish_pull_request_creates_pr_without_push_when_remote_branch_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/326\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.remote_branch_exists is True
    assert result.pushed_branch is False
    assert result.created_pr is True


def test_ensure_finish_pull_request_dry_run_omits_push_when_remote_branch_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=True,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.lines == [
        "Dry run: would create PR `TASK-326: canonical finish` for `codex/task-326-finish-pr-bootstrap`."
    ]


def test_ensure_finish_pull_request_dry_run_reports_push_and_create_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context(task_id="TASK-261", branch_name="codex/task-261-docker-readiness")
    _patch_generated_pr_metadata(
        monkeypatch,
        task_id=context.task_id,
        title="TASK-261: docker readiness",
    )

    docker_calls: list[str] = []

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        if args[:3] in {["git", "push", "-u"], ["gh", "pr", "create"]}:
            raise AssertionError(args)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: (
            docker_calls.append("called")
            or task_commands_module.DockerReadiness(
                ready=True,
                attempted_start=False,
                supported_auto_start=True,
                lines=["Docker is ready."],
            )
        ),
    )

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=True,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url is None
    assert result.remote_branch_exists is False
    assert result.pushed_branch is False
    assert result.created_pr is False
    assert result.generated_title == "TASK-261: docker readiness"
    assert result.generated_body == "Primary-Task: TASK-261\n"
    assert docker_calls == []
    assert result.lines == [
        "Dry run: would push `codex/task-261-docker-readiness` to `origin`.",
        "Dry run: would create PR `TASK-261: docker readiness` for `codex/task-261-docker-readiness`.",
    ]


def test_ensure_finish_pull_request_attaches_to_existing_open_branch_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["gh", "pr", "create"]:
            raise AssertionError(args)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.pushed_branch is False
    assert result.created_pr is False
    assert result.lines == []


def test_ensure_finish_pull_request_reuses_recovered_same_branch_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context(current_branch="main")
    context.recovered_pr_url = "https://example.invalid/pr/326"
    context.recovered_pr_state = "MERGED"

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        if args[:3] == ["gh", "pr", "create"]:
            raise AssertionError(args)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.remote_branch_exists is False
    assert result.pushed_branch is False
    assert result.created_pr is False


def test_ensure_finish_pull_request_ignores_closed_recovered_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context(current_branch="main")
    context.recovered_pr_url = "https://example.invalid/pr/326"
    context.recovered_pr_state = "CLOSED"
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 327,
                            "url": "https://example.invalid/pr/327",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["git", "push", "-u"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/327\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=["Docker is ready."],
        ),
    )

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/327"
    assert result.pushed_branch is True
    assert result.created_pr is True


def test_ensure_finish_pull_request_reuses_same_branch_lifecycle_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: task_commands_module.TaskPullRequest(
            number=326,
            url="https://example.invalid/pr/326",
            state="MERGED",
            is_draft=False,
            head_ref_name=context.branch_name,
            head_ref_oid="head-sha-326",
            merge_commit_oid="merge-sha-326",
            check_state="pass",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        if args[:3] == ["gh", "pr", "create"]:
            raise AssertionError(args)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.remote_branch_exists is False
    assert result.pushed_branch is False
    assert result.created_pr is False


def test_ensure_finish_pull_request_ignores_closed_same_branch_lifecycle_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: task_commands_module.TaskPullRequest(
            number=326,
            url="https://example.invalid/pr/326",
            state="CLOSED",
            is_draft=False,
            head_ref_name=context.branch_name,
            head_ref_oid="head-sha-326",
            merge_commit_oid=None,
            check_state="pass",
        ),
    )

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 327,
                            "url": "https://example.invalid/pr/327",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["git", "push", "-u"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/327\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=["Docker is ready."],
        ),
    )

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/327"
    assert result.pushed_branch is True
    assert result.created_pr is True


def test_ensure_finish_pull_request_recovers_from_create_race_by_requerying_branch_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, returncode=1, stderr="pull request already exists")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.created_pr is False
    assert result.lines[-1] == (
        "PR already exists after create attempt; continuing with the discovered branch PR."
    )


def test_ensure_finish_pull_request_uses_created_pr_url_when_requery_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            return _completed(args, stdout="[]")
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/326\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, task_commands_module.FinishPullRequestBootstrap)
    assert result.pr_url == "https://example.invalid/pr/326"
    assert result.created_pr is True
    assert result.lines[-1] == (
        "Continuing with the newly created PR URL while branch lookup catches up."
    )


def test_find_open_branch_pull_request_blocks_on_query_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="gh failed"),
    )

    result = task_commands_module._find_open_branch_pull_request(
        branch_name="codex/task-326-finish-pr-bootstrap",
        config=config,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["branch_name"] == "codex/task-326-finish-pr-bootstrap"
    assert lines[0] == "Task finish blocked: gh failed"


def test_find_open_branch_pull_request_blocks_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, stdout="{not-json}", stderr="bad payload"),
    )

    result = task_commands_module._find_open_branch_pull_request(
        branch_name="codex/task-326-finish-pr-bootstrap",
        config=config,
    )

    assert isinstance(result, tuple)
    exit_code, _data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines[0] == "Task finish blocked: Unable to parse GitHub pull request search results."
    assert lines[-1] == "bad payload"


def test_find_open_branch_pull_request_blocks_on_non_list_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, stdout='{"number":326}'),
    )

    result = task_commands_module._find_open_branch_pull_request(
        branch_name="codex/task-326-finish-pr-bootstrap",
        config=config,
    )

    assert isinstance(result, tuple)
    exit_code, _data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines[0] == "Task finish blocked: Unable to parse GitHub pull request search results."


def test_ensure_finish_pull_request_blocks_when_multiple_open_prs_match_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        },
                        {
                            "number": 327,
                            "url": "https://example.invalid/pr/327",
                            "headRefName": context.branch_name,
                        },
                    ]
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["matching_pull_requests"] == [
        {"number": 326, "url": "https://example.invalid/pr/326"},
        {"number": 327, "url": "https://example.invalid/pr/327"},
    ]
    assert lines[0] == (
        "Task finish blocked: multiple open pull requests match branch "
        "`codex/task-326-finish-pr-bootstrap`."
    )


def test_ensure_finish_pull_request_returns_scope_guard_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_title",
        lambda **_kwargs: "TASK-326: canonical finish",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_body",
        lambda **_kwargs: "Primary-Task: TASK-326\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(["scope"], returncode=1, stderr="scope failed"),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["generated_pr_title"] == "TASK-326: canonical finish"
    assert lines[0] == "Task finish blocked: generated PR metadata failed scope validation."
    assert lines[-1] == "scope failed"


def test_ensure_finish_pull_request_blocks_when_push_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=["Docker is ready."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(args, stdout="[]")
        if args[:3] == ["git", "push", "-u"]:
            return _completed(args, returncode=1, stderr="push failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["branch_name"] == context.branch_name
    assert lines[0] == (
        "Task finish blocked: unable to push branch `codex/task-326-finish-pr-bootstrap` to origin."
    )
    assert lines[-1] == "push failed"


def test_ensure_finish_pull_request_blocks_when_create_fails_without_recoverable_branch_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            return _completed(args, stdout="[]")
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, returncode=1, stderr="create failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["generated_pr_title"] == "TASK-326: canonical finish"
    assert lines[0] == (
        "Task finish blocked: unable to create a PR for branch "
        "`codex/task-326-finish-pr-bootstrap`."
    )
    assert lines[-1] == "create failed"


def test_ensure_finish_pull_request_returns_branch_query_blocker_after_create_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context()
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(args, returncode=1, stderr="requery failed")
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/326\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._ensure_finish_pull_request(
        context=context,
        config=config,
        dry_run=False,
    )

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["branch_name"] == context.branch_name
    assert lines[0] == "Task finish blocked: requery failed"


def test_finish_task_data_allows_main_recovery_to_bootstrap_branch_and_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    context = _finish_context(current_branch="main")
    _patch_generated_pr_metadata(monkeypatch, task_id=context.task_id)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda: config,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: context,
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=["Docker is ready."],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-326", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    pr_list_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal pr_list_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:3] == ["gh", "pr", "list"]:
            pr_list_calls += 1
            if pr_list_calls == 1:
                return _completed(args, stdout="[]")
            return _completed(
                args,
                stdout=json.dumps(
                    [
                        {
                            "number": 326,
                            "url": "https://example.invalid/pr/326",
                            "headRefName": context.branch_name,
                        }
                    ]
                ),
            )
        if args[:3] == ["git", "push", "-u"]:
            return _completed(args)
        if args[:3] == ["gh", "pr", "create"]:
            return _completed(args, stdout="https://example.invalid/pr/326\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/326"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-326: canonical finish","body":"Primary-Task: TASK-326\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-sha-326\n")
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-326-finish-pr-bootstrap",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-326", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-sha-326"
    assert lines[0] == (
        "Resuming TASK-326 from main using task branch codex/task-326-finish-pr-bootstrap."
    )
    assert "Pushing branch `codex/task-326-finish-pr-bootstrap` to `origin`..." in lines
    assert "Creating canonical PR for `codex/task-326-finish-pr-bootstrap`..." in lines


def test_resolve_finish_pr_title_prefers_live_then_archive_then_branch_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_record = task_repo_module.TaskRecord(
        task_id="TASK-326",
        title="Live Title",
        priority=None,
        estimate=None,
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )
    archived_record = task_repo_module.TaskRecord(
        task_id="TASK-326",
        title="Archived Title",
        priority=None,
        estimate=None,
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="",
        status="completed",
        sprint_lines=[],
        spec_paths=[],
        archived=True,
    )

    monkeypatch.setattr(
        task_repo_module,
        "task_record",
        lambda _task_id, include_archive=False: (
            live_record if not include_archive else archived_record
        ),
    )
    monkeypatch.setattr(task_repo_module, "closed_task_archive_record", lambda _task_id: None)
    assert (
        task_commands_module._resolve_finish_pr_title(
            task_id="TASK-326",
            branch_name="codex/task-326-finish-pr-bootstrap",
        )
        == "TASK-326: Live Title"
    )

    monkeypatch.setattr(
        task_repo_module,
        "task_record",
        lambda _task_id, include_archive=False: None if not include_archive else archived_record,
    )
    assert (
        task_commands_module._resolve_finish_pr_title(
            task_id="TASK-326",
            branch_name="codex/task-326-finish-pr-bootstrap",
        )
        == "TASK-326: Archived Title"
    )

    monkeypatch.setattr(task_repo_module, "task_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        task_repo_module,
        "closed_task_archive_record",
        lambda _task_id: archived_record,
    )
    assert (
        task_commands_module._resolve_finish_pr_title(
            task_id="TASK-326",
            branch_name="codex/task-326-finish-pr-bootstrap",
        )
        == "TASK-326: Archived Title"
    )

    monkeypatch.setattr(task_repo_module, "closed_task_archive_record", lambda _task_id: None)
    assert (
        task_commands_module._resolve_finish_pr_title(
            task_id="TASK-326",
            branch_name="codex/task-326-finish-pr-bootstrap",
        )
        == "TASK-326: finish pr bootstrap"
    )
