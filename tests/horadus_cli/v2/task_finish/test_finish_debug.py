from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_finish.merge as merge_module
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
            number=0, url=result.stdout.strip(), head_ref_name=branch_name
        )

    monkeypatch.setattr(task_commands_module, "_find_open_branch_pull_request", compat_lookup)


def test_finish_task_data_emits_debug_lines_when_finish_debug_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_outdated_thread_auto_resolution(monkeypatch)
    monkeypatch.setenv("HORADUS_FINISH_DEBUG", "1")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-332-finish-debug-lines",
            branch_task_id="TASK-332",
            task_id="TASK-332",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-332 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [], "pass")
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _review_gate_process(
            reason="thumbs_up",
            reviewed_head_oid="head-sha-332",
            summary_thumbs_up=True,
            summary="review gate passed early: reviewer reacted THUMBS_UP.",
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_current_required_checks_blocker", lambda **_kwargs: None
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
            ["Task lifecycle: TASK-332", "- state: local-main-synced", "- strict complete: yes"],
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
            return _completed(args, stdout="https://example.invalid/pr/332\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/332"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-332: finish debug lines","body":"Primary-Task: TASK-332\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-332\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/332"]:
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
            "refs/heads/codex/task-332-finish-debug-lines",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-332", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-332"
    assert any(
        "Required checks passed for https://example.invalid/pr/332" in line for line in lines
    )
    assert any("Review gate subprocess exited rc=0" in line for line in lines)
    assert any("Parsed review gate result: status=pass, reason=thumbs_up" in line for line in lines)
    assert any("Review gate passed for https://example.invalid/pr/332" in line for line in lines)
    assert any("Resolved merge commit merge-commit-332." in line for line in lines)


def test_auto_merge_debug_lines_emit_when_finish_debug_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_FINISH_DEBUG", "1")

    lines = merge_module._auto_merge_debug_lines(
        pr_url="https://example.invalid/pr/332",
        auto_merge_result=_completed(["gh", "pr", "merge"], returncode=0),
    )

    assert len(lines) == 1
    assert "Auto-merge command exited rc=0 for https://example.invalid/pr/332" in lines[0]
