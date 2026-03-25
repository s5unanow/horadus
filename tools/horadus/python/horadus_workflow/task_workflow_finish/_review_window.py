from __future__ import annotations

import subprocess  # nosec B404
import time

from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import _review_gate as gate_module
from . import _review_refresh as refresh_module
from . import _review_threads as threads_module
from . import checks, preconditions

_PRE_REVIEW_STATE_HEADER = "Stale or outdated review state handled before entering the review wait:"


def _append_review_state_section(
    lines: list[str], *, header: str, section_lines: list[str]
) -> None:
    if not section_lines:
        return
    if not lines:
        lines.append(header)
    lines.extend(section_lines)


def _current_head_review_thread_lines(unresolved_review_lines: list[str]) -> list[str]:
    if not unresolved_review_lines:
        return []
    return [
        "Current-head review-thread blockers:",
        *unresolved_review_lines,
    ]


def _append_pre_review_refresh_lines(lines: list[str], section_lines: list[str]) -> None:
    _append_review_state_section(
        lines,
        header=_PRE_REVIEW_STATE_HEADER,
        section_lines=section_lines,
    )


def _pre_review_unresolved_thread_blocker(
    *, needs_fresh_review_request: bool, unresolved_review_lines: list[str]
) -> tuple[str, dict[str, object], list[str]]:
    blocker_lines = _current_head_review_thread_lines(unresolved_review_lines)
    extra_lines = [*blocker_lines]
    if needs_fresh_review_request:
        extra_lines = [
            "GitHub still marks these threads as current after review-state refresh; "
            "inspect whether they are stale older-head threads that now require "
            "manual resolution.",
            *extra_lines,
        ]
    return (
        "PR still has unresolved review threads marked current on GitHub."
        if needs_fresh_review_request
        else "PR is blocked by unresolved review comments.",
        {"manual_thread_inspection_required": needs_fresh_review_request},
        extra_lines,
    )


def _pre_review_refresh_summary_line(*, stale_thread_ids: list[str], timeout_seconds: int) -> str:
    if stale_thread_ids:
        return (
            "Refreshed stale review state for the current head; discarding the previous "
            f"review window and starting a fresh {timeout_seconds}s review window."
        )
    return (
        "Detected reviewer activity on an older head; discarding the previous "
        f"review window and starting a fresh {timeout_seconds}s review window."
    )


def _current_head_finish_blocker(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[str, dict[str, object], list[str]] | None:
    head_alignment_blocker = preconditions._branch_head_alignment_blocker(
        branch_name=context.branch_name,
        pr_url=pr_url,
        config=config,
    )
    if head_alignment_blocker is not None:
        return head_alignment_blocker

    closure_blocker = lifecycle._pre_merge_task_closure_blocker(
        context.task_id,
        branch_name=context.branch_name,
        config=config,
    )
    if closure_blocker is not None:
        return closure_blocker

    checks_blocker = checks._current_required_checks_blocker(
        pr_url=pr_url,
        config=config,
        block_pending=True,
    )
    if checks_blocker is not None:
        blocker_message, blocker_lines = checks_blocker
        return (blocker_message, {}, blocker_lines)
    return None


def _head_changed_review_gate_blocker(
    *,
    context: shared.FinishContext,
    pr_url: str,
    config: shared.FinishConfig,
    review_lines: list[str],
) -> tuple[int, dict[str, object], list[str]] | None:
    blocker = _current_head_finish_blocker(context=context, pr_url=pr_url, config=config)
    if blocker is None:
        return None
    blocker_message, blocker_data, blocker_lines = blocker
    return shared._task_blocked(
        blocker_message,
        next_action=(
            "Ensure the updated PR head is pushed, task-close state is present on that head, "
            "and current-head required checks are green, then re-run `horadus tasks finish`."
        ),
        data={
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            **blocker_data,
        },
        extra_lines=[*review_lines, *blocker_lines],
    )


def _prepare_current_head_review_window(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[list[str], tuple[str, dict[str, object], list[str]] | None]:
    blocker = _current_head_finish_blocker(context=context, pr_url=pr_url, config=config)
    if blocker is not None:
        return ([], blocker)

    try:
        stale_thread_ids = threads_module._outdated_unresolved_review_thread_ids(
            pr_url=pr_url,
            config=config,
        )
        needs_fresh_review_request = bool(stale_thread_ids)
        if not needs_fresh_review_request:
            needs_fresh_review_request = refresh_module._needs_pre_review_fresh_review_request(
                pr_url=pr_url,
                config=config,
            )
    except ValueError as exc:
        return (
            [],
            (
                "unable to determine outdated review thread state on the current head.",
                {},
                [str(exc)],
            ),
        )

    review_refresh_lines: list[str] = []
    if stale_thread_ids:
        resolved_ok, stale_thread_lines = threads_module._resolve_review_threads(
            thread_ids=stale_thread_ids,
            config=config,
        )
        if not resolved_ok:
            return (
                [],
                (
                    "PR still has outdated unresolved review threads that could not be auto-resolved.",
                    {},
                    stale_thread_lines,
                ),
            )
        _append_pre_review_refresh_lines(review_refresh_lines, stale_thread_lines)
    unresolved_review_lines, unresolved_blocker = _unresolved_review_threads_or_blocker(
        pr_url=pr_url,
        config=config,
    )
    if unresolved_blocker is not None:
        return (review_refresh_lines, unresolved_blocker)
    if unresolved_review_lines:
        return (
            review_refresh_lines,
            _pre_review_unresolved_thread_blocker(
                needs_fresh_review_request=needs_fresh_review_request,
                unresolved_review_lines=unresolved_review_lines,
            ),
        )
    if not needs_fresh_review_request:
        return (review_refresh_lines, None)

    request_lines, request_blocker = refresh_module._fresh_review_request_blocker(
        pr_url=pr_url,
        config=config,
    )
    if request_blocker is not None:
        return ([], request_blocker)
    _append_pre_review_refresh_lines(review_refresh_lines, request_lines)
    _append_pre_review_refresh_lines(
        review_refresh_lines,
        [
            _pre_review_refresh_summary_line(
                stale_thread_ids=stale_thread_ids,
                timeout_seconds=config.review_timeout_seconds,
            )
        ],
    )
    return (review_refresh_lines, None)


def _review_gate_wait_line(review_result: shared.ReviewGateResult) -> str:
    waiting_parts = [
        f"reviewer={review_result.reviewer_login}",
        f"head={review_result.current_head_oid}",
    ]
    if review_result.remaining_seconds is not None:
        waiting_parts.append(f"remaining={review_result.remaining_seconds}s")
    if review_result.deadline_at:
        waiting_parts.append(f"deadline={review_result.deadline_at}")
    elif review_result.wait_window_started_at:
        waiting_parts.append(f"started={review_result.wait_window_started_at}")
    else:
        waiting_parts.append(f"timeout={review_result.timeout_seconds}s")
    return f"Waiting for review gate ({', '.join(waiting_parts)})..."


def _review_gate_lines(review_result: shared.ReviewGateResult) -> list[str]:
    lines: list[str] = []
    if review_result.status == "waiting" or review_result.timed_out:
        lines.append(_review_gate_wait_line(review_result))
    if review_result.status != "waiting":
        lines.append(review_result.summary)
    lines.extend(review_result.informational_lines)
    lines.extend(review_result.actionable_lines)
    return lines


def _review_gate_debug_lines(
    *,
    pr_url: str,
    review_result: subprocess.CompletedProcess[str] | None = None,
    review_gate: shared.ReviewGateResult | None = None,
) -> list[str]:
    if not shared._finish_debug_enabled():
        return []
    if review_result is not None:
        return [
            shared._finish_debug_line(
                f"Review gate subprocess exited rc={review_result.returncode} for {pr_url}."
            )
        ]
    assert review_gate is not None
    return [
        shared._finish_debug_line(
            "Parsed review gate result: "
            f"status={review_gate.status}, reason={review_gate.reason}, "
            f"summary_thumbs_up={review_gate.summary_thumbs_up}, "
            f"clean_current_head_review={review_gate.clean_current_head_review}."
        )
    ]


def _review_gate_parse_blocker_message(review_result: subprocess.CompletedProcess[str]) -> str:
    output_lines = shared._output_lines(review_result)
    if any(line.startswith(("Unable to ", "gh ")) for line in output_lines):
        return "review gate could not load current GitHub review state."
    return "review gate returned an unreadable result."


def _run_review_gate_once(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[
    shared.ReviewGateResult | None, list[str], tuple[int, dict[str, object], list[str]] | None
]:
    debug_lines: list[str] = []
    last_error: ValueError | None = None
    last_result: subprocess.CompletedProcess[str] | None = None
    for _attempt in range(2):
        try:
            review_result = gate_module._run_review_gate(
                pr_url=pr_url,
                config=config,
                single_poll=True,
            )
        except shared.CommandTimeoutError as exc:
            return (
                None,
                [],
                shared._task_blocked(
                    "review gate command did not exit after the configured wait window.",
                    next_action=(
                        "Inspect GitHub/Codex review delivery and re-run `horadus tasks finish` "
                        "if the review gate keeps hanging."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[str(exc), *exc.output_lines()],
                ),
            )
        debug_lines.extend(_review_gate_debug_lines(pr_url=pr_url, review_result=review_result))
        try:
            review_gate = gate_module._parse_review_gate_result(review_result)
        except ValueError as exc:
            last_error = exc
            last_result = review_result
            continue
        debug_lines.extend(_review_gate_debug_lines(pr_url=pr_url, review_gate=review_gate))
        return (review_gate, debug_lines, None)
    assert last_error is not None
    assert last_result is not None
    return (
        None,
        debug_lines,
        shared._task_blocked(
            _review_gate_parse_blocker_message(last_result),
            next_action="Resolve the GitHub review-state read failure, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            extra_lines=[str(last_error), *shared._output_lines(last_result)],
        ),
    )


def _unresolved_review_threads_or_blocker(
    *, pr_url: str, config: shared.FinishConfig
) -> tuple[list[str], tuple[str, dict[str, object], list[str]] | None]:
    unresolved_thread_lines = shared._compat_attr(
        "_unresolved_review_thread_lines",
        threads_module,
    )
    try:
        return (
            unresolved_thread_lines(pr_url=pr_url, config=config),
            None,
        )
    except ValueError as exc:
        return (
            [],
            (
                "unable to determine unresolved review thread state on the current head.",
                {},
                [str(exc)],
            ),
        )


def _unresolved_review_thread_blocker(
    *,
    context: shared.FinishContext,
    pr_url: str,
    review_lines: list[str],
    unresolved_review_lines: list[str],
    refreshed_review_state: bool,
) -> tuple[int, dict[str, object], list[str]]:
    manual_inspection = refreshed_review_state
    intro_line = (
        "GitHub still marks these threads as current after review-state refresh; inspect whether "
        "they are stale older-head threads that now require manual resolution."
        if manual_inspection
        else None
    )
    extra_lines = [*review_lines]
    if intro_line is not None:
        extra_lines.append(intro_line)
    extra_lines.extend(_current_head_review_thread_lines(unresolved_review_lines))
    return shared._task_blocked(
        (
            "PR still has unresolved review threads marked current on GitHub."
            if manual_inspection
            else "PR is blocked by unresolved review comments."
        ),
        next_action=(
            "Inspect the unresolved threads in GitHub. Resolve stale threads that no longer "
            "apply or address still-applicable feedback, then re-run `horadus tasks finish`."
            if manual_inspection
            else "Resolve the current-head review threads in GitHub, then re-run `horadus tasks finish`."
        ),
        data={
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            "manual_thread_inspection_required": manual_inspection,
        },
        extra_lines=extra_lines,
    )


def review_gate_data(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[int, dict[str, object], list[str]]:
    refresh_lines, refresh_blocker = _prepare_current_head_review_window(
        context=context, pr_url=pr_url, config=config
    )
    if refresh_blocker is not None:
        blocker_message, blocker_data, blocker_lines = refresh_blocker
        blocker_exit_code = (
            ExitCode.ENVIRONMENT_ERROR
            if blocker_message.startswith(
                (
                    "unable to determine unresolved",
                    "unable to determine outdated",
                    "unable to request a fresh current-head review",
                    "PR still has outdated unresolved review threads",
                )
            )
            else ExitCode.VALIDATION_ERROR
        )
        next_action = (
            "Ensure the current PR head is merge-ready and GitHub review state is readable, "
            "then re-run `horadus tasks finish`."
        )
        if blocker_message.startswith(
            (
                "PR still has unresolved review threads marked current on GitHub.",
                "PR is blocked by unresolved current-head review threads.",
            )
        ):
            next_action = (
                "Inspect the unresolved threads in GitHub. Resolve stale threads that no longer "
                "apply or address still-applicable feedback, then re-run `horadus tasks finish`."
            )
        return shared._task_blocked(
            blocker_message,
            next_action=next_action,
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                **blocker_data,
            },
            exit_code=blocker_exit_code,
            extra_lines=blocker_lines,
        )

    lines = list(refresh_lines)
    refreshed_review_state = bool(refresh_lines)
    while True:
        review_gate, gate_lines, gate_blocker = _run_review_gate_once(
            context=context,
            pr_url=pr_url,
            config=config,
        )
        lines.extend(gate_lines)
        if gate_blocker is not None:
            return gate_blocker
        assert review_gate is not None
        review_lines = _review_gate_lines(review_gate)

        if review_gate.status == "waiting":
            lines.extend(review_lines)
            if config.review_poll_seconds:  # pragma: no branch
                time.sleep(config.review_poll_seconds)
            continue

        if review_gate.status == "head_changed":
            blocker = _head_changed_review_gate_blocker(
                context=context,
                pr_url=pr_url,
                config=config,
                review_lines=review_lines,
            )
            if blocker is not None:
                return blocker
            lines.extend(review_lines)
            request_lines, request_blocker = refresh_module._fresh_review_request_blocker(
                pr_url=pr_url,
                config=config,
            )
            if request_blocker is not None:
                blocker_message, blocker_data, blocker_lines = request_blocker
                return shared._task_blocked(
                    blocker_message,
                    next_action=(
                        "Fix the fresh-review request failure for the current PR head, then "
                        "re-run `horadus tasks finish`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                        **blocker_data,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[*review_lines, *blocker_lines],
                )
            lines.extend(request_lines)
            refreshed_review_state = True
            continue

        if review_gate.status == "block":
            return shared._task_blocked(
                (
                    "review gate timed out before the required current-head review arrived."
                    if review_gate.reason == "timeout_fail"
                    else "review gate did not pass."
                ),
                next_action=(
                    f"Wait for a current-head review from `{config.review_bot_login}`, then "
                    "re-run `horadus tasks finish`."
                    if review_gate.reason == "timeout_fail"
                    else "Address the current-head review feedback, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=ExitCode.VALIDATION_ERROR,
                extra_lines=review_lines,
            )

        lines.extend(review_lines)

        unresolved_review_lines, unresolved_blocker = _unresolved_review_threads_or_blocker(
            pr_url=pr_url,
            config=config,
        )
        if unresolved_blocker is not None:
            blocker_message, blocker_data, blocker_lines = unresolved_blocker
            return shared._task_blocked(
                blocker_message,
                next_action="Resolve the GitHub review-thread query issue, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                    **blocker_data,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=[*review_lines, *blocker_lines],
            )
        if unresolved_review_lines:
            return _unresolved_review_thread_blocker(
                context=context,
                pr_url=pr_url,
                review_lines=review_lines,
                unresolved_review_lines=unresolved_review_lines,
                refreshed_review_state=refreshed_review_state,
            )

        try:
            stale_thread_ids = threads_module._outdated_unresolved_review_thread_ids(
                pr_url=pr_url,
                config=config,
            )
        except ValueError as exc:
            return shared._task_blocked(
                "unable to determine outdated review thread state on the current head.",
                next_action="Resolve the GitHub review-thread query issue, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=[*review_lines, str(exc)],
            )
        if stale_thread_ids:
            resolved_ok, stale_thread_lines = threads_module._resolve_review_threads(
                thread_ids=stale_thread_ids,
                config=config,
            )
            if not resolved_ok:
                return shared._task_blocked(
                    "PR still has outdated unresolved review threads that could not be auto-resolved.",
                    next_action="Re-run `horadus tasks finish`; if the stale-thread blocker persists, inspect GitHub thread state.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[*review_lines, *stale_thread_lines],
                )
            lines.extend(stale_thread_lines)
            refreshed_review_state = True

        post_review_blocker = checks._current_required_checks_blocker(
            pr_url=pr_url,
            config=config,
            block_pending=True,
        )
        if post_review_blocker is not None:
            blocker_message, blocker_lines = post_review_blocker
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    "Ensure the current PR head still has green required checks, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=[*review_lines, *blocker_lines],
            )
        break

    return (ExitCode.OK, {}, lines)


__all__ = [
    "_current_head_finish_blocker",
    "_head_changed_review_gate_blocker",
    "_prepare_current_head_review_window",
    "_review_gate_lines",
]
