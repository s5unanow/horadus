from __future__ import annotations

import json
import time

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _required_checks_state(*, pr_url: str, config: shared.FinishConfig) -> tuple[str, list[str]]:
    result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "checks",
            pr_url,
            "--required",
            "--json",
            "bucket,name,link,workflow",
        ]
    )
    lines = shared._output_lines(result)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        if result.returncode == 0:
            return ("error", ["Unable to parse required-check payload from `gh pr checks`."])
        return ("pending", lines)

    if not isinstance(payload, list):
        if result.returncode == 0:
            return ("error", ["Unable to parse required-check payload from `gh pr checks`."])
        return ("pending", lines)

    failed_checks: list[str] = []
    pending_checks: list[str] = []
    saw_checks = False
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        saw_checks = True
        bucket = str(entry.get("bucket") or "").strip().lower()
        name = str(entry.get("name") or "").strip() or "unnamed-check"
        workflow = str(entry.get("workflow") or "").strip()
        label = f"{workflow} / {name}" if workflow and workflow != name else name
        link = str(entry.get("link") or "").strip()
        detail = f"{label}: {bucket}"
        if link:
            detail = f"{detail} ({link})"
        if bucket in {"fail", "cancel"}:
            failed_checks.append(detail)
        elif bucket == "pending":
            pending_checks.append(detail)

    if failed_checks:
        return ("fail", failed_checks)
    if pending_checks:
        return ("pending", pending_checks)
    if result.returncode == 0:
        return ("pass", [])
    if saw_checks:
        return ("pending", lines)
    return ("pending", lines)


def _coerce_wait_for_required_checks_result(
    result: tuple[bool, list[str]] | tuple[bool, list[str], str],
) -> tuple[bool, list[str], str]:
    if len(result) == 2:
        checks_ok, check_lines = result
        return (checks_ok, check_lines, "pass" if checks_ok else "timeout")
    checks_ok, check_lines, reason = result
    return (checks_ok, check_lines, reason)


def _current_required_checks_blocker(
    *, pr_url: str, config: shared.FinishConfig, block_pending: bool = True
) -> tuple[str, list[str]] | None:
    check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
    if check_state == "error":
        return (
            "required PR checks could not be determined on the current head.",
            check_lines,
        )
    if check_state == "fail":
        return (
            "required PR checks are failing on the current head.",
            check_lines,
        )
    if check_state == "pending" and block_pending:
        return (
            "required PR checks are still pending on the current head.",
            check_lines,
        )
    return None


def _wait_for_required_checks(
    *, pr_url: str, config: shared.FinishConfig
) -> tuple[bool, list[str], str]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
        if check_state == "pass":
            return (True, [], "pass")
        if check_state == "fail":
            return (False, check_lines, "fail")
        if check_state == "error":
            return (False, check_lines, "error")
        if time.time() >= deadline:
            return (
                False,
                check_lines or ["`gh pr checks --required` did not report success before timeout."],
                "timeout",
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _wait_for_pr_state(
    *, pr_url: str, expected_state: str, config: shared.FinishConfig
) -> tuple[bool, list[str]]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        result = shared._run_command(
            [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
        )
        if result.returncode == 0 and result.stdout.strip() == expected_state:
            return (True, [])
        if time.time() >= deadline:
            return (
                False,
                shared._output_lines(result)
                or [f"PR did not reach state {expected_state!r} before timeout."],
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


__all__ = [
    "_coerce_wait_for_required_checks_result",
    "_current_required_checks_blocker",
    "_required_checks_state",
    "_wait_for_pr_state",
    "_wait_for_required_checks",
]
