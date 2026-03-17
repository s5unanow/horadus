#!/usr/bin/env python3
"""Wait through the PR review window and fail on actionable current-head bot comments."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime

from tools.horadus.python.horadus_workflow import (
    pr_review_gate_graphql,
    pr_review_gate_outcomes,
    pr_review_gate_state,
    pr_review_gate_window,
)
from tools.horadus.python.horadus_workflow.review_defaults import (
    DEFAULT_REVIEW_TIMEOUT_SECONDS,
)

DEFAULT_REVIEWER_LOGIN = "chatgpt-codex-connector[bot]"
DEFAULT_OUTPUT_FORMAT = "text"

EXIT_TIMEOUT_FAILURE = 1
EXIT_ACTIONABLE_FEEDBACK = 2
EXIT_HEAD_CHANGED = 3


class GhError(RuntimeError):
    """Raised when a gh invocation fails."""


ReviewGateOutcome = pr_review_gate_outcomes.ReviewGateOutcome
_actionable_review_lines = pr_review_gate_outcomes.actionable_review_lines


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


def _infer_json_context(args: tuple[str, ...] | list[str]) -> str:
    command = tuple(args)
    if command[:2] == ("repo", "view"):
        return "repository metadata"
    if command[:2] == ("pr", "view"):
        return (
            "pull request metadata"
            if any(field in command for field in ("number,headRefOid,url", "number,headRefOid"))
            else "current PR head metadata"
        )
    if len(command) >= 2 and command[0] == "api":
        endpoint = command[1]
        if endpoint.endswith("/reviews"):
            return "review summaries"
        if "/pulls/" in endpoint and endpoint.endswith("/comments"):
            return "review comments"
        if endpoint.endswith("/reactions"):
            return "PR summary reactions"
        if endpoint.endswith("/comments"):
            return "issue comments"
    return "GitHub JSON payload"


def _run_gh_json(*args: str) -> object:
    return _run_gh_json_command(args, context=_infer_json_context(args))


def _run_gh_paginated_json(*args: str) -> object:
    command = ("api", *args, "--paginate", "--slurp")
    return _run_gh_json_command(command, context=_infer_json_context(command))


def _run_gh_json_command(args: tuple[str, ...] | list[str], *, context: str) -> object:
    last_error: GhError | None = None
    for _attempt in range(2):
        try:
            output = _run_gh(*args).strip()
        except GhError as exc:
            last_error = GhError(f"Unable to load {context}: {exc}")
            continue
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            last_error = GhError(f"Unable to parse {context} from gh output: {exc.msg}.")
    assert last_error is not None
    raise last_error


def _is_rate_limit_error(exc: GhError) -> bool:
    return "API rate limit exceeded" in str(exc)


def _run_gh_graphql_json(*, query: str, fields: dict[str, str], context: str) -> object:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in fields.items():
        args.extend(["-F", f"{key}={value}"])
    return _run_gh_json_command(args, context=context)


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


def _review_order_key(review: dict[str, object]) -> tuple[datetime, int]:
    submitted_at = _parse_github_timestamp(review.get("submitted_at"))
    if submitted_at is None:
        submitted_at = datetime.min.replace(tzinfo=UTC)
    review_id = review.get("id")
    order = review_id if isinstance(review_id, int) else -1
    return submitted_at, order


def _matching_review_comments(
    *,
    repo: str,
    pr_number: int,
    head_oid: str,
    reviewer_login: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    try:
        reviews = _flatten_paginated_list(
            _run_gh_paginated_json(f"repos/{repo}/pulls/{pr_number}/reviews"),
            label="reviews",
        )
        comments = _flatten_paginated_list(
            _run_gh_paginated_json(f"repos/{repo}/pulls/{pr_number}/comments"),
            label="comments",
        )
    except GhError as exc:
        if not _is_rate_limit_error(exc):
            raise
        reviews, comments = pr_review_gate_graphql.graphql_reviews_and_comments(
            repo=repo,
            pr_number=pr_number,
            load_graphql=lambda query, fields, context: _run_gh_graphql_json(
                query=query,
                fields=fields,
                context=context,
            ),
            error_factory=GhError,
        )

    matching_reviews = [
        review
        for review in reviews
        if isinstance(review, dict)
        and review.get("commit_id") == head_oid
        and _user_login(review) == reviewer_login
    ]
    latest_matching_review = (
        max(matching_reviews, key=_review_order_key) if matching_reviews else None
    )
    actionable_reviews = (
        [latest_matching_review]
        if latest_matching_review is not None
        and (
            str(latest_matching_review.get("state") or "").strip().upper() == "CHANGES_REQUESTED"
            or (
                bool(str(latest_matching_review.get("body") or "").strip())
                and str(latest_matching_review.get("state") or "").strip().upper() != "APPROVED"
            )
        )
        else []
    )
    review_ids = {review["id"] for review in matching_reviews if "id" in review}

    matching_comments = [
        comment
        for comment in comments
        if isinstance(comment, dict)
        and comment.get("pull_request_review_id") in review_ids
        and _user_login(comment) == reviewer_login
    ]
    return matching_reviews, matching_comments, actionable_reviews


def _matching_issue_comments(
    *,
    repo: str,
    pr_number: int,
    reviewer_login: str,
    wait_window_started_at: datetime,
) -> list[dict[str, object]]:
    try:
        comments = _flatten_paginated_list(
            _run_gh_paginated_json(f"repos/{repo}/issues/{pr_number}/comments"),
            label="issue comments",
        )
    except (GhError, json.JSONDecodeError):
        return []
    return [
        comment
        for comment in comments
        if isinstance(comment, dict)
        and _user_login(comment) == reviewer_login
        and (created_at := _parse_github_timestamp(comment.get("created_at"))) is not None
        and created_at >= wait_window_started_at
        and bool(str(comment.get("body") or "").strip())
    ]


def _fresh_review_marker_for_head(*, reviewer_login: str, head_oid: str) -> str:
    return f"<!-- horadus:fresh-review reviewer={reviewer_login} head={head_oid} -->"


def _latest_current_head_review_request_at(
    *,
    repo: str,
    pr_number: int,
    reviewer_login: str,
    head_oid: str,
) -> datetime | None:
    try:
        comments = _flatten_paginated_list(
            _run_gh_paginated_json(f"repos/{repo}/issues/{pr_number}/comments"),
            label="issue comments",
        )
    except (GhError, json.JSONDecodeError):
        return None

    marker = _fresh_review_marker_for_head(reviewer_login=reviewer_login, head_oid=head_oid)
    timestamps = [
        created_at
        for comment in comments
        if isinstance(comment, dict)
        and marker in str(comment.get("body") or "")
        and (created_at := _parse_github_timestamp(comment.get("created_at"))) is not None
    ]
    return max(timestamps) if timestamps else None


def _parse_github_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _initial_review_loop_state(
    *, pr_url: str, reviewer_login: str, timeout_seconds: int
) -> pr_review_gate_window.ReviewLoopContext:
    repo, pr_number, head_oid = _review_context(pr_url)
    wait_window_started_at = pr_review_gate_state.start_wait_window(
        repo=repo,
        pr_number=pr_number,
        reviewer_login=reviewer_login,
        head_oid=head_oid,
    )
    current_epoch = time.time()
    started_epoch = min(wait_window_started_at.timestamp(), current_epoch)
    if started_epoch != wait_window_started_at.timestamp():
        wait_window_started_at = datetime.fromtimestamp(started_epoch, tz=UTC)
    return pr_review_gate_window.ReviewLoopContext(
        repo=repo,
        pr_number=pr_number,
        head_oid=head_oid,
        wait_window_started_at=wait_window_started_at,
        deadline_epoch=started_epoch + timeout_seconds,
    )


def _has_pr_summary_thumbs_up(
    *,
    repo: str,
    pr_number: int,
    reviewer_login: str,
    head_oid: str,
    wait_window_started_at: datetime,
) -> bool:
    try:
        reactions = _flatten_paginated_list(
            _run_gh_paginated_json(f"repos/{repo}/issues/{pr_number}/reactions"),
            label="reactions",
        )
    except GhError as exc:
        if not _is_rate_limit_error(exc):
            raise
        reactions = pr_review_gate_graphql.graphql_reactions(
            repo=repo,
            pr_number=pr_number,
            load_graphql=lambda query, fields, context: _run_gh_graphql_json(
                query=query,
                fields=fields,
                context=context,
            ),
            error_factory=GhError,
        )
    signal_started_at = _latest_current_head_review_request_at(
        repo=repo,
        pr_number=pr_number,
        reviewer_login=reviewer_login,
        head_oid=head_oid,
    )
    if signal_started_at is None:
        signal_started_at = wait_window_started_at

    return any(
        isinstance(reaction, dict)
        and reaction.get("content") == "+1"
        and _user_login(reaction) == reviewer_login
        and (created_at := _parse_github_timestamp(reaction.get("created_at"))) is not None
        and created_at >= signal_started_at
        for reaction in reactions
    )


def _informational_issue_comment_lines(comments: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for comment in comments:
        url = str(comment.get("html_url") or "").strip()
        header = "- reviewer issue comment"
        if url:
            header = f"{header} {url}"
        lines.append(header)
        body = " ".join(str(comment.get("body") or "").strip().split())
        if body:
            lines.append(f"  {body}")
    return lines


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

    if outcome.status == "waiting":
        print(outcome.summary)
        for line in outcome.informational_lines:
            print(line)
        return 0

    if outcome.status == "block":
        if outcome.reason == "actionable_comments":
            print("review gate failed: actionable current-head review comments found:")
        elif outcome.reason == "actionable_reviews":
            print("review gate failed: actionable current-head review summary feedback found:")
        else:
            print(outcome.summary)
        for line in (*outcome.informational_lines, *outcome.actionable_lines):
            print(line)
    else:
        print(outcome.summary)
        for line in outcome.informational_lines:
            print(line)

    if outcome.status == "head_changed":
        return EXIT_HEAD_CHANGED
    if outcome.status == "block":
        return (
            EXIT_ACTIONABLE_FEEDBACK if outcome.reason != "timeout_fail" else EXIT_TIMEOUT_FAILURE
        )
    return 0


def _matching_review_state(
    *, args: argparse.Namespace, loop_context: pr_review_gate_window.ReviewLoopContext
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    tuple[str, ...],
    bool,
    bool,
]:
    matching_reviews, matching_comments, actionable_reviews = _matching_review_comments(
        repo=loop_context.repo,
        pr_number=loop_context.pr_number,
        head_oid=loop_context.head_oid,
        reviewer_login=args.reviewer_login,
    )
    matching_issue_comments = _matching_issue_comments(
        repo=loop_context.repo,
        pr_number=loop_context.pr_number,
        reviewer_login=args.reviewer_login,
        wait_window_started_at=loop_context.wait_window_started_at,
    )
    has_pr_summary_thumbs_up = _has_pr_summary_thumbs_up(
        repo=loop_context.repo,
        pr_number=loop_context.pr_number,
        reviewer_login=args.reviewer_login,
        head_oid=loop_context.head_oid,
        wait_window_started_at=loop_context.wait_window_started_at,
    )
    informational_lines = tuple(_informational_issue_comment_lines(matching_issue_comments))
    saw_clean_current_head_review = any(
        str(review.get("state") or "").strip().upper() == "APPROVED" for review in matching_reviews
    )
    return (
        matching_reviews,
        matching_comments,
        actionable_reviews,
        informational_lines,
        has_pr_summary_thumbs_up,
        saw_clean_current_head_review,
    )


def _review_gate_once(
    *, args: argparse.Namespace, loop_context: pr_review_gate_window.ReviewLoopContext
) -> ReviewGateOutcome:
    current_head_oid = _current_head_oid(args.pr_url)
    if current_head_oid != loop_context.head_oid:
        return pr_review_gate_outcomes.head_changed_outcome(
            reviewer_login=args.reviewer_login,
            loop_context=loop_context,
            current_head_oid=current_head_oid,
            timeout_seconds=args.timeout_seconds,
        )
    current_time = time.time()
    (
        _matching_reviews,
        matching_comments,
        actionable_reviews,
        informational_lines,
        has_pr_summary_thumbs_up,
        saw_clean_current_head_review,
    ) = _matching_review_state(args=args, loop_context=loop_context)
    feedback_outcome = pr_review_gate_outcomes.feedback_outcome(
        reviewer_login=args.reviewer_login,
        loop_context=loop_context,
        timeout_seconds=args.timeout_seconds,
        matching_comments=matching_comments,
        actionable_reviews=actionable_reviews,
        informational_lines=informational_lines,
        has_pr_summary_thumbs_up=has_pr_summary_thumbs_up,
    )
    if feedback_outcome is not None:
        return feedback_outcome
    return pr_review_gate_outcomes.approval_or_timeout_outcome(
        reviewer_login=args.reviewer_login,
        loop_context=loop_context,
        timeout_seconds=args.timeout_seconds,
        timeout_policy=args.timeout_policy,
        informational_lines=informational_lines,
        has_pr_summary_thumbs_up=has_pr_summary_thumbs_up,
        saw_clean_current_head_review=saw_clean_current_head_review,
        current_time=current_time,
    )


def _validate_main_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must be non-negative")


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
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
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
    parser.add_argument(
        "--single-poll",
        action="store_true",
        help="Evaluate the current review state once and return a waiting status when the review window is still open.",
    )
    args = parser.parse_args(argv)
    _validate_main_args(parser, args)

    try:
        loop_context = _initial_review_loop_state(
            pr_url=args.pr_url,
            reviewer_login=args.reviewer_login,
            timeout_seconds=args.timeout_seconds,
        )
        while True:
            outcome = _review_gate_once(args=args, loop_context=loop_context)
            if args.single_poll or outcome.status != "waiting":
                return _emit_outcome(outcome, output_format=args.format)
            if args.format == "text":
                _emit_outcome(outcome, output_format=args.format)
            if args.poll_seconds:  # pragma: no branch
                time.sleep(args.poll_seconds)
    except GhError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_TIMEOUT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
