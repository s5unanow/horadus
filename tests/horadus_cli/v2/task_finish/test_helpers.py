from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_finish.review as review_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def test_run_command_and_shell_execute_locally() -> None:
    command_result = task_commands_module._run_command(["/bin/echo", "hi"])
    shell_result = task_commands_module._run_shell("printf shell-ok")

    assert command_result.stdout.strip() == "hi"
    assert shell_result.stdout == "shell-ok"


def test_run_command_raises_wrapped_timeout_error_with_captured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            ["git", "status"],
            5,
            output="partial-out",
            stderr="partial-err",
        )

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout)

    with pytest.raises(task_commands_module.CommandTimeoutError) as excinfo:
        task_commands_module._run_command(["git", "status"], timeout_seconds=5)

    assert excinfo.value.stdout == "partial-out"
    assert excinfo.value.stderr == "partial-err"
    assert excinfo.value.output_lines() == ["partial-out", "partial-err"]


def test_run_command_requires_explicit_timeout_value_when_subprocess_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["git", "status"], 5)

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout)

    with pytest.raises(
        RuntimeError,
        match="subprocess timed out without an explicit timeout value",
    ):
        task_commands_module._run_command(["git", "status"])


def test_task_command_helper_parsers_cover_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    assert task_commands_module._result_message(_completed(["x"]), "fallback") == "fallback"
    assert task_commands_module._output_lines(
        _completed(["x"], stdout=" one \n", stderr=" two ")
    ) == ["one", "two"]
    assert task_commands_module._parse_report_date(None) == datetime.now(tz=UTC).date()
    assert task_commands_module._parse_recorded_at("2026-03-08T10:00:00").tzinfo == UTC
    assert task_commands_module._parse_recorded_at("2026-03-08T10:00:00Z").tzinfo == UTC

    outside = tmp_path.parent / "outside.txt"
    assert task_commands_module._relative_display_path(outside) == str(outside)


def test_task_command_branch_and_rollup_helpers_cover_edge_cases() -> None:
    assert task_commands_module._parse_git_branch_lines("  main\n\n* codex/task-257-x\n") == [
        "main",
        "codex/task-257-x",
    ]
    assert task_commands_module._parse_remote_branch_lines(
        "bad-line\nabc refs/heads/codex/task-257-x\nabc refs/tags/v1\n"
    ) == ["codex/task-257-x"]
    assert task_commands_module._check_rollup_state(None) == "none"
    assert task_commands_module._check_rollup_state([{"status": "IN_PROGRESS"}]) == "pending"
    assert (
        task_commands_module._check_rollup_state([{"status": "COMPLETED", "conclusion": "FAILURE"}])
        == "fail"
    )
    assert (
        task_commands_module._check_rollup_state(
            ["not-a-dict", {"status": "COMPLETED", "conclusion": ""}]
        )
        == "pending"
    )
    assert (
        task_commands_module._check_rollup_state(
            [
                {"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "COMPLETED", "conclusion": "SKIPPED"},
            ]
        )
        == "pass"
    )
    assert task_commands_module._task_id_from_branch_name("codex/task-257-coverage-hard-fail") == (
        "TASK-257"
    )
    assert task_commands_module._task_id_from_branch_name("main") is None


def test_task_command_env_and_output_helpers_cover_validation_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TASK_COMMAND_TEST_INT", raising=False)
    monkeypatch.setenv("REVIEW_TIMEOUT_POLICY", " allow ")
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert task_commands_module._read_int_env("TASK_COMMAND_TEST_INT", 7) == 7
    assert task_commands_module._read_review_timeout_policy_env() == "allow"
    assert task_commands_module._summarize_output_lines(["one", "two"], max_lines=5) == [
        "one",
        "two",
    ]
    assert task_commands_module._ensure_command_available("git") == "/usr/bin/git"

    monkeypatch.setenv("TASK_COMMAND_TEST_INT", "-1")
    with pytest.raises(ValueError, match="must be non-negative"):
        task_commands_module._read_int_env("TASK_COMMAND_TEST_INT", 7)


def test_run_pr_scope_guard_and_review_gate_use_expected_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_subprocess_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return _completed(args)

    monkeypatch.setattr(task_commands_module.subprocess, "run", fake_subprocess_run)

    scope_result = task_commands_module._run_pr_scope_guard(
        branch_name="codex/task-257-coverage-hard-fail",
        pr_title="TASK-257: coverage hard fail",
        pr_body="Primary-Task: TASK-257\n",
    )

    assert scope_result.returncode == 0
    assert captured["args"] == ["./scripts/check_pr_task_scope.sh"]
    assert captured["env"]["PR_BRANCH"] == "codex/task-257-coverage-hard-fail"

    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=30,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=2,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    gate_calls: dict[str, object] = {}
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **kwargs: (
            gate_calls.update({"args": args, "kwargs": kwargs}) or _completed(args)
        ),
    )

    gate_result = task_commands_module._run_review_gate(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert gate_result.returncode == 0
    assert gate_calls["args"][:2] == ["python3", "./scripts/check_pr_review_gate.py"]
    assert gate_calls["args"][-2:] == ["--format", "json"]
    assert gate_calls["kwargs"]["timeout_seconds"] == 37


def test_wait_helpers_cover_timeout_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=0,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh"], returncode=1, stderr="still pending"),
    )

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is False
    assert check_lines == ["still pending"]
    assert check_reason == "timeout"
    assert state_ok is False
    assert state_lines == ["still pending"]


def test_wait_helpers_retry_until_checks_and_state_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=2,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    check_results = iter(
        [
            _completed(["gh", "pr", "checks"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "checks"]),
        ]
    )
    state_results = iter(
        [
            _completed(["gh", "pr", "view"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "view"], stdout="MERGED\n"),
        ]
    )
    sleep_calls: list[int] = []

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "checks"]:
            return next(check_results)
        if args[:3] == ["gh", "pr", "view"]:
            return next(state_results)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(task_commands_module.time, "sleep", sleep_calls.append)

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is True
    assert check_lines == []
    assert check_reason == "pass"
    assert state_ok is True
    assert state_lines == []
    assert sleep_calls == [2, 2]


def test_review_module_compat_ignores_unknown_attribute_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = object()

    monkeypatch.setattr(review_module, "_task317_unknown_attr", marker, raising=False)

    assert review_module._task317_unknown_attr is marker


def test_wait_helpers_retry_without_sleep_when_polling_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    check_results = iter(
        [
            _completed(["gh", "pr", "checks"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "checks"]),
        ]
    )
    state_results = iter(
        [
            _completed(["gh", "pr", "view"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "view"], stdout="MERGED\n"),
        ]
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "checks"]:
            return next(check_results)
        if args[:3] == ["gh", "pr", "view"]:
            return next(state_results)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is True
    assert check_lines == []
    assert check_reason == "pass"
    assert state_ok is True
    assert state_lines == []
