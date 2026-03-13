from __future__ import annotations

import json
from typing import Any

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _maybe_request_fresh_review(*, pr_url: str, config: shared.FinishConfig) -> list[str]:
    pr_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number,headRefOid", "--jq", "."]
    )
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if pr_result.returncode != 0 or repo_result.returncode != 0:
        return ["Failed to determine PR metadata for automatic fresh-review request."]
    try:
        pr_payload = json.loads(pr_result.stdout or "{}")
    except json.JSONDecodeError:
        return ["Failed to parse PR metadata for automatic fresh-review request."]
    if not isinstance(pr_payload, dict):
        return ["Failed to parse PR metadata for automatic fresh-review request."]
    pr_number = pr_payload.get("number")
    head_oid = str(pr_payload.get("headRefOid") or "").strip()
    repo_name = repo_result.stdout.strip()
    if not isinstance(pr_number, int) or "/" not in repo_name or not head_oid:
        return ["Failed to determine PR metadata for automatic fresh-review request."]

    marker = f"<!-- horadus:fresh-review reviewer={config.review_bot_login} head={head_oid} -->"
    request_comment = (
        f"@codex review\n{marker}"
        if config.review_bot_login == "chatgpt-codex-connector[bot]"
        else f"@{config.review_bot_login} review\n{marker}"
    )

    comments_result = shared._run_command(
        [
            config.gh_bin,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo_name}/issues/{pr_number}/comments",
        ]
    )
    if comments_result.returncode != 0:
        return ["Failed to inspect existing fresh-review requests automatically."]
    try:
        comments_payload = json.loads(comments_result.stdout or "[]")
    except json.JSONDecodeError:
        return ["Failed to inspect existing fresh-review requests automatically."]
    existing_comments: list[dict[str, Any]] = []
    if isinstance(comments_payload, list):
        if all(isinstance(entry, dict) for entry in comments_payload):
            existing_comments = [entry for entry in comments_payload if isinstance(entry, dict)]
        else:
            for page in comments_payload:
                if not isinstance(page, list):
                    return ["Failed to inspect existing fresh-review requests automatically."]
                for entry in page:
                    if not isinstance(entry, dict):
                        return ["Failed to inspect existing fresh-review requests automatically."]
                    existing_comments.append(entry)
    else:
        return ["Failed to inspect existing fresh-review requests automatically."]

    if any(marker in str(comment.get("body") or "") for comment in existing_comments):
        return [
            f"Fresh review already requested for `{config.review_bot_login}` on current head {head_oid}."
        ]

    result = shared._run_command(
        [config.gh_bin, "pr", "comment", pr_url, "--body", request_comment]
    )
    if result.returncode != 0:
        return [
            f"Failed to request a fresh review from `{config.review_bot_login}` automatically.",
            *shared._output_lines(result),
        ]
    requested_with = (
        "@codex review"
        if config.review_bot_login == "chatgpt-codex-connector[bot]"
        else f"@{config.review_bot_login} review"
    )
    return [
        f"Requested a fresh review from `{config.review_bot_login}` with `{requested_with}` for head {head_oid}."
    ]


def _fresh_review_request_blocker(
    *, pr_url: str, config: shared.FinishConfig
) -> tuple[list[str], tuple[str, dict[str, object], list[str]] | None]:
    request_lines = _maybe_request_fresh_review(pr_url=pr_url, config=config)
    if request_lines and request_lines[0].startswith("Failed"):
        return (
            [],
            (
                "unable to request a fresh current-head review automatically.",
                {},
                request_lines,
            ),
        )
    return (request_lines, None)


def _needs_pre_review_fresh_review_request(*, pr_url: str, config: shared.FinishConfig) -> bool:
    pr_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number,headRefOid", "--jq", "."]
    )
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if pr_result.returncode != 0 or repo_result.returncode != 0:
        raise ValueError("Unable to determine PR metadata for pre-review refresh state.")
    try:
        pr_payload = json.loads(pr_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse PR metadata for pre-review refresh state.") from exc
    if not isinstance(pr_payload, dict):
        raise ValueError("Unable to parse PR metadata for pre-review refresh state.")
    pr_number = pr_payload.get("number")
    head_oid = str(pr_payload.get("headRefOid") or "").strip()
    repo_name = repo_result.stdout.strip()
    if not isinstance(pr_number, int) or "/" not in repo_name or not head_oid:
        raise ValueError("Unable to determine PR metadata for pre-review refresh state.")

    reviews_result = shared._run_command(
        [
            config.gh_bin,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo_name}/pulls/{pr_number}/reviews",
        ]
    )
    if reviews_result.returncode != 0:
        raise ValueError("Unable to inspect prior reviewer activity for pre-review refresh.")
    try:
        reviews_payload = json.loads(reviews_result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse prior reviewer activity for pre-review refresh.") from exc

    review_entries: list[dict[str, Any]] = []
    if isinstance(reviews_payload, list):
        if all(isinstance(entry, dict) for entry in reviews_payload):
            review_entries = [entry for entry in reviews_payload if isinstance(entry, dict)]
        else:
            for page in reviews_payload:
                if not isinstance(page, list):
                    raise ValueError("Unexpected prior reviewer activity payload.")
                for entry in page:
                    if not isinstance(entry, dict):
                        raise ValueError("Unexpected prior reviewer activity payload.")
                    review_entries.append(entry)
    else:
        raise ValueError("Unexpected prior reviewer activity payload.")

    saw_current_head_review = False
    saw_other_head_review = False
    for review in review_entries:
        user = review.get("user")
        if not isinstance(user, dict):
            continue
        login = str(user.get("login") or "").strip()
        if login != config.review_bot_login:
            continue
        commit_id = str(review.get("commit_id") or "").strip()
        if not commit_id:
            continue
        if commit_id == head_oid:
            saw_current_head_review = True
        else:
            saw_other_head_review = True
    return saw_other_head_review and not saw_current_head_review


__all__ = [
    "_fresh_review_request_blocker",
    "_maybe_request_fresh_review",
    "_needs_pre_review_fresh_review_request",
]
