#!/usr/bin/env python3
"""Wait through the PR review window and fail on actionable current-head bot comments."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import time
from datetime import UTC, datetime

DEFAULT_REVIEWER_LOGIN = "chatgpt-codex-connector[bot]"


class GhError(RuntimeError):
    """Raised when a gh invocation fails."""


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


def _review_context(pr_url: str) -> tuple[str, int, str]:
    repo_data = _run_gh_json("repo", "view", "--json", "nameWithOwner")
    pr_data = _run_gh_json("pr", "view", pr_url, "--json", "number,headRefOid,url")

    if not isinstance(repo_data, dict) or "nameWithOwner" not in repo_data:
        raise GhError("unable to resolve repository name from gh repo view")
    if not isinstance(pr_data, dict) or "number" not in pr_data or "headRefOid" not in pr_data:
        raise GhError("unable to resolve PR number/headRefOid from gh pr view")

    return str(repo_data["nameWithOwner"]), int(pr_data["number"]), str(pr_data["headRefOid"])


def _matching_review_comments(
    *,
    repo: str,
    pr_number: int,
    head_oid: str,
    reviewer_login: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    reviews = _run_gh_json("api", f"repos/{repo}/pulls/{pr_number}/reviews")
    comments = _run_gh_json("api", f"repos/{repo}/pulls/{pr_number}/comments")

    if not isinstance(reviews, list):
        raise GhError("unexpected reviews payload from gh api")
    if not isinstance(comments, list):
        raise GhError("unexpected comments payload from gh api")

    matching_reviews = [
        review
        for review in reviews
        if isinstance(review, dict)
        and review.get("commit_id") == head_oid
        and isinstance(review.get("user"), dict)
        and review["user"].get("login") == reviewer_login
    ]
    review_ids = {review["id"] for review in matching_reviews if "id" in review}

    matching_comments = [
        comment
        for comment in comments
        if isinstance(comment, dict)
        and comment.get("pull_request_review_id") in review_ids
        and isinstance(comment.get("user"), dict)
        and comment["user"].get("login") == reviewer_login
    ]
    return matching_reviews, matching_comments


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
    reactions = _run_gh_json("api", f"repos/{repo}/issues/{pr_number}/reactions")
    if not isinstance(reactions, list):
        raise GhError("unexpected reactions payload from gh api")

    return any(
        isinstance(reaction, dict)
        and reaction.get("content") == "+1"
        and isinstance(reaction.get("user"), dict)
        and reaction["user"].get("login") == reviewer_login
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
    args = parser.parse_args(argv)

    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must be non-negative")

    repo, pr_number, head_oid = _review_context(args.pr_url)
    wait_window_started_at = datetime.now(tz=UTC)
    deadline = time.time() + args.timeout_seconds
    saw_clean_current_head_review = False
    has_pr_summary_thumbs_up = False

    while True:
        matching_reviews, matching_comments = _matching_review_comments(
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
        if matching_comments:
            _print_actionable_comments(matching_comments)
            return 2
        if matching_reviews:
            saw_clean_current_head_review = True

        if time.time() >= deadline:
            if saw_clean_current_head_review and has_pr_summary_thumbs_up:
                print(
                    "review gate passed: "
                    f"{args.reviewer_login} reviewed current head {head_oid} with no inline comments "
                    f"and reacted THUMBS_UP on the PR summary during the {args.timeout_seconds}s "
                    "wait window."
                )
                return 0
            if saw_clean_current_head_review:
                print(
                    "review gate passed: "
                    f"{args.reviewer_login} reviewed current head {head_oid} with no inline comments "
                    f"during the {args.timeout_seconds}s wait window."
                )
                return 0
            if has_pr_summary_thumbs_up:
                print(
                    "review gate passed: "
                    f"{args.reviewer_login} reacted THUMBS_UP on the PR summary during the "
                    f"{args.timeout_seconds}s wait window."
                )
                return 0
            message = (
                "review gate timeout: "
                f"no actionable current-head review feedback from {args.reviewer_login} for {head_oid} "
                f"within {args.timeout_seconds}s."
            )
            if args.timeout_policy == "allow":
                print(f"{message} Continuing due to timeout policy=allow.")
                return 0
            print(f"{message} Failing due to timeout policy=fail.")
            return 1

        if args.poll_seconds:  # pragma: no branch
            time.sleep(args.poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
