from __future__ import annotations

import json
import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _run_review_gate(
    *, pr_url: str, config: shared.FinishConfig, single_poll: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [
        config.python_bin,
        "./scripts/check_pr_review_gate.py",
        "--pr-url",
        pr_url,
        "--reviewer-login",
        config.review_bot_login,
        "--timeout-seconds",
        str(config.review_timeout_seconds),
        "--poll-seconds",
        str(config.review_poll_seconds),
        "--timeout-policy",
        config.review_timeout_policy,
        "--format",
        "json",
    ]
    if single_poll:
        command.append("--single-poll")
    timeout_seconds = (
        120
        if single_poll
        else config.review_timeout_seconds
        + max(config.review_poll_seconds, 1)
        + shared.DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS
    )
    return shared._run_command_with_timeout(
        command,
        timeout_seconds=timeout_seconds,
    )


def _parse_review_gate_result(result: subprocess.CompletedProcess[str]) -> shared.ReviewGateResult:
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unable to parse review gate payload: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Unable to parse review gate payload: expected a JSON object.")

    actionable_lines = payload.get("actionable_lines", [])
    if not isinstance(actionable_lines, list) or not all(
        isinstance(line, str) for line in actionable_lines
    ):
        raise ValueError(
            "Unable to parse review gate payload: actionable_lines must be a string list."
        )
    informational_lines = payload.get("informational_lines", [])
    if not isinstance(informational_lines, list) or not all(
        isinstance(line, str) for line in informational_lines
    ):
        raise ValueError(
            "Unable to parse review gate payload: informational_lines must be a string list."
        )

    required_str_fields = (
        "status",
        "reason",
        "reviewer_login",
        "reviewed_head_oid",
        "current_head_oid",
        "summary",
    )
    for field_name in required_str_fields:
        if not isinstance(payload.get(field_name), str) or not str(payload[field_name]).strip():
            raise ValueError(f"Unable to parse review gate payload: missing {field_name}.")

    try:
        return shared.ReviewGateResult(
            status=str(payload["status"]).strip(),
            reason=str(payload["reason"]).strip(),
            reviewer_login=str(payload["reviewer_login"]).strip(),
            reviewed_head_oid=str(payload["reviewed_head_oid"]).strip(),
            current_head_oid=str(payload["current_head_oid"]).strip(),
            clean_current_head_review=bool(payload.get("clean_current_head_review")),
            summary_thumbs_up=bool(payload.get("summary_thumbs_up")),
            actionable_comment_count=int(payload.get("actionable_comment_count", 0)),
            actionable_review_count=int(payload.get("actionable_review_count", 0)),
            timeout_seconds=int(payload.get("timeout_seconds", 0)),
            timed_out=bool(payload.get("timed_out")),
            summary=str(payload["summary"]).strip(),
            informational_lines=[str(line) for line in informational_lines],
            actionable_lines=[str(line) for line in actionable_lines],
            wait_window_started_at=(
                str(payload["wait_window_started_at"]).strip()
                if isinstance(payload.get("wait_window_started_at"), str)
                and str(payload["wait_window_started_at"]).strip()
                else None
            ),
            deadline_at=(
                str(payload["deadline_at"]).strip()
                if isinstance(payload.get("deadline_at"), str)
                and str(payload["deadline_at"]).strip()
                else None
            ),
            remaining_seconds=(
                int(payload["remaining_seconds"])
                if payload.get("remaining_seconds") is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Unable to parse review gate payload: invalid field types.") from exc


__all__ = [
    "_parse_review_gate_result",
    "_run_review_gate",
]
