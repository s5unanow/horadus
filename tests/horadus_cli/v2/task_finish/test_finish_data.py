from __future__ import annotations

import subprocess
from unittest import mock

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed
from tests.horadus_cli.v2.task_finish.helpers import (
    _disable_outdated_thread_auto_resolution,
    _review_gate_process,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _compat_branch_pr_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)

    def compat_lookup(
        *, branch_name: str, config: task_commands_module.FinishConfig
    ) -> tuple[int, dict[str, object], list[str]] | task_commands_module.BranchPullRequest | None:
        result = task_commands_module._run_command(
            [config.gh_bin, "pr", "view", branch_name, "--json", "url"]
        )
        if result.returncode != 0:
            return None
        return task_commands_module.BranchPullRequest(
            number=0,
            url=result.stdout.strip(),
            head_ref_name=branch_name,
        )

    monkeypatch.setattr(task_commands_module, "_find_open_branch_pull_request", compat_lookup)


def test_finish_task_data_blocks_for_missing_required_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: None if name == "gh" else "/bin/fake",
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert lines[0] == "Task finish blocked: missing required command 'gh'."


def test_finish_task_data_propagates_finish_context_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    expected = task_commands_module._task_blocked(
        "working tree must be clean.",
        next_action="Commit or stash local changes, then re-run `horadus tasks finish TASK-257`.",
    )
    monkeypatch.setattr(
        task_commands_module, "_resolve_finish_context", lambda *_args, **_kwargs: expected
    )

    assert task_commands_module.finish_task_data("TASK-257", dry_run=False) == expected


def test_finish_task_data_blocks_when_task_closure_state_is_not_on_pr_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-295-enforce-pre-merge-task-closure",
            branch_task_id="TASK-295",
            task_id="TASK-295",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-295 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        lambda *_args, **_kwargs: (
            "primary task closure state is not present on the PR head.",
            {
                "task_closure": {
                    "present_in_backlog": True,
                    "active_sprint_lines": ["- `TASK-295` Enforce Pre-Merge Task Closure State"],
                    "present_in_completed": False,
                    "present_in_closed_archive": False,
                }
            },
            [
                "- tasks/BACKLOG.md still contains the task as open.",
                "- tasks/CURRENT_SPRINT.md still lists the task under Active Tasks:",
                "  - `TASK-295` Enforce Pre-Merge Task Closure State",
            ],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/295\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/295"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-295: closure guard","body":"Primary-Task: TASK-295\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-295", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["task_closure"]["present_in_backlog"] is True
    assert (
        lines[0] == "Task finish blocked: primary task closure state is not present on the PR head."
    )
    assert "horadus tasks close-ledgers TASK-295" in lines[1]
    assert "- tasks/BACKLOG.md still contains the task as open." in lines


def test_finish_task_data_dry_run_reports_bootstrap_for_missing_branch_and_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_title",
        lambda **_kwargs: "TASK-258: canonical finish",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_body",
        lambda **_kwargs: "Primary-Task: TASK-258\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-258-canonical-finish"
    assert data["generated_pr_title"] == "TASK-258: canonical finish"
    assert data["generated_pr_body"] == "Primary-Task: TASK-258\n"
    assert lines[0] == "Finishing TASK-258 from codex/task-258-canonical-finish"
    assert "Dry run: would push `codex/task-258-canonical-finish` to `origin`." in lines
    assert (
        "Dry run: would create PR `TASK-258: canonical finish` for "
        "`codex/task-258-canonical-finish`."
    ) in lines


def test_finish_task_data_blocks_when_local_remote_pr_heads_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-295-enforce-pre-merge-task-closure",
            branch_task_id="TASK-295",
            task_id="TASK-295",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-295 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_branch_head_alignment_blocker",
        lambda **_kwargs: (
            "task branch head, pushed branch head, and PR head are not aligned.",
            {
                "branch_name": "codex/task-295-enforce-pre-merge-task-closure",
                "local_branch_head": "local-sha",
                "remote_branch_head": "remote-sha",
                "pr_head": "pr-sha",
            },
            [
                "- local branch head: local-sha",
                "- remote branch head: remote-sha",
                "- PR head: pr-sha",
            ],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/295\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/295"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-295: head alignment","body":"Primary-Task: TASK-295\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-295", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["local_branch_head"] == "local-sha"
    assert (
        lines[0]
        == "Task finish blocked: task branch head, pushed branch head, and PR head are not aligned."
    )
    assert "local branch, origin branch, and PR head all match" in lines[1]
    assert lines[-1] == "- PR head: pr-sha"


def test_finish_task_data_blocks_when_push_gate_docker_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-261-docker-readiness",
            branch_task_id="TASK-261",
            task_id="TASK-261",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=False,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker auto-start did not make the daemon ready before timeout."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-261", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["docker_ready"] is False
    assert "Docker is not ready for the next required push gate." in lines[0]
    assert "Make Docker ready, then re-run `horadus tasks finish TASK-261`." in lines[1]
    assert lines[-1] == "Docker auto-start did not make the daemon ready before timeout."


def test_finish_task_data_dry_run_does_not_attempt_docker_auto_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-261-docker-readiness",
            branch_task_id="TASK-261",
            task_id="TASK-261",
        ),
    )
    docker_calls: list[str] = []
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_title",
        lambda **_kwargs: "TASK-261: docker readiness",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_pr_body",
        lambda **_kwargs: "Primary-Task: TASK-261\n",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-261 (Primary-Task)"
        ),
    )
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

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-261", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert docker_calls == []
    assert data["branch_name"] == "codex/task-261-docker-readiness"
    assert data["generated_pr_title"] == "TASK-261: docker readiness"
    assert "Dry run: would push `codex/task-261-docker-readiness` to `origin`." in lines
    assert (
        "Dry run: would create PR `TASK-261: docker readiness` for "
        "`codex/task-261-docker-readiness`."
    ) in lines


def test_finish_task_data_blocks_when_required_checks_do_not_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (False, ["required-check failure details"], "timeout"),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert "required PR checks did not pass before timeout" in lines[0]
    assert "Inspect the failing required checks" in lines[1]
    assert lines[-1] == "required-check failure details"


def test_finish_task_data_blocks_immediately_when_required_checks_are_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (False, ["CI / Test: fail"], "fail"),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: required PR checks are failing on the current head."
    assert lines[-1] == "CI / Test: fail"


def test_finish_task_data_blocks_when_checks_turn_red_after_review_gate_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-275-enforce-finish-review-timeout",
            branch_task_id="TASK-275",
            task_id="TASK-275",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-275 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-275",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        mock.Mock(
            side_effect=[
                None,
                (
                    "required PR checks are failing on the current head.",
                    ["CI / Test: fail"],
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/275\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/275"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-275: enforce finish timeout","body":"Primary-Task: TASK-275\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/275"
    assert lines[0] == "Task finish blocked: required PR checks are failing on the current head."
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "CI / Test: fail"


def test_finish_task_data_blocks_on_unresolved_review_threads_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-290-finish-ci-failure-reporting",
            branch_task_id="TASK-290",
            task_id="TASK-290",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-290 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-290",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- tools/horadus/python/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
            "  Please resolve this thread.",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review`."
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/290\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-290: finish CI failure reporting","body":"Primary-Task: TASK-290\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-290", dry_run=False)
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/290"
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert any("Please resolve this thread." in line for line in lines)
    assert not any("Requested a fresh review" in line for line in lines)


def test_finish_task_data_blocks_on_unresolved_review_threads_after_clean_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-290-finish-ci-failure-reporting",
            branch_task_id="TASK-290",
            task_id="TASK-290",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-290 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-290",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-290 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- tools/horadus/python/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
            "  Please resolve this thread.",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head `head-sha-290`."
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/290\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-290: finish CI failure reporting","body":"Primary-Task: TASK-290\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-290", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert not any(
        "Requested a fresh review from `chatgpt-codex-connector[bot]`" in line for line in lines
    )
    assert "  Please resolve this thread." in lines


def test_finish_task_data_uses_non_blocking_pending_check_mode_after_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-290-finish-ci-failure-reporting",
            branch_task_id="TASK-290",
            task_id="TASK-290",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-290 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-290",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-290", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    blocker_calls: list[dict[str, object]] = []

    def fake_current_required_checks_blocker(**kwargs: object) -> tuple[str, list[str]] | None:
        blocker_calls.append(dict(kwargs))
        return None

    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        fake_current_required_checks_blocker,
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/290\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-290: finish CI failure reporting","body":"Primary-Task: TASK-290\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-290\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/290"]:
            if "--auto" in args:
                return _completed(args)
            return _completed(
                args,
                returncode=1,
                stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
            )
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
            "refs/heads/codex/task-290-finish-ci-failure-reporting",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-290", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-290"
    assert blocker_calls == [
        {
            "pr_url": "https://example.invalid/pr/290",
            "config": mock.ANY,
            "block_pending": True,
        },
        {
            "pr_url": "https://example.invalid/pr/290",
            "config": mock.ANY,
            "block_pending": True,
        },
    ]
    assert any("Base branch policy requires auto-merge" in line for line in lines)


def test_finish_task_data_blocks_when_pr_metadata_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            return _completed(args, returncode=1, stderr="metadata failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: metadata failed"


def test_finish_task_data_blocks_when_pr_metadata_is_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            return _completed(args, stdout="{bad")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: Unable to parse the PR title/body."


def test_finish_task_data_blocks_when_pr_state_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, returncode=1, stderr="state failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: state failed"


def test_finish_task_data_blocks_when_branch_is_not_pushed_after_pr_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert (
        lines[0]
        == "Task finish blocked: branch `codex/task-257-coverage-hard-fail` is not pushed to origin."
    )


def test_finish_task_data_blocks_when_pr_draft_status_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, returncode=1, stderr="draft failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines[0] == "Task finish blocked: draft failed"


def test_finish_task_data_blocks_when_pr_is_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="true\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is draft; refusing to merge."


def test_finish_task_data_dry_run_reports_merge_and_sync_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert (
        lines[-1]
        == "Dry run: scope and PR preconditions passed; would wait for checks, merge, and sync main."
    )


def test_finish_task_data_rejects_zero_review_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "0")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        "Task finish blocked: REVIEW_TIMEOUT_SECONDS must be positive for `horadus tasks finish`.",
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_rejects_review_timeout_override_without_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-283", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        (
            "Task finish blocked: REVIEW_TIMEOUT_SECONDS may differ from the default 600s "
            "(10 minutes) only when "
            "HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE=1 confirms an explicit human "
            "request."
        ),
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_allows_review_timeout_override_with_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE", "1")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-283-finish-review-thumbs-up",
            branch_task_id="TASK-283",
            task_id="TASK-283",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-283 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="thumbs_up",
            reviewed_head_oid="head-sha-283",
            summary_thumbs_up=True,
            summary=(
                "review gate passed early: chatgpt-codex-connector[bot] reacted THUMBS_UP on the "
                "PR summary during the active review window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-283", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/283\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/283"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-283: finish review thumbs up","body":"Primary-Task: TASK-283\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-283\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/283"]:
            return _completed(args)
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
            "refs/heads/codex/task-283-finish-review-thumbs-up",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-283", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-283"
    assert any("reacted THUMBS_UP on the PR summary" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-283 and synced main."


def test_finish_task_data_rejects_review_timeout_policy_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_POLICY", "fail")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        "Task finish blocked: REVIEW_TIMEOUT_POLICY must remain `allow` for `horadus tasks finish`.",
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_allows_merge_when_review_gate_times_out_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-275-enforce-finish-review-timeout",
            branch_task_id="TASK-275",
            task_id="TASK-275",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-275 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-275",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-276", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/275\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/275"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-275: enforce finish timeout","body":"Primary-Task: TASK-275\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-275\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/275"]:
            return _completed(args)
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
            "refs/heads/codex/task-275-enforce-finish-review-timeout",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["pr_url"] == "https://example.invalid/pr/275"
    assert data["merge_commit"] == "merge-commit-275"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-275 and synced main."


def test_finish_task_data_allows_early_merge_on_pr_summary_thumbs_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-283-finish-review-thumbs-up",
            branch_task_id="TASK-283",
            task_id="TASK-283",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-283 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="thumbs_up",
            reviewed_head_oid="head-sha-283",
            summary_thumbs_up=True,
            summary=(
                "review gate passed early: chatgpt-codex-connector[bot] reacted THUMBS_UP "
                "on the PR summary during the active review window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-283", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/283\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/283"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-283: finish review thumbs up","body":"Primary-Task: TASK-283\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-283\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/283"]:
            return _completed(args)
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
            "refs/heads/codex/task-283-finish-review-thumbs-up",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-283", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-283"
    assert any("review gate passed early:" in line for line in lines)
    assert not any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-283 and synced main."


def test_finish_task_data_resumes_from_main_with_explicit_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-289-finish-branch-context-recovery",
            branch_task_id="TASK-289",
            task_id="TASK-289",
            current_branch="main",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-289 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-289",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-289", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:4]
            == [
                "gh",
                "pr",
                "view",
                "codex/task-289-finish-branch-context-recovery",
            ]
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/289\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/289"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-289: finish branch context recovery","body":"Primary-Task: TASK-289\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-289\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/289"]:
            return _completed(args)
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
            "refs/heads/codex/task-289-finish-branch-context-recovery",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-289", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["pr_url"] == "https://example.invalid/pr/289"
    assert data["merge_commit"] == "merge-commit-289"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert lines[0] == (
        "Resuming TASK-289 from main using task branch codex/task-289-finish-branch-context-recovery."
    )
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-289 and synced main."


def test_finish_task_data_restarts_review_window_after_pr_head_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    gate_results = iter(
        [
            _review_gate_process(
                status="head_changed",
                reason="head_changed",
                reviewed_head_oid="head-a",
                current_head_oid="head-b",
                returncode=3,
                summary="review gate deferred: PR head changed from head-a to head-b during the review window.",
            ),
            _review_gate_process(
                reason="silent_timeout_allow",
                reviewed_head_oid="head-b",
                current_head_oid="head-b",
                timed_out=True,
                summary=(
                    "review gate timeout: no actionable current-head review feedback from "
                    "chatgpt-codex-connector[bot] for head-b within 600s. Continuing due to timeout policy=allow."
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: next(gate_results),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-b."
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-307", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-307\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/307"]:
            return _completed(args)
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
            "refs/heads/codex/task-307-stateful-review-loop",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-307"
    assert any("PR head changed from head-a to head-b" in line for line in lines)
    assert any("Requested a fresh review" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-307 and synced main."


def test_finish_task_data_refreshes_stale_review_state_before_waiting_for_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    stale_thread_ids = iter([["PRRT_stale_thread_309"], []])
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: next(stale_thread_ids),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (
            True,
            ["Resolved outdated review thread automatically: PRRT_stale_thread_309"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-sha-309."
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-309",
            current_head_oid="head-sha-309",
            timed_out=True,
            summary=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-309 within 600s. Continuing due "
                "to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-309", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-309\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/309"]:
            return _completed(args)
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
            "refs/heads/codex/task-309-finish-rerun-refresh",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-309"
    stale_index = lines.index(
        "Resolved outdated review thread automatically: PRRT_stale_thread_309"
    )
    request_index = lines.index(
        "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-sha-309."
    )
    refresh_index = next(
        index
        for index, line in enumerate(lines)
        if "discarding the previous review window and starting a fresh 600s review window" in line
    )
    wait_index = next(
        index for index, line in enumerate(lines) if line.startswith("Waiting for review gate ")
    )
    assert stale_index < wait_index
    assert request_index < wait_index
    assert refresh_index < wait_index
    assert lines[-1] == "Task finish passed: merged merge-commit-309 and synced main."


def test_finish_task_data_retries_fresh_review_request_without_stale_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_needs_pre_review_fresh_review_request",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-sha-309."
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-309",
            current_head_oid="head-sha-309",
            timed_out=True,
            summary=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-309 within 600s. Continuing due "
                "to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-309", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-309\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/309"]:
            return _completed(args)
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
            "refs/heads/codex/task-309-finish-rerun-refresh",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-309"
    request_index = lines.index(
        "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-sha-309."
    )
    refresh_index = next(
        index
        for index, line in enumerate(lines)
        if "Detected reviewer activity on an older head; discarding the previous review window and starting a fresh 600s review window."
        in line
    )
    wait_index = next(
        index for index, line in enumerate(lines) if line.startswith("Waiting for review gate ")
    )
    assert request_index < wait_index
    assert refresh_index < wait_index
    assert lines[-1] == "Task finish passed: merged merge-commit-309 and synced main."


def test_finish_task_data_blocks_when_pre_review_refresh_cannot_request_fresh_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: ["PRRT_stale_thread_309"],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (
            True,
            ["Resolved outdated review thread automatically: PRRT_stale_thread_309"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Failed to request a fresh review from `chatgpt-codex-connector[bot]` automatically.",
            "comment failed",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("review gate should not run")),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert (
        lines[0]
        == "Task finish blocked: unable to request a fresh current-head review automatically."
    )
    assert "comment failed" in lines


def test_finish_task_data_blocks_when_head_change_cannot_request_fresh_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="head_changed",
            reason="head_changed",
            reviewed_head_oid="head-a",
            current_head_oid="head-b",
            returncode=3,
            summary="review gate deferred: PR head changed from head-a to head-b during the review window.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_head_finish_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Failed to request a fresh review from `chatgpt-codex-connector[bot]` automatically.",
            "comment failed",
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert (
        lines[0]
        == "Task finish blocked: unable to request a fresh current-head review automatically."
    )
    assert any("PR head changed from head-a to head-b" in line for line in lines)
    assert lines[-1] == "comment failed"


def test_finish_task_data_blocks_when_pre_review_stale_thread_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: ["PRRT_stale_thread_309"],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (
            False,
            ["Failed to resolve outdated review threads automatically."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert (
        lines[0]
        == "Task finish blocked: PR still has outdated unresolved review threads that could not be auto-resolved."
    )
    assert lines[-1] == "Failed to resolve outdated review threads automatically."


def test_finish_task_data_blocks_when_review_gate_returns_unreadable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="{bad", returncode=0),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/307"
    assert lines[0] == "Task finish blocked: review gate returned an unreadable result."
    assert any("Unable to parse review gate payload:" in line for line in lines)


def test_finish_task_data_blocks_when_review_thread_query_fails_after_review_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-307",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("graphql failed")),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/307"
    assert (
        lines[0]
        == "Task finish blocked: unable to determine unresolved review thread state on the current head."
    )
    assert lines[-1] == "graphql failed"


def test_finish_task_data_blocks_when_pr_head_changes_to_non_mergeable_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="head_changed",
            reason="head_changed",
            reviewed_head_oid="head-a",
            current_head_oid="head-b",
            returncode=3,
            summary="review gate deferred: PR head changed from head-a to head-b during the review window.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_head_finish_blocker",
        lambda **_kwargs: ("required checks pending", {}, ["CI / build: pending"]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/307"
    assert lines[0] == "Task finish blocked: required checks pending"
    assert "CI / build: pending" in lines


def test_finish_task_data_head_change_blocker_stops_before_fresh_review_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="head_changed",
            reason="head_changed",
            reviewed_head_oid="head-a",
            current_head_oid="head-b",
            returncode=3,
            summary="review gate deferred: PR head changed from head-a to head-b during the review window.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_head_finish_blocker",
        lambda **_kwargs: ("required checks pending", {}, ["CI / build: pending"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "fresh review should not be requested when current head is not merge-ready"
            )
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert lines[0] == "Task finish blocked: required checks pending"
    assert "CI / build: pending" in lines


def test_finish_task_data_returns_head_change_blocker_result_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="head_changed",
            reason="head_changed",
            reviewed_head_oid="head-a",
            current_head_oid="head-b",
            returncode=3,
            summary="review gate deferred: PR head changed from head-a to head-b during the review window.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_head_changed_review_gate_blocker",
        lambda **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"task_id": "TASK-309", "pr_url": "https://example.invalid/pr/309"},
            ["Task finish blocked: required checks pending", "CI / build: pending"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["task_id"] == "TASK-309"
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert lines[0] == "Task finish blocked: required checks pending"
    assert "CI / build: pending" in lines


def test_finish_task_data_does_not_request_fresh_review_for_non_timeout_thread_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="thumbs_up",
            reviewed_head_oid="head-sha-307",
            current_head_oid="head-sha-307",
            timed_out=False,
            summary_thumbs_up=True,
            summary="review gate passed early: bot reacted THUMBS_UP.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_current_required_checks_blocker", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: ["- src/file.py:10", "  Please resolve this thread."],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not request review")),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/307"
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."


def test_finish_task_data_blocks_when_outdated_review_thread_query_fails_after_review_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-307-stateful-review-loop",
            branch_task_id="TASK-307",
            task_id="TASK-307",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-307 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-307",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module, "_unresolved_review_thread_lines", lambda **_kwargs: []
    )
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("pagination incomplete")),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/307\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/307"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-307: stateful review loop","body":"Primary-Task: TASK-307\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-307", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/307"
    assert (
        lines[0]
        == "Task finish blocked: unable to determine outdated review thread state on the current head."
    )
    assert lines[-1] == "pagination incomplete"


def test_finish_task_data_blocks_when_post_review_outdated_thread_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-309-finish-rerun-refresh",
            branch_task_id="TASK-309",
            task_id="TASK-309",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-309 (Primary-Task)"
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
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="pass",
            reason="thumbs_up",
            reviewed_head_oid="head-sha-309",
            current_head_oid="head-sha-309",
            summary="review gate passed early: reviewer signaled approval on the current head.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_unresolved_review_thread_lines", lambda **_kwargs: []
    )
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        mock.Mock(side_effect=[[], ValueError("post-review pagination incomplete")]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/309\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/309"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-309: finish rerun refresh","body":"Primary-Task: TASK-309\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-309", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/309"
    assert (
        lines[0]
        == "Task finish blocked: unable to determine outdated review thread state on the current head."
    )
    assert lines[-1] == "post-review pagination incomplete"


def test_finish_task_data_blocks_when_review_gate_process_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-284-finish-timeout-exit",
            branch_task_id="TASK-284",
            task_id="TASK-284",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-284 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )

    def fake_run_review_gate(**_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise task_commands_module.CommandTimeoutError(
            ["python", "./scripts/check_pr_review_gate.py"],
            631,
        )

    monkeypatch.setattr(task_commands_module, "_run_review_gate", fake_run_review_gate)
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/284\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/284"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-284: finish timeout exit","body":"Primary-Task: TASK-284\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-284", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/284"
    assert (
        lines[0]
        == "Task finish blocked: review gate command did not exit after the configured wait window."
    )
    assert lines[-1] == "Command timed out after 631s: python ./scripts/check_pr_review_gate.py"


def test_finish_task_data_blocks_when_merge_command_hangs_after_review_gate_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-284-finish-timeout-exit",
            branch_task_id="TASK-284",
            task_id="TASK-284",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-284 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="silent_timeout_allow",
            reviewed_head_oid="head-sha-284",
            timed_out=True,
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    real_run_command_with_timeout = task_commands_module._run_command_with_timeout

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/284\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/284"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-284: finish timeout exit","body":"Primary-Task: TASK-284\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    def fake_run_command_with_timeout(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "merge"]:
            raise task_commands_module.CommandTimeoutError(args, 120)
        return real_run_command_with_timeout(args, **kwargs)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        fake_run_command_with_timeout,
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-284", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/284"
    assert (
        lines[0]
        == "Task finish blocked: merge command did not exit cleanly after the review gate passed."
    )
    assert lines[-1].startswith("Command timed out after 120s: gh pr merge")


def test_finish_task_data_blocks_when_review_gate_finds_actionable_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-276-allow-silent-review-timeout",
            branch_task_id="TASK-276",
            task_id="TASK-276",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-276 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            status="block",
            reason="actionable_comments",
            reviewed_head_oid="head-sha-276",
            actionable_lines=[
                "- tools/horadus/python/horadus_cli/task_commands.py:1900 https://example.invalid/comment/276",
                "  Please address this before merge.",
            ],
            returncode=2,
            summary="review gate failed: actionable current-head review comments found:",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/276\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/276"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-276: allow silent review timeout","body":"Primary-Task: TASK-276\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-276", dry_run=False)

    assert exit_code == 2
    assert data["pr_url"] == "https://example.invalid/pr/276"
    assert lines[0] == "Task finish blocked: review gate did not pass."
    assert (
        lines[1]
        == "Next action: Address the current-head review feedback, then re-run `horadus tasks finish`."
    )
    assert lines[-2].startswith("- tools/horadus/python/horadus_cli/task_commands.py:1900")


def test_finish_task_data_blocks_when_pr_title_or_body_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-274-standardize-task-pr-titles",
            branch_task_id="TASK-274",
            task_id="TASK-274",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"],
            returncode=1,
            stdout="PR scope guard failed.\nPR title must match required task format:\n  TASK-XXX: short summary\n",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/274\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/274"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"feat(repo): standardize PR titles","body":"Primary-Task: TASK-274\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-274", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/274"
    assert "PR scope validation failed." in lines[0]
    assert "Fix the PR title to `TASK-274: short summary`" in lines[1]
    assert "PR title must match required task format" in lines[-2]


def test_finish_task_data_succeeds_when_pr_already_merged_after_remote_branch_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-258",
            clean_current_head_review=True,
            summary=(
                "review gate passed: "
                "chatgpt-codex-connector[bot] approved current head head-sha-258 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_branch_head_alignment_blocker",
        lambda **_kwargs: (
            "task branch head, pushed branch head, and PR head are not aligned.",
            {},
            ["- local branch head: missing"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_pre_merge_task_closure_blocker",
        lambda *_args, **_kwargs: (
            "primary task closure state is not present on the PR head.",
            {},
            ["- tasks/BACKLOG.md still contains the task as open."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
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
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert "PR already merged; skipping merge step." in lines
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."


def test_finish_task_data_enables_auto_merge_when_branch_policy_requires_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-258",
            clean_current_head_review=True,
            summary=(
                "review gate passed: "
                "chatgpt-codex-connector[bot] approved current head head-sha-258 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/258"]:
            if "--auto" in args:
                return _completed(args)
            return _completed(
                args,
                returncode=1,
                stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
            )
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
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert any("Base branch policy requires auto-merge" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."


def test_finish_task_data_auto_resolves_outdated_threads_before_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-306-stale-thread-finish",
            branch_task_id="TASK-306",
            task_id="TASK-306",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-306 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-306",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-306 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        mock.Mock(side_effect=[[], ["PRRT_stale_thread_1"]]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (
            True,
            ["Resolved outdated review thread automatically: PRRT_stale_thread_1"],
        ),
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-306", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-306."
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/306\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/306"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-306: stale thread finish","body":"Primary-Task: TASK-306\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-306\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/306"]:
            if "--auto" in args:
                return _completed(args)
            return _completed(
                args,
                returncode=1,
                stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
            )
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
            "refs/heads/codex/task-306-stale-thread-finish",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-306", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-306"
    assert any(
        line == "Resolved outdated review thread automatically: PRRT_stale_thread_1"
        for line in lines
    )
    assert lines[-1] == "Task finish passed: merged merge-commit-306 and synced main."


def test_finish_task_data_blocks_when_auto_resolving_outdated_threads_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-306-stale-thread-finish",
            branch_task_id="TASK-306",
            task_id="TASK-306",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-306 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-306",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-306 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        mock.Mock(side_effect=[[], ["PRRT_stale_thread_2"]]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (False, ["Failed to resolve outdated review threads automatically."]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-306."
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/306\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/306"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-306: stale thread finish","body":"Primary-Task: TASK-306\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-306", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/306"
    assert (
        lines[0]
        == "Task finish blocked: PR still has outdated unresolved review threads that could not be auto-resolved."
    )
    assert lines[-1] == "Failed to resolve outdated review threads automatically."


def test_finish_task_data_continues_when_merge_timeout_or_failure_still_results_in_merged_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-258",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-258 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def make_fake_run_command(state_outputs: list[str]):
        state_calls = 0

        def fake_run_command(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal state_calls
            if args[:2] == ["git", "ls-remote"]:
                return _completed(args)
            if (
                args[:3] == ["gh", "pr", "view"]
                and len(args) >= 6
                and args[3].startswith("codex/task-")
                and "--json" in args
                and "url" in args
            ):
                return _completed(args, stdout="https://example.invalid/pr/258\n")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
                if "--json" in args and "title,body" in args:
                    return _completed(
                        args,
                        stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                    )
                if "--json" in args and "state" in args:
                    output = state_outputs[min(state_calls, len(state_outputs) - 1)]
                    state_calls += 1
                    return _completed(args, stdout=output)
                if "--json" in args and "isDraft" in args:
                    return _completed(args, stdout="false\n")
                if "--json" in args and "mergeCommit" in args:
                    return _completed(args, stdout="merge-commit-258\n")
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
                "refs/heads/codex/task-258-canonical-finish",
            ]:
                return _completed(args, returncode=1)
            raise AssertionError(args)

        return fake_run_command

    monkeypatch.setattr(
        task_commands_module, "_run_command", make_fake_run_command(["OPEN\n", "MERGED\n"])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: (_ for _ in ()).throw(
            task_commands_module.CommandTimeoutError(args, 120)
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Merge command timed out, but PR is already MERGED; continuing." in lines

    monkeypatch.setattr(
        task_commands_module, "_run_command", make_fake_run_command(["OPEN\n", "MERGED\n"])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: _completed(
            args, returncode=1, stderr="merge exited after server-side completion"
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Merge step reported failure, but PR is already MERGED; continuing." in lines


def test_finish_task_data_covers_auto_merge_timeout_and_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-258",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-258 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def make_fake_run_command(stage: str):
        state_calls = 0

        def fake_run_command(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal state_calls
            if args[:2] == ["git", "ls-remote"]:
                return _completed(args)
            if (
                args[:3] == ["gh", "pr", "view"]
                and len(args) >= 6
                and args[3].startswith("codex/task-")
                and "--json" in args
                and "url" in args
            ):
                return _completed(args, stdout="https://example.invalid/pr/258\n")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
                if "--json" in args and "title,body" in args:
                    return _completed(
                        args,
                        stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                    )
                if "--json" in args and "state" in args:
                    state_calls += 1
                    if stage == "auto-timeout-success":
                        if state_calls <= 2:
                            return _completed(args, stdout="OPEN\n")
                        return _completed(args, stdout="MERGED\n")
                    if stage == "auto-failure-merged":
                        if state_calls <= 2:
                            return _completed(args, stdout="OPEN\n")
                        return _completed(args, stdout="MERGED\n")
                    if stage == "auto-timeout-blocked":
                        return _completed(args, stdout="OPEN\n")
                    return _completed(args, stdout="OPEN\n")
                if "--json" in args and "isDraft" in args:
                    return _completed(args, stdout="false\n")
                if "--json" in args and "mergeCommit" in args:
                    return _completed(args, stdout="merge-commit-258\n")
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
                "refs/heads/codex/task-258-canonical-finish",
            ]:
                return _completed(args, returncode=1)
            raise AssertionError(args)

        return fake_run_command

    def make_fake_run_command_with_timeout(stage: str):
        def fake_run_command_with_timeout(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if "--auto" not in args:
                return _completed(
                    args,
                    returncode=1,
                    stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
                )
            if stage == "auto-timeout-success":
                raise task_commands_module.CommandTimeoutError(args, 120)
            if stage == "auto-timeout-blocked":
                raise task_commands_module.CommandTimeoutError(args, 120)
            if stage == "auto-failure-merged":
                return _completed(args, returncode=1, stderr="auto merge finished server-side")
            if stage == "auto-failure-blocked":
                return _completed(args, returncode=1, stderr="auto merge still blocked")
            if stage == "auto-merge-wait-timeout":
                return _completed(args)
            raise AssertionError(stage)

        return fake_run_command_with_timeout

    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-timeout-success"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-timeout-success"),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Auto-merge command timed out, but PR is already MERGED; continuing." in lines

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-timeout-blocked"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-timeout-blocked"),
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert (
        lines[0]
        == "Task finish blocked: auto-merge command did not exit cleanly after the review gate passed."
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-failure-merged"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-failure-merged"),
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-failure-blocked"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-failure-blocked"),
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: merge failed."
    assert lines[-1] == "auto merge still blocked"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-merge-wait-timeout"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-merge-wait-timeout"),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (False, ["still waiting"])
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: auto-merge did not complete before timeout."
    assert lines[-1] == "still waiting"


def test_finish_task_data_blocks_when_merge_fails_without_auto_merge_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="clean_review",
            reviewed_head_oid="head-sha-258",
            clean_current_head_review=True,
            timed_out=True,
            summary=(
                "review gate passed: chatgpt-codex-connector[bot] approved current head "
                "head-sha-258 during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    state_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal state_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                state_calls += 1
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: _completed(
            args, returncode=1, stderr="merge failed for another reason"
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: merge failed."
    assert lines[-1] == "merge failed for another reason"


def test_finish_task_data_blocks_when_completion_verifier_fails_after_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-259-done-state-verifier",
            branch_task_id="TASK-259",
            task_id="TASK-259",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-259 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"lifecycle_state": "merged", "strict_complete": False},
            [
                "Task lifecycle: TASK-259",
                "- state: merged",
                "- strict complete: no",
                "Strict verification failed: repo-policy completion requires state `local-main-synced`.",
            ],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/259\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/259"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-259: done state verifier","body":"Primary-Task: TASK-259\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-259\n")
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
            "refs/heads/codex/task-259-done-state-verifier",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-259", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["lifecycle"]["lifecycle_state"] == "merged"
    assert "completion verifier did not pass after merge" in lines[0]
    assert "horadus tasks lifecycle TASK-259 --strict" in lines[1]


@pytest.mark.parametrize(
    ("stage", "expected_first_line", "expected_last_line"),
    [
        (
            "merge-commit",
            "Task finish blocked: could not determine merge commit.",
            "Next action: Inspect the merged PR state in GitHub, then re-run `horadus tasks finish`.",
        ),
        (
            "switch-main",
            "Task finish blocked: switch failed",
            "Next action: Resolve the local git state and switch to `main`, then re-run `horadus tasks finish`.",
        ),
        (
            "pull-main",
            "Task finish blocked: pull failed",
            "Next action: Resolve the local `main` sync issue and re-run `horadus tasks finish`.",
        ),
        (
            "cat-file",
            "Task finish blocked: merge commit merge-commit-258 is not available locally after syncing main.",
            "Next action: Fetch/pull `main` successfully, then re-run `horadus tasks finish`.",
        ),
        (
            "delete-branch",
            "Task finish blocked: merged branch `codex/task-258-canonical-finish` still exists locally and could not be deleted.",
            "Next action: Delete `codex/task-258-canonical-finish` locally after syncing main, then re-run `horadus tasks finish`.",
        ),
    ],
)
def test_finish_task_data_blocks_on_post_merge_sync_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_first_line: str,
    expected_last_line: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                if stage == "merge-commit":
                    return _completed(args, returncode=1, stderr="merge commit unavailable")
                return _completed(args, stdout="merge-commit-258\n")
        if args[:3] == ["git", "switch", "main"]:
            if stage == "switch-main":
                return _completed(args, returncode=1, stderr="switch failed")
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            if stage == "pull-main":
                return _completed(args, returncode=1, stderr="pull failed")
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            if stage == "cat-file":
                return _completed(args, returncode=1)
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=0 if stage == "delete-branch" else 1)
        if args[:3] == ["git", "branch", "-d"]:
            return _completed(args, returncode=1, stderr="delete failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == expected_first_line
    assert lines[1] == expected_last_line


def test_finish_task_data_deletes_local_branch_when_it_still_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
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
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args)
        if args[:3] == ["git", "branch", "-d"]:
            return _completed(args, stdout="Deleted branch.\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."
