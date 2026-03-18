from __future__ import annotations

import time
from dataclasses import dataclass

from tools.horadus.python.horadus_workflow import pr_review_gate_window


@dataclass(frozen=True, slots=True)
class ReviewGateOutcome:
    status: str
    reason: str
    reviewer_login: str
    reviewed_head_oid: str
    current_head_oid: str
    clean_current_head_review: bool
    summary_thumbs_up: bool
    actionable_comment_count: int
    actionable_review_count: int
    timeout_seconds: int
    timed_out: bool
    summary: str
    informational_lines: tuple[str, ...] = ()
    actionable_lines: tuple[str, ...] = ()
    wait_window_started_at: str | None = None
    deadline_at: str | None = None
    remaining_seconds: int | None = None


def actionable_review_lines(reviews: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for review in reviews:
        state = str(review.get("state") or "").strip() or "UNKNOWN"
        url = str(review.get("html_url") or "").strip()
        body = " ".join(str(review.get("body") or "").strip().split())
        header = f"- {state}"
        if url:
            header = f"{header} {url}"
        lines.append(header)
        if body:
            lines.append(f"  {body}")
    return lines


def waiting_outcome(
    *,
    reviewer_login: str,
    loop_context: pr_review_gate_window.ReviewLoopContext,
    timeout_seconds: int,
    clean_current_head_review: bool,
    summary_thumbs_up: bool,
    informational_lines: tuple[str, ...],
) -> ReviewGateOutcome:
    window_fields = pr_review_gate_window.review_window_fields(loop_context)
    return ReviewGateOutcome(
        status="waiting",
        reason="waiting",
        reviewer_login=reviewer_login,
        reviewed_head_oid=loop_context.head_oid,
        current_head_oid=loop_context.head_oid,
        clean_current_head_review=clean_current_head_review,
        summary_thumbs_up=summary_thumbs_up,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=timeout_seconds,
        timed_out=False,
        summary=(
            "Waiting for review gate "
            f"(reviewer={reviewer_login}, head={loop_context.head_oid}, "
            f"remaining={window_fields['remaining_seconds']}s, "
            f"deadline={window_fields['deadline_at']})..."
        ),
        informational_lines=informational_lines,
        wait_window_started_at=window_fields["wait_window_started_at"],
        deadline_at=window_fields["deadline_at"],
        remaining_seconds=window_fields["remaining_seconds"],
    )


def head_changed_outcome(
    *,
    reviewer_login: str,
    loop_context: pr_review_gate_window.ReviewLoopContext,
    current_head_oid: str,
    timeout_seconds: int,
) -> ReviewGateOutcome:
    window_fields = pr_review_gate_window.review_window_fields(loop_context)
    return ReviewGateOutcome(
        status="head_changed",
        reason="head_changed",
        reviewer_login=reviewer_login,
        reviewed_head_oid=loop_context.head_oid,
        current_head_oid=current_head_oid,
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=timeout_seconds,
        timed_out=False,
        summary=(
            "review gate deferred: "
            f"PR head changed from {loop_context.head_oid} to {current_head_oid} during the review window."
        ),
        wait_window_started_at=window_fields["wait_window_started_at"],
        deadline_at=window_fields["deadline_at"],
        remaining_seconds=window_fields["remaining_seconds"],
    )


def feedback_outcome(
    *,
    reviewer_login: str,
    loop_context: pr_review_gate_window.ReviewLoopContext,
    timeout_seconds: int,
    matching_comments: list[dict[str, object]],
    actionable_reviews: list[dict[str, object]],
    informational_lines: tuple[str, ...],
    has_pr_summary_thumbs_up: bool,
) -> ReviewGateOutcome | None:
    window_fields = pr_review_gate_window.review_window_fields(loop_context)
    if matching_comments:
        return ReviewGateOutcome(
            status="block",
            reason="actionable_comments",
            reviewer_login=reviewer_login,
            reviewed_head_oid=loop_context.head_oid,
            current_head_oid=loop_context.head_oid,
            clean_current_head_review=False,
            summary_thumbs_up=has_pr_summary_thumbs_up,
            actionable_comment_count=len(matching_comments),
            actionable_review_count=len(actionable_reviews),
            timeout_seconds=timeout_seconds,
            timed_out=False,
            summary="review gate failed: actionable current-head review comments found:",
            informational_lines=informational_lines,
            actionable_lines=tuple(
                line
                for comment in matching_comments
                for line in (
                    f"- {comment.get('path') or '<unknown>'!s}:{comment.get('line') or comment.get('original_line') or '?'} "
                    f"{str(comment.get('html_url') or '').strip()}".rstrip(),
                    *(
                        [f"  {' '.join(str(comment.get('body') or '').strip().split())}"]
                        if str(comment.get("body") or "").strip()
                        else []
                    ),
                )
            ),
            wait_window_started_at=window_fields["wait_window_started_at"],
            deadline_at=window_fields["deadline_at"],
            remaining_seconds=window_fields["remaining_seconds"],
        )
    if not actionable_reviews:
        return None
    return ReviewGateOutcome(
        status="block",
        reason="actionable_reviews",
        reviewer_login=reviewer_login,
        reviewed_head_oid=loop_context.head_oid,
        current_head_oid=loop_context.head_oid,
        clean_current_head_review=False,
        summary_thumbs_up=has_pr_summary_thumbs_up,
        actionable_comment_count=0,
        actionable_review_count=len(actionable_reviews),
        timeout_seconds=timeout_seconds,
        timed_out=False,
        summary="review gate failed: actionable current-head review summary feedback found:",
        informational_lines=informational_lines,
        actionable_lines=tuple(actionable_review_lines(actionable_reviews)),
        wait_window_started_at=window_fields["wait_window_started_at"],
        deadline_at=window_fields["deadline_at"],
        remaining_seconds=window_fields["remaining_seconds"],
    )


def approval_or_timeout_outcome(
    *,
    reviewer_login: str,
    loop_context: pr_review_gate_window.ReviewLoopContext,
    timeout_seconds: int,
    timeout_policy: str,
    informational_lines: tuple[str, ...],
    has_pr_summary_thumbs_up: bool,
    saw_clean_current_head_review: bool,
    current_time: float | None = None,
) -> ReviewGateOutcome:
    window_fields = pr_review_gate_window.review_window_fields(loop_context)
    if has_pr_summary_thumbs_up:
        summary = (
            "review gate passed early: "
            f"{reviewer_login} approved current head {loop_context.head_oid} and reacted THUMBS_UP "
            "on the PR summary during the active review window."
            if saw_clean_current_head_review
            else "review gate passed early: "
            f"{reviewer_login} reacted THUMBS_UP on the PR summary during the active review window."
        )
        return ReviewGateOutcome(
            status="pass",
            reason="clean_review_and_thumbs_up" if saw_clean_current_head_review else "thumbs_up",
            reviewer_login=reviewer_login,
            reviewed_head_oid=loop_context.head_oid,
            current_head_oid=loop_context.head_oid,
            clean_current_head_review=saw_clean_current_head_review,
            summary_thumbs_up=True,
            actionable_comment_count=0,
            actionable_review_count=0,
            timeout_seconds=timeout_seconds,
            timed_out=False,
            summary=summary,
            informational_lines=informational_lines,
            wait_window_started_at=window_fields["wait_window_started_at"],
            deadline_at=window_fields["deadline_at"],
            remaining_seconds=window_fields["remaining_seconds"],
        )
    now = time.time() if current_time is None else current_time
    if now < loop_context.deadline_epoch:
        return waiting_outcome(
            reviewer_login=reviewer_login,
            loop_context=loop_context,
            timeout_seconds=timeout_seconds,
            clean_current_head_review=saw_clean_current_head_review,
            summary_thumbs_up=has_pr_summary_thumbs_up,
            informational_lines=informational_lines,
        )
    if saw_clean_current_head_review:
        return ReviewGateOutcome(
            status="pass",
            reason="clean_review",
            reviewer_login=reviewer_login,
            reviewed_head_oid=loop_context.head_oid,
            current_head_oid=loop_context.head_oid,
            clean_current_head_review=True,
            summary_thumbs_up=False,
            actionable_comment_count=0,
            actionable_review_count=0,
            timeout_seconds=timeout_seconds,
            timed_out=True,
            summary=(
                "review gate passed: "
                f"{reviewer_login} approved current head {loop_context.head_oid} during the "
                f"{timeout_seconds}s wait window."
            ),
            informational_lines=informational_lines,
            wait_window_started_at=window_fields["wait_window_started_at"],
            deadline_at=window_fields["deadline_at"],
            remaining_seconds=window_fields["remaining_seconds"],
        )
    message = (
        "review gate timeout: "
        f"no actionable current-head review feedback from {reviewer_login} for "
        f"{loop_context.head_oid} within {timeout_seconds}s."
    )
    return ReviewGateOutcome(
        status="pass" if timeout_policy == "allow" else "block",
        reason="silent_timeout_allow" if timeout_policy == "allow" else "timeout_fail",
        reviewer_login=reviewer_login,
        reviewed_head_oid=loop_context.head_oid,
        current_head_oid=loop_context.head_oid,
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=timeout_seconds,
        timed_out=True,
        summary=(
            f"{message} Continuing due to timeout policy=allow."
            if timeout_policy == "allow"
            else f"{message} Failing due to timeout policy=fail."
        ),
        informational_lines=informational_lines,
        wait_window_started_at=window_fields["wait_window_started_at"],
        deadline_at=window_fields["deadline_at"],
        remaining_seconds=window_fields["remaining_seconds"],
    )


__all__ = [
    "ReviewGateOutcome",
    "actionable_review_lines",
    "approval_or_timeout_outcome",
    "feedback_outcome",
    "head_changed_outcome",
    "waiting_outcome",
]
