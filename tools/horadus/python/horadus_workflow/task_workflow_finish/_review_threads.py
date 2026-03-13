from __future__ import annotations

import json
from typing import Any

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _unresolved_review_thread_lines(*, pr_url: str, config: shared.FinishConfig) -> list[str]:
    threads = _review_threads(pr_url=pr_url, config=config)
    return _review_thread_lines(threads, include_outdated=False)


def _review_threads(*, pr_url: str, config: shared.FinishConfig) -> list[dict[str, Any]]:
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if repo_result.returncode != 0:
        raise ValueError(
            shared._result_message(repo_result, "Unable to determine repository name.")
        )
    repo_name = repo_result.stdout.strip()
    if "/" not in repo_name:
        raise ValueError("Unable to determine repository name.")
    owner, repo = repo_name.split("/", 1)

    pr_number_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number", "--jq", ".number"]
    )
    if pr_number_result.returncode != 0:
        raise ValueError(shared._result_message(pr_number_result, "Unable to determine PR number."))
    pr_number_raw = pr_number_result.stdout.strip()
    if not pr_number_raw.isdigit():
        raise ValueError("Unable to determine PR number.")

    query = (
        "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100, after:$after){"
        "pageInfo{hasNextPage endCursor}"
        "nodes{"
        "id isResolved isOutdated "
        "comments(first:20){"
        "pageInfo{hasNextPage}"
        "nodes{author{login} body path line originalLine url}"
        "}"
        "}"
        "}"
        "}"
        "}"
        "}"
    )
    all_threads: list[dict[str, Any]] = []
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
            f"number={pr_number_raw}",
        ]
        if after_cursor is not None:
            args.extend(["-F", f"after={after_cursor}"])
        else:
            args.extend(["-F", "after="])
        threads_result = shared._run_command(args)
        if threads_result.returncode != 0:
            raise ValueError(
                shared._result_message(threads_result, "Unable to load PR review threads.")
            )
        try:
            payload = json.loads(threads_result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Unable to parse PR review threads payload.") from exc

        review_threads = (
            payload.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
        )
        if not isinstance(review_threads, dict):
            raise ValueError("Unexpected PR review threads payload.")
        page_info = review_threads.get("pageInfo")
        nodes = review_threads.get("nodes")
        if not isinstance(page_info, dict) or not isinstance(nodes, list):
            raise ValueError("Unexpected PR review threads payload.")
        for thread in nodes:
            if not isinstance(thread, dict):
                raise ValueError("Unexpected PR review thread entry.")
            comments = thread.get("comments")
            if not isinstance(comments, dict):
                raise ValueError("Unexpected PR review thread comments payload.")
            comment_page_info = comments.get("pageInfo")
            comment_nodes = comments.get("nodes")
            if not isinstance(comment_page_info, dict) or not isinstance(comment_nodes, list):
                raise ValueError("Unexpected PR review thread comments payload.")
            if comment_page_info.get("hasNextPage") is True:
                raise ValueError("PR review thread comments pagination is incomplete.")
            all_threads.append(thread)
        if page_info.get("hasNextPage") is not True:
            break
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise ValueError("PR review thread pagination is incomplete.")
        after_cursor = end_cursor
    return all_threads


def _review_thread_lines(threads: list[dict[str, Any]], *, include_outdated: bool) -> list[str]:
    lines: list[str] = []
    for thread in threads:
        if thread.get("isResolved") is True or (
            not include_outdated and thread.get("isOutdated") is True
        ):
            continue
        comments = thread.get("comments", {}).get("nodes", [])
        if not isinstance(comments, list):
            continue
        comment = next((entry for entry in reversed(comments) if isinstance(entry, dict)), None)
        if comment is None:
            continue
        path = str(comment.get("path") or "<unknown>")
        line = comment.get("line") or comment.get("originalLine") or "?"
        url = str(comment.get("url") or "").strip()
        author = ""
        if isinstance(comment.get("author"), dict):
            author = str(comment["author"].get("login") or "").strip()
        header = f"- {path}:{line}"
        if url:
            header = f"{header} {url}"
        if author:
            header = f"{header} ({author})"
        lines.append(header)
        body = " ".join(str(comment.get("body") or "").strip().split())
        if body:
            lines.append(f"  {body}")
    return lines


def _outdated_unresolved_review_thread_ids(
    *, pr_url: str, config: shared.FinishConfig
) -> list[str]:
    thread_ids: list[str] = []
    for thread in _review_threads(pr_url=pr_url, config=config):
        if thread.get("isResolved") is True or thread.get("isOutdated") is not True:
            continue
        thread_id = str(thread.get("id") or "").strip()
        if thread_id:
            thread_ids.append(thread_id)
    return thread_ids


def _resolve_review_threads(
    *, thread_ids: list[str], config: shared.FinishConfig
) -> tuple[bool, list[str]]:
    if not thread_ids:
        return True, []

    lines: list[str] = []
    for thread_id in thread_ids:
        mutation = (
            "mutation($threadId:ID!){"
            "resolveReviewThread(input:{threadId:$threadId}){"
            "thread{id isResolved}"
            "}"
            "}"
        )
        result = shared._run_command(
            [
                config.gh_bin,
                "api",
                "graphql",
                "-f",
                f"query={mutation}",
                "-F",
                f"threadId={thread_id}",
            ]
        )
        if result.returncode != 0:
            return False, [
                "Failed to resolve outdated review threads automatically.",
                *shared._output_lines(result),
            ]
        lines.append(f"Resolved outdated review thread automatically: {thread_id}")
    return True, lines


__all__ = [
    "_outdated_unresolved_review_thread_ids",
    "_resolve_review_threads",
    "_review_thread_lines",
    "_review_threads",
    "_unresolved_review_thread_lines",
]
