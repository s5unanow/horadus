from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

GraphqlLoader = Callable[[str, dict[str, str], str], object]
ErrorFactory = Callable[[str], Exception]


def _repo_owner_name(repo: str) -> tuple[str, str]:
    owner, repo_name = repo.split("/", 1)
    return owner, repo_name


def graphql_reviews_and_comments(
    *,
    repo: str,
    pr_number: int,
    load_graphql: GraphqlLoader,
    error_factory: ErrorFactory,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    owner, repo_name = _repo_owner_name(repo)
    query = (
        "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reviews(first:100,after:$after){"
        "pageInfo{hasNextPage endCursor}"
        "nodes{"
        "databaseId state body submittedAt "
        "author{login} "
        "commit{oid} "
        "comments(first:100){nodes{author{login} path line originalLine body url}}"
        "}"
        "}"
        "}"
        "}"
        "}"
    )
    after_cursor: str | None = None
    reviews: list[dict[str, object]] = []
    comments: list[dict[str, object]] = []
    while True:
        payload = cast(
            "dict[str, Any]",
            load_graphql(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "number": str(pr_number),
                    "after": after_cursor or "",
                },
                "pull request reviews",
            ),
        )
        try:
            reviews_payload = payload["data"]["repository"]["pullRequest"]["reviews"]
            page_info = reviews_payload["pageInfo"]
            page_nodes = reviews_payload["nodes"]
        except (KeyError, TypeError) as exc:
            raise error_factory("unexpected pull request reviews payload from gh graphql") from exc
        if not isinstance(page_info, dict) or not isinstance(page_nodes, list):
            raise error_factory("unexpected pull request reviews payload from gh graphql")
        for node in page_nodes:
            if not isinstance(node, dict):
                raise error_factory("unexpected pull request review entry from gh graphql")
            review_id = node.get("databaseId")
            author = node.get("author")
            commit = node.get("commit")
            reviews.append(
                {
                    "id": review_id,
                    "state": node.get("state"),
                    "body": node.get("body"),
                    "submitted_at": node.get("submittedAt"),
                    "commit_id": commit.get("oid") if isinstance(commit, dict) else None,
                    "user": {"login": author.get("login")} if isinstance(author, dict) else {},
                }
            )
            review_comments = node.get("comments")
            if not isinstance(review_comments, dict):
                raise error_factory(
                    "unexpected pull request review comments payload from gh graphql"
                )
            comment_nodes = review_comments.get("nodes")
            if not isinstance(comment_nodes, list):
                raise error_factory(
                    "unexpected pull request review comments payload from gh graphql"
                )
            for comment_node in comment_nodes:
                if not isinstance(comment_node, dict):
                    raise error_factory(
                        "unexpected pull request review comment entry from gh graphql"
                    )
                comment_author = comment_node.get("author")
                comments.append(
                    {
                        "pull_request_review_id": review_id,
                        "path": comment_node.get("path"),
                        "line": comment_node.get("line"),
                        "original_line": comment_node.get("originalLine"),
                        "html_url": comment_node.get("url"),
                        "body": comment_node.get("body"),
                        "user": (
                            {"login": comment_author.get("login")}
                            if isinstance(comment_author, dict)
                            else {}
                        ),
                    }
                )
        if page_info.get("hasNextPage") is not True:
            break
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise error_factory("pull request reviews pagination is incomplete")
        after_cursor = end_cursor
    return reviews, comments


def graphql_reactions(
    *,
    repo: str,
    pr_number: int,
    load_graphql: GraphqlLoader,
    error_factory: ErrorFactory,
) -> list[dict[str, object]]:
    owner, repo_name = _repo_owner_name(repo)
    query = (
        "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reactions(first:100,after:$after){"
        "pageInfo{hasNextPage endCursor}"
        "nodes{content createdAt user{login}}"
        "}"
        "}"
        "}"
        "}"
    )
    after_cursor: str | None = None
    reactions: list[dict[str, object]] = []
    while True:
        payload = cast(
            "dict[str, Any]",
            load_graphql(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "number": str(pr_number),
                    "after": after_cursor or "",
                },
                "PR summary reactions",
            ),
        )
        try:
            reactions_payload = payload["data"]["repository"]["pullRequest"]["reactions"]
            page_info = reactions_payload["pageInfo"]
            page_nodes = reactions_payload["nodes"]
        except (KeyError, TypeError) as exc:
            raise error_factory("unexpected PR summary reactions payload from gh graphql") from exc
        if not isinstance(page_info, dict) or not isinstance(page_nodes, list):
            raise error_factory("unexpected PR summary reactions payload from gh graphql")
        for node in page_nodes:
            if not isinstance(node, dict):
                raise error_factory("unexpected PR summary reaction entry from gh graphql")
            user = node.get("user")
            content = node.get("content")
            reactions.append(
                {
                    "content": "+1" if content == "THUMBS_UP" else content,
                    "created_at": node.get("createdAt"),
                    "user": {"login": user.get("login")} if isinstance(user, dict) else {},
                }
            )
        if page_info.get("hasNextPage") is not True:
            break
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise error_factory("PR summary reactions pagination is incomplete")
        after_cursor = end_cursor
    return reactions


__all__ = ["graphql_reactions", "graphql_reviews_and_comments"]
