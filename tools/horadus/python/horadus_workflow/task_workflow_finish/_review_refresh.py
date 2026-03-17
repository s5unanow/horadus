from __future__ import annotations

import json
from typing import Any

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared

PRE_REVIEW_GRAPHQL_REVIEWS_QUERY = (
    "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
    "repository(owner:$owner,name:$repo){"
    "pullRequest(number:$number){"
    "reviews(first:100,after:$after){"
    "pageInfo{hasNextPage endCursor}"
    "nodes{author{login} commit{oid}}"
    "}"
    "}"
    "}"
    "}"
)


def _review_request_command(config: shared.FinishConfig) -> str:
    if config.review_bot_login == "chatgpt-codex-connector[bot]":
        return "@codex review"
    return f"@{config.review_bot_login} review"


def _request_comment_body(body: object) -> str:
    return str(body or "").strip()


def _marker_for_head(*, config: shared.FinishConfig, head_oid: str) -> str:
    return f"<!-- horadus:fresh-review reviewer={config.review_bot_login} head={head_oid} -->"


def _request_timeline(
    pr_url: str, *, config: shared.FinishConfig
) -> tuple[int, str, list[dict[str, Any]]]:
    pr_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number,headRefOid", "--jq", "."]
    )
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if pr_result.returncode != 0 or repo_result.returncode != 0:
        raise ValueError("Unable to determine PR metadata for fresh-review request state.")
    try:
        pr_payload = json.loads(pr_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse PR metadata for fresh-review request state.") from exc
    if not isinstance(pr_payload, dict):
        raise ValueError("Unable to parse PR metadata for fresh-review request state.")
    pr_number = pr_payload.get("number")
    head_oid = str(pr_payload.get("headRefOid") or "").strip()
    repo_name = repo_result.stdout.strip()
    if not isinstance(pr_number, int) or "/" not in repo_name or not head_oid:
        raise ValueError("Unable to determine PR metadata for fresh-review request state.")
    owner, repo = repo_name.split("/", 1)

    query = (
        "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "timelineItems(first:100,after:$after,itemTypes:[ISSUE_COMMENT,PULL_REQUEST_COMMIT,HEAD_REF_FORCE_PUSHED_EVENT]){"
        "pageInfo{hasNextPage endCursor}"
        "nodes{"
        "__typename "
        "... on IssueComment{id body createdAt author{login}} "
        "... on PullRequestCommit{commit{oid committedDate}} "
        "... on HeadRefForcePushedEvent{createdAt beforeCommit{oid} afterCommit{oid}}"
        "}"
        "}"
        "}"
        "}"
        "}"
    )
    timeline_items: list[dict[str, Any]] = []
    after_cursor: str | None = None
    while True:
        args = [
            config.gh_bin,
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number}",
        ]
        if after_cursor is not None:
            args.extend(["-F", f"after={after_cursor}"])
        else:
            args.extend(["-F", "after="])
        timeline_result = shared._run_command(args)
        if timeline_result.returncode != 0:
            raise ValueError("Unable to inspect fresh-review request history.")
        try:
            payload = json.loads(timeline_result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Unable to parse fresh-review request history.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Unexpected fresh-review request history payload.")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Unexpected fresh-review request history payload.")
        repository = data.get("repository")
        if not isinstance(repository, dict):
            raise ValueError("Unexpected fresh-review request history payload.")
        pull_request = repository.get("pullRequest")
        if not isinstance(pull_request, dict):
            raise ValueError("Unexpected fresh-review request history payload.")
        timeline_payload = pull_request.get("timelineItems")
        if not isinstance(timeline_payload, dict):
            raise ValueError("Unexpected fresh-review request history payload.")
        page_info = timeline_payload.get("pageInfo")
        page_nodes = timeline_payload.get("nodes")
        if not isinstance(page_info, dict) or not isinstance(page_nodes, list):
            raise ValueError("Unexpected fresh-review request history payload.")
        for item in page_nodes:
            if not isinstance(item, dict):
                raise ValueError("Unexpected fresh-review request history payload.")
            timeline_items.append(item)
        if page_info.get("hasNextPage") is not True:
            break
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise ValueError("Fresh-review request history pagination is incomplete.")
        after_cursor = end_cursor
    return (pr_number, head_oid, timeline_items)


def _request_comment_state(
    *, timeline_items: list[dict[str, Any]], config: shared.FinishConfig, head_oid: str
) -> tuple[bool, bool]:
    request_command = _review_request_command(config)
    current_head_start_index = -1
    for index, item in enumerate(timeline_items):
        item_type = str(item.get("__typename") or "").strip()
        if item_type == "HeadRefForcePushedEvent":
            after_commit = item.get("afterCommit")
            if (
                isinstance(after_commit, dict)
                and str(after_commit.get("oid") or "").strip() == head_oid
            ):
                current_head_start_index = index
        elif item_type == "PullRequestCommit":
            commit = item.get("commit")
            if isinstance(commit, dict) and str(commit.get("oid") or "").strip() == head_oid:
                current_head_start_index = index

    saw_current_head_request = False
    saw_other_head_request = False
    current_head_marker = _marker_for_head(config=config, head_oid=head_oid)
    for index, item in enumerate(timeline_items):
        if str(item.get("__typename") or "").strip() != "IssueComment":
            continue
        body = _request_comment_body(item.get("body"))
        if not body.startswith(request_command):
            continue
        if current_head_marker in body:
            saw_current_head_request = True
            continue
        if "<!-- horadus:fresh-review reviewer=" in body:
            saw_other_head_request = True
            continue
        if index > current_head_start_index:
            saw_current_head_request = True
        else:
            saw_other_head_request = True
    return (saw_current_head_request, saw_other_head_request)


def _maybe_request_fresh_review(*, pr_url: str, config: shared.FinishConfig) -> list[str]:
    try:
        _pr_number, head_oid, timeline_items = _request_timeline(pr_url, config=config)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Unable to parse PR metadata"):
            return ["Failed to parse PR metadata for automatic fresh-review request."]
        if message.startswith("Unexpected") or "history" in message:
            return ["Failed to inspect existing fresh-review requests automatically."]
        return ["Failed to determine PR metadata for automatic fresh-review request."]

    marker = _marker_for_head(config=config, head_oid=head_oid)
    request_command = _review_request_command(config)
    request_comment = f"{request_command}\n{marker}"
    saw_current_head_request, _saw_other_head_request = _request_comment_state(
        timeline_items=timeline_items,
        config=config,
        head_oid=head_oid,
    )
    if saw_current_head_request:
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
    return [
        f"Requested a fresh review from `{config.review_bot_login}` with `{request_command}` for head {head_oid}."
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


def _review_entries_from_payload(reviews_payload: object) -> list[dict[str, Any]]:
    review_entries: list[dict[str, Any]] = []
    if isinstance(reviews_payload, list):
        if all(isinstance(entry, dict) for entry in reviews_payload):
            return [entry for entry in reviews_payload if isinstance(entry, dict)]
        for page in reviews_payload:
            if not isinstance(page, list):
                raise ValueError("Unexpected prior reviewer activity payload.")
            for entry in page:
                if not isinstance(entry, dict):
                    raise ValueError("Unexpected prior reviewer activity payload.")
                review_entries.append(entry)
        return review_entries
    raise ValueError("Unexpected prior reviewer activity payload.")


def _graphql_review_entries(
    *, repo_name: str, pr_number: int, config: shared.FinishConfig
) -> list[dict[str, Any]]:
    owner, repo = repo_name.split("/", 1)
    review_entries: list[dict[str, Any]] = []
    after_cursor: str | None = None
    while True:
        args = [
            config.gh_bin,
            "api",
            "graphql",
            "-f",
            f"query={PRE_REVIEW_GRAPHQL_REVIEWS_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number}",
            "-F",
            f"after={after_cursor or ''}",
        ]
        reviews_result = shared._run_command(args)
        if reviews_result.returncode != 0:
            raise ValueError("Unable to inspect prior reviewer activity for pre-review refresh.")
        try:
            payload = json.loads(reviews_result.stdout or "{}")
            reviews_payload = payload["data"]["repository"]["pullRequest"]["reviews"]
            page_info = reviews_payload["pageInfo"]
            page_nodes = reviews_payload["nodes"]
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Unable to parse prior reviewer activity for pre-review refresh."
            ) from exc
        except (KeyError, TypeError) as exc:
            raise ValueError("Unexpected prior reviewer activity payload.") from exc
        if not isinstance(page_info, dict) or not isinstance(page_nodes, list):
            raise ValueError("Unexpected prior reviewer activity payload.")
        for review in page_nodes:
            if not isinstance(review, dict):
                raise ValueError("Unexpected prior reviewer activity payload.")
            user = review.get("author")
            commit = review.get("commit")
            review_entries.append(
                {
                    "user": {"login": user.get("login")} if isinstance(user, dict) else {},
                    "commit_id": commit.get("oid") if isinstance(commit, dict) else "",
                }
            )
        if page_info.get("hasNextPage") is not True:
            return review_entries
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise ValueError("Unexpected prior reviewer activity payload.")
        after_cursor = end_cursor


def _needs_pre_review_fresh_review_request(*, pr_url: str, config: shared.FinishConfig) -> bool:
    try:
        pr_number, head_oid, timeline_items = _request_timeline(pr_url, config=config)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Unable to parse PR metadata"):
            raise ValueError("Unable to parse PR metadata for pre-review refresh state.") from exc
        if message.startswith("Unable to parse fresh-review request history."):
            raise ValueError(
                "Unable to parse prior reviewer activity for pre-review refresh."
            ) from exc
        if message.startswith("Unexpected fresh-review request history payload."):
            raise ValueError("Unexpected prior reviewer activity payload.") from exc
        if "history" in message:
            raise ValueError(
                "Unable to inspect prior reviewer activity for pre-review refresh."
            ) from exc
        raise ValueError("Unable to determine PR metadata for pre-review refresh state.") from exc
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    repo_name = repo_result.stdout.strip()
    if repo_result.returncode != 0 or "/" not in repo_name:
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
        rate_limit_message = reviews_result.stderr.strip() or reviews_result.stdout.strip()
        if "API rate limit exceeded" not in rate_limit_message:
            raise ValueError("Unable to inspect prior reviewer activity for pre-review refresh.")
        review_entries = _graphql_review_entries(
            repo_name=repo_name,
            pr_number=pr_number,
            config=config,
        )
    else:
        try:
            review_entries = _review_entries_from_payload(json.loads(reviews_result.stdout or "[]"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Unable to parse prior reviewer activity for pre-review refresh."
            ) from exc

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
    saw_current_head_request, saw_other_head_request = _request_comment_state(
        timeline_items=timeline_items,
        config=config,
        head_oid=head_oid,
    )
    return (saw_other_head_review or saw_other_head_request) and not (
        saw_current_head_review or saw_current_head_request
    )


__all__ = [
    "_fresh_review_request_blocker",
    "_maybe_request_fresh_review",
    "_needs_pre_review_fresh_review_request",
]
