from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_workflow.task_workflow_finish._review_gate as review_gate_module
import tools.horadus.python.horadus_workflow.task_workflow_finish._review_window as review_window_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def _context() -> review_window_module.shared.FinishContext:
    return review_window_module.shared.FinishContext(
        branch_name="codex/task-348-finish-review-window-recovery",
        branch_task_id="TASK-348",
        task_id="TASK-348",
    )


def _config(*, review_poll_seconds: int = 1) -> review_window_module.shared.FinishConfig:
    return review_window_module.shared.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=review_poll_seconds,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )


def _review_gate_result(
    *,
    status: str,
    reason: str,
    summary: str,
    wait_window_started_at: str | None = None,
    deadline_at: str | None = None,
    remaining_seconds: int | None = None,
) -> review_window_module.shared.ReviewGateResult:
    return review_window_module.shared.ReviewGateResult(
        status=status,
        reason=reason,
        reviewer_login="chatgpt-codex-connector[bot]",
        reviewed_head_oid="head-sha-348",
        current_head_oid="head-sha-348",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=5,
        timed_out=reason in {"silent_timeout_allow", "clean_review"},
        summary=summary,
        informational_lines=[],
        actionable_lines=[],
        wait_window_started_at=wait_window_started_at,
        deadline_at=deadline_at,
        remaining_seconds=remaining_seconds,
    )


def test_review_gate_parse_blocker_message_falls_back_to_unreadable_result() -> None:
    result = _completed(["review"], stderr="plain failure")
    assert (
        review_window_module._review_gate_parse_blocker_message(result)
        == "review gate returned an unreadable result."
    )
    github_result = _completed(["review"], stderr="Unable to load PR review threads.")
    assert (
        review_window_module._review_gate_parse_blocker_message(github_result)
        == "review gate could not load current GitHub review state."
    )


def test_unresolved_review_thread_blocker_marks_manual_inspection() -> None:
    exit_code, data, lines = review_window_module._unresolved_review_thread_blocker(
        context=_context(),
        pr_url="https://example.invalid/pr/348",
        review_lines=["review gate timeout"],
        unresolved_review_lines=["- path.py:1 https://example.invalid/comment/1"],
        refreshed_review_state=True,
    )

    assert exit_code == review_window_module.ExitCode.VALIDATION_ERROR
    assert data["manual_thread_inspection_required"] is True
    assert (
        lines[0]
        == "Task finish blocked: PR still has unresolved review threads marked current on GitHub."
    )
    assert "Current-head review-thread blockers:" in lines
    assert any("manual resolution" in line for line in lines)


def test_review_gate_data_sleeps_between_waiting_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        [
            (
                _review_gate_result(
                    status="waiting",
                    reason="waiting",
                    summary="Waiting for review gate ...",
                    wait_window_started_at="2026-03-17T12:29:56+00:00",
                    deadline_at="2026-03-17T12:30:00+00:00",
                    remaining_seconds=4,
                ),
                [],
                None,
            ),
            (
                _review_gate_result(
                    status="pass",
                    reason="silent_timeout_allow",
                    summary="review gate timeout: no actionable current-head review feedback.",
                ),
                [],
                None,
            ),
        ]
    )
    sleep_calls: list[int] = []
    monkeypatch.setattr(
        review_window_module,
        "_prepare_current_head_review_window",
        lambda **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        review_window_module, "_run_review_gate_once", lambda **_kwargs: next(results)
    )
    monkeypatch.setattr(
        review_window_module,
        "_unresolved_review_threads_or_blocker",
        lambda **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        review_window_module.threads_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        review_window_module.checks,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        review_window_module.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    exit_code, _data, lines = review_window_module.review_gate_data(
        context=_context(),
        pr_url="https://example.invalid/pr/348",
        config=_config(review_poll_seconds=1),
    )

    assert exit_code == review_window_module.ExitCode.OK
    assert sleep_calls == [1]
    assert (
        "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], "
        "head=head-sha-348, remaining=4s, deadline=2026-03-17T12:30:00+00:00)..."
    ) in lines
    assert not any(
        line == "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], timeout=5s)..."
        for line in lines
    )


def test_review_gate_data_returns_environment_blocker_when_thread_state_is_unreadable_after_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_window_module,
        "_prepare_current_head_review_window",
        lambda **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        review_window_module,
        "_run_review_gate_once",
        lambda **_kwargs: (
            _review_gate_result(
                status="pass", reason="silent_timeout_allow", summary="review gate timeout"
            ),
            [],
            None,
        ),
    )
    monkeypatch.setattr(
        review_window_module,
        "_unresolved_review_threads_or_blocker",
        lambda **_kwargs: (
            [],
            (
                "unable to determine unresolved review thread state on the current head.",
                {},
                ["graphql failed"],
            ),
        ),
    )

    exit_code, _data, lines = review_window_module.review_gate_data(
        context=_context(),
        pr_url="https://example.invalid/pr/348",
        config=_config(review_poll_seconds=0),
    )

    assert exit_code == review_window_module.ExitCode.ENVIRONMENT_ERROR
    assert (
        lines[0]
        == "Task finish blocked: unable to determine unresolved review thread state on the current head."
    )
    assert lines[-1] == "graphql failed"


def test_review_gate_lines_uses_started_at_when_deadline_is_unavailable() -> None:
    lines = review_window_module._review_gate_lines(
        _review_gate_result(
            status="waiting",
            reason="waiting",
            summary="Waiting for review gate ...",
            wait_window_started_at="2026-03-17T12:29:56+00:00",
            remaining_seconds=4,
        )
    )

    assert lines == [
        "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], "
        "head=head-sha-348, remaining=4s, started=2026-03-17T12:29:56+00:00)..."
    ]


def test_review_gate_lines_include_timeout_wait_recap_for_timed_out_result() -> None:
    lines = review_window_module._review_gate_lines(
        _review_gate_result(
            status="pass",
            reason="silent_timeout_allow",
            summary="review gate timeout: no actionable current-head review feedback.",
        )
    )

    assert lines == [
        "Waiting for review gate (reviewer=chatgpt-codex-connector[bot], "
        "head=head-sha-348, timeout=5s)...",
        "review gate timeout: no actionable current-head review feedback.",
    ]


def test_review_gate_data_blocks_on_unresolved_threads_after_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_window_module,
        "_prepare_current_head_review_window",
        lambda **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        review_window_module,
        "_run_review_gate_once",
        lambda **_kwargs: (
            _review_gate_result(
                status="pass", reason="silent_timeout_allow", summary="review gate timeout"
            ),
            [],
            None,
        ),
    )
    monkeypatch.setattr(
        review_window_module,
        "_unresolved_review_threads_or_blocker",
        lambda **_kwargs: (["- path.py:1 https://example.invalid/comment/1"], None),
    )

    exit_code, _data, lines = review_window_module.review_gate_data(
        context=_context(),
        pr_url="https://example.invalid/pr/348",
        config=_config(review_poll_seconds=0),
    )

    assert exit_code == review_window_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert "Current-head review-thread blockers:" in lines


def test_run_review_gate_single_poll_appends_flag_and_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_command_with_timeout(
        args: list[str], *, timeout_seconds: float, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["timeout_seconds"] = timeout_seconds
        return _completed(args, stdout='{"status":"waiting"}')

    monkeypatch.setattr(
        review_gate_module.shared,
        "_run_command_with_timeout",
        fake_run_command_with_timeout,
    )

    review_gate_module._run_review_gate(
        pr_url="https://example.invalid/pr/348",
        config=_config(review_poll_seconds=1),
        single_poll=True,
    )

    assert "--single-poll" in captured["args"]
    assert captured["timeout_seconds"] == 120
