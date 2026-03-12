#!/usr/bin/env python3
"""Wait through the PR review window and fail on actionable current-head bot comments."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

DEFAULT_REVIEWER_LOGIN = "chatgpt-codex-connector[bot]"
DEFAULT_OUTPUT_FORMAT = "text"

EXIT_TIMEOUT_FAILURE = 1
EXIT_ACTIONABLE_FEEDBACK = 2
EXIT_HEAD_CHANGED = 3


class GhError(RuntimeError):
    """Raised when a gh invocation fails."""


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
    actionable_lines: tuple[str, ...] = ()


def _run_gh(*args: str) -> str:
    result = subprocess.run(  # nosec
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise GhError(f"gh {' '.join(args)} failed: {stderr}")
    return result.stdout


def _run_gh_json(*args: str) -> object:
    output = _run_gh(*args).strip()
    if not output:
        return None
    return json.loads(output)


def _run_gh_paginated_json(*args: str) -> object:
    output = _run_gh("api", *args, "--paginate", "--slurp").strip()
    if not output:
        return None
    return json.loads(output)


def _review_context(pr_url: str) -> tuple[str, int, str]:
    repo_data = _run_gh_json("repo", "view", "--json", "nameWithOwner")
    pr_data = _run_gh_json("pr", "view", pr_url, "--json", "number,headRefOid,url")

    if not isinstance(repo_data, dict) or "nameWithOwner" not in repo_data:
        raise GhError("unable to resolve repository name from gh repo view")
    if not isinstance(pr_data, dict) or "number" not in pr_data or "headRefOid" not in pr_data:
        raise GhError("unable to resolve PR number/headRefOid from gh pr view")

    return str(repo_data["nameWithOwner"]), int(pr_data["number"]), str(pr_data["headRefOid"])


def _current_head_oid(pr_url: str) -> str:
    pr_data = _run_gh_json("pr", "view", pr_url, "--json", "headRefOid")
    if not isinstance(pr_data, dict) or "headRefOid" not in pr_data:
        raise GhError("unable to resolve current PR headRefOid from gh pr view")
    head_oid = str(pr_data["headRefOid"]).strip()
    if not head_oid:
        raise GhError("unable to resolve current PR headRefOid from gh pr view")
    return head_oid


def _flatten_paginated_list(payload: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        raise GhError(f"unexpected {label} payload from gh api")

    if not payload:
        return []

    if all(isinstance(entry, dict) for entry in payload):
        return list(payload)

    flattened: list[dict[str, object]] = []
    for page in payload:
        if not isinstance(page, list):
            raise GhError(f"unexpected {label} payload from gh api")
        for entry in page:
            if not isinstance(entry, dict):
                raise GhError(f"unexpected {label} payload from gh api")
            flattened.append(entry)
    return flattened


def _user_login(payload: dict[str, object]) -> str | None:
    user = payload.get("user")
    if not isinstance(user, dict):
        return None
    login = user.get("login")
    return login if isinstance(login, str) else None


def _actionable_review_lines(reviews: list[dict[str, object]]) -> list[str]:
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


def _matching_review_comments(
    *,
    repo: str,
    pr_number: int,
    head_oid: str,
    reviewer_login: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    reviews = _flatten_paginated_list(
        _run_gh_paginated_json(f"repos/{repo}/pulls/{pr_number}/reviews"),
        label="reviews",
    )
    comments = _flatten_paginated_list(
        _run_gh_paginated_json(f"repos/{repo}/pulls/{pr_number}/comments"),
        label="comments",
    )

    matching_reviews = [
        review
        for review in reviews
        if isinstance(review, dict)
        and review.get("commit_id") == head_oid
        and _user_login(review) == reviewer_login
    ]
    actionable_reviews = [
        review
        for review in matching_reviews
        if str(review.get("state") or "").strip().upper() == "CHANGES_REQUESTED"
        or (
            bool(str(review.get("body") or "").strip())
            and str(review.get("state") or "").strip().upper() != "APPROVED"
        )
    ]
    review_ids = {review["id"] for review in matching_reviews if "id" in review}

    matching_comments = [
        comment
        for comment in comments
        if isinstance(comment, dict)
        and comment.get("pull_request_review_id") in review_ids
        and _user_login(comment) == reviewer_login
    ]
    return matching_reviews, matching_comments, actionable_reviews


def _parse_github_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _has_pr_summary_thumbs_up(
    *,
    repo: str,
    pr_number: int,
    reviewer_login: str,
    wait_window_started_at: datetime,
) -> bool:
    reactions = _flatten_paginated_list(
        _run_gh_paginated_json(f"repos/{repo}/issues/{pr_number}/reactions"),
        label="reactions",
    )

    return any(
        isinstance(reaction, dict)
        and reaction.get("content") == "+1"
        and _user_login(reaction) == reviewer_login
        and (created_at := _parse_github_timestamp(reaction.get("created_at"))) is not None
        and created_at >= wait_window_started_at
        for reaction in reactions
    )


def _print_actionable_comments(comments: list[dict[str, object]]) -> None:
    print("review gate failed: actionable current-head review comments found:")
    for comment in comments:
        path = str(comment.get("path") or "<unknown>")
        line = comment.get("line") or comment.get("original_line") or "?"
        url = str(comment.get("html_url") or "")
        body = " ".join(str(comment.get("body") or "").strip().split())
        print(f"- {path}:{line} {url}".rstrip())
        if body:
            print(f"  {body}")


def _emit_outcome(outcome: ReviewGateOutcome, *, output_format: str) -> int:
    if output_format == "json":
        print(json.dumps(asdict(outcome), sort_keys=True))
        if outcome.status == "head_changed":
            return EXIT_HEAD_CHANGED
        if outcome.status == "block":
            return (
                EXIT_ACTIONABLE_FEEDBACK
                if outcome.reason != "timeout_fail"
                else EXIT_TIMEOUT_FAILURE
            )
        return 0

    if outcome.status == "block":
        if outcome.reason == "actionable_comments":
            print("review gate failed: actionable current-head review comments found:")
        elif outcome.reason == "actionable_reviews":
            print("review gate failed: actionable current-head review summary feedback found:")
        else:
            print(outcome.summary)
        for line in outcome.actionable_lines:
            print(line)
    else:
        print(outcome.summary)

    if outcome.status == "head_changed":
        return EXIT_HEAD_CHANGED
    if outcome.status == "block":
        return (
            EXIT_ACTIONABLE_FEEDBACK if outcome.reason != "timeout_fail" else EXIT_TIMEOUT_FAILURE
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-url", required=True, help="PR URL or gh-resolvable PR ref.")
    parser.add_argument(
        "--reviewer-login",
        default=DEFAULT_REVIEWER_LOGIN,
        help=f"GitHub login to wait for (default: {DEFAULT_REVIEWER_LOGIN}).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="How long to wait for a current-head review before timing out; must be positive.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=10,
        help="Polling interval while waiting for review.",
    )
    parser.add_argument(
        "--timeout-policy",
        choices=("allow", "fail"),
        default="allow",
        help="Whether timeout allows merge to continue or fails closed.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default=DEFAULT_OUTPUT_FORMAT,
        help="Output format for the final gate result.",
    )
    args = parser.parse_args(argv)

    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must be non-negative")

    try:
        repo, pr_number, head_oid = _review_context(args.pr_url)
    except GhError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_TIMEOUT_FAILURE
    wait_window_started_at = datetime.now(tz=UTC)
    deadline = time.time() + args.timeout_seconds
    saw_clean_current_head_review = False
    has_pr_summary_thumbs_up = False

    while True:
        try:
            current_head_oid = _current_head_oid(args.pr_url)
            if current_head_oid != head_oid:
                return _emit_outcome(
                    ReviewGateOutcome(
                        status="head_changed",
                        reason="head_changed",
                        reviewer_login=args.reviewer_login,
                        reviewed_head_oid=head_oid,
                        current_head_oid=current_head_oid,
                        clean_current_head_review=saw_clean_current_head_review,
                        summary_thumbs_up=has_pr_summary_thumbs_up,
                        actionable_comment_count=0,
                        actionable_review_count=0,
                        timeout_seconds=args.timeout_seconds,
                        timed_out=False,
                        summary=(
                            "review gate deferred: "
                            f"PR head changed from {head_oid} to {current_head_oid} during the review window."
                        ),
                    ),
                    output_format=args.format,
                )

            matching_reviews, matching_comments, actionable_reviews = _matching_review_comments(
                repo=repo,
                pr_number=pr_number,
                head_oid=head_oid,
                reviewer_login=args.reviewer_login,
            )
            has_pr_summary_thumbs_up = _has_pr_summary_thumbs_up(
                repo=repo,
                pr_number=pr_number,
                reviewer_login=args.reviewer_login,
                wait_window_started_at=wait_window_started_at,
            )
        except GhError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_TIMEOUT_FAILURE

        if matching_comments:
            return _emit_outcome(
                ReviewGateOutcome(
                    status="block",
                    reason="actionable_comments",
                    reviewer_login=args.reviewer_login,
                    reviewed_head_oid=head_oid,
                    current_head_oid=head_oid,
                    clean_current_head_review=False,
                    summary_thumbs_up=has_pr_summary_thumbs_up,
                    actionable_comment_count=len(matching_comments),
                    actionable_review_count=len(actionable_reviews),
                    timeout_seconds=args.timeout_seconds,
                    timed_out=False,
                    summary="review gate failed: actionable current-head review comments found:",
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
                ),
                output_format=args.format,
            )
        if actionable_reviews:
            return _emit_outcome(
                ReviewGateOutcome(
                    status="block",
                    reason="actionable_reviews",
                    reviewer_login=args.reviewer_login,
                    reviewed_head_oid=head_oid,
                    current_head_oid=head_oid,
                    clean_current_head_review=False,
                    summary_thumbs_up=has_pr_summary_thumbs_up,
                    actionable_comment_count=0,
                    actionable_review_count=len(actionable_reviews),
                    timeout_seconds=args.timeout_seconds,
                    timed_out=False,
                    summary="review gate failed: actionable current-head review summary feedback found:",
                    actionable_lines=tuple(_actionable_review_lines(actionable_reviews)),
                ),
                output_format=args.format,
            )
        if any(
            str(review.get("state") or "").strip().upper() == "APPROVED"
            for review in matching_reviews
        ):
            saw_clean_current_head_review = True

        if has_pr_summary_thumbs_up:
            if saw_clean_current_head_review:
                return _emit_outcome(
                    ReviewGateOutcome(
                        status="pass",
                        reason="clean_review_and_thumbs_up",
                        reviewer_login=args.reviewer_login,
                        reviewed_head_oid=head_oid,
                        current_head_oid=head_oid,
                        clean_current_head_review=True,
                        summary_thumbs_up=True,
                        actionable_comment_count=0,
                        actionable_review_count=0,
                        timeout_seconds=args.timeout_seconds,
                        timed_out=False,
                        summary=(
                            "review gate passed early: "
                            f"{args.reviewer_login} approved current head {head_oid} and reacted THUMBS_UP "
                            "on the PR summary during the active review window."
                        ),
                    ),
                    output_format=args.format,
                )
            return _emit_outcome(
                ReviewGateOutcome(
                    status="pass",
                    reason="thumbs_up",
                    reviewer_login=args.reviewer_login,
                    reviewed_head_oid=head_oid,
                    current_head_oid=head_oid,
                    clean_current_head_review=False,
                    summary_thumbs_up=True,
                    actionable_comment_count=0,
                    actionable_review_count=0,
                    timeout_seconds=args.timeout_seconds,
                    timed_out=False,
                    summary=(
                        "review gate passed early: "
                        f"{args.reviewer_login} reacted THUMBS_UP on the PR summary during the active review window."
                    ),
                ),
                output_format=args.format,
            )

        if time.time() >= deadline:
            if saw_clean_current_head_review:
                return _emit_outcome(
                    ReviewGateOutcome(
                        status="pass",
                        reason="clean_review",
                        reviewer_login=args.reviewer_login,
                        reviewed_head_oid=head_oid,
                        current_head_oid=head_oid,
                        clean_current_head_review=True,
                        summary_thumbs_up=False,
                        actionable_comment_count=0,
                        actionable_review_count=0,
                        timeout_seconds=args.timeout_seconds,
                        timed_out=True,
                        summary=(
                            "review gate passed: "
                            f"{args.reviewer_login} approved current head {head_oid} during the "
                            f"{args.timeout_seconds}s wait window."
                        ),
                    ),
                    output_format=args.format,
                )
            message = (
                "review gate timeout: "
                f"no actionable current-head review feedback from {args.reviewer_login} for {head_oid} "
                f"within {args.timeout_seconds}s."
            )
            if args.timeout_policy == "allow":
                return _emit_outcome(
                    ReviewGateOutcome(
                        status="pass",
                        reason="silent_timeout_allow",
                        reviewer_login=args.reviewer_login,
                        reviewed_head_oid=head_oid,
                        current_head_oid=head_oid,
                        clean_current_head_review=False,
                        summary_thumbs_up=False,
                        actionable_comment_count=0,
                        actionable_review_count=0,
                        timeout_seconds=args.timeout_seconds,
                        timed_out=True,
                        summary=f"{message} Continuing due to timeout policy=allow.",
                    ),
                    output_format=args.format,
                )
            return _emit_outcome(
                ReviewGateOutcome(
                    status="block",
                    reason="timeout_fail",
                    reviewer_login=args.reviewer_login,
                    reviewed_head_oid=head_oid,
                    current_head_oid=head_oid,
                    clean_current_head_review=False,
                    summary_thumbs_up=False,
                    actionable_comment_count=0,
                    actionable_review_count=0,
                    timeout_seconds=args.timeout_seconds,
                    timed_out=True,
                    summary=f"{message} Failing due to timeout policy=fail.",
                ),
                output_format=args.format,
            )

        if args.poll_seconds:  # pragma: no branch
            time.sleep(args.poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
