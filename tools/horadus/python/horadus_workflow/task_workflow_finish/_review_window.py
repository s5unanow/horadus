from __future__ import annotations

import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import _review_gate as gate_module
from . import _review_refresh as refresh_module
from . import _review_threads as threads_module
from . import checks, preconditions


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

    if not needs_fresh_review_request:
        return ([], None)

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
        review_refresh_lines.extend(stale_thread_lines)
    request_lines, request_blocker = refresh_module._fresh_review_request_blocker(
        pr_url=pr_url,
        config=config,
    )
    if request_blocker is not None:
        return ([], request_blocker)
    review_refresh_lines.extend(request_lines)
    if stale_thread_ids:
        review_refresh_lines.append(
            "Refreshed stale review state for the current head; discarding the previous "
            f"review window and starting a fresh {config.review_timeout_seconds}s review window."
        )
    else:
        review_refresh_lines.append(
            "Detected reviewer activity on an older head; discarding the previous "
            f"review window and starting a fresh {config.review_timeout_seconds}s review window."
        )
    return (review_refresh_lines, None)


def _review_gate_lines(review_result: shared.ReviewGateResult) -> list[str]:
    return [
        review_result.summary,
        *review_result.informational_lines,
        *review_result.actionable_lines,
    ]


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
                    "unable to determine outdated",
                    "unable to request a fresh current-head review",
                    "PR still has outdated unresolved review threads",
                )
            )
            else ExitCode.VALIDATION_ERROR
        )
        return shared._task_blocked(
            blocker_message,
            next_action=(
                "Ensure the current PR head is merge-ready and GitHub review state is readable, "
                "then re-run `horadus tasks finish`."
            ),
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
    while True:
        lines.append(
            "Waiting for review gate "
            f"(reviewer={config.review_bot_login}, timeout={config.review_timeout_seconds}s)..."
        )
        try:
            review_result = gate_module._run_review_gate(pr_url=pr_url, config=config)
        except shared.CommandTimeoutError as exc:
            return shared._task_blocked(
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
            )
        lines.extend(_review_gate_debug_lines(pr_url=pr_url, review_result=review_result))

        try:
            review_gate = gate_module._parse_review_gate_result(review_result)
        except ValueError as exc:
            return shared._task_blocked(
                "review gate returned an unreadable result.",
                next_action="Resolve the review gate script failure, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=[str(exc), *shared._output_lines(review_result)],
            )
        lines.extend(_review_gate_debug_lines(pr_url=pr_url, review_gate=review_gate))
        review_lines = _review_gate_lines(review_gate)

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
                exit_code=review_result.returncode,
                extra_lines=review_lines,
            )

        lines.extend(review_lines)

        try:
            unresolved_review_lines = threads_module._unresolved_review_thread_lines(
                pr_url=pr_url,
                config=config,
            )
        except ValueError as exc:
            return shared._task_blocked(
                "unable to determine unresolved review thread state on the current head.",
                next_action="Resolve the GitHub review-thread query issue, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=[*review_lines, str(exc)],
            )
        if unresolved_review_lines:
            extra_lines = [*review_lines, *unresolved_review_lines]
            if review_gate.timed_out:
                extra_lines.extend(
                    refresh_module._maybe_request_fresh_review(pr_url=pr_url, config=config)
                )
            return shared._task_blocked(
                "PR is blocked by unresolved review comments.",
                next_action=(
                    "Resolve the unresolved review threads in GitHub and wait for a fresh "
                    "current-head review, then re-run `horadus tasks finish`."
                    if review_gate.timed_out
                    else "Resolve the unresolved review threads in GitHub, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=extra_lines,
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
