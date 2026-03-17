from __future__ import annotations

import pytest

import tools.horadus.python.horadus_workflow.pr_review_gate_graphql as graphql_module


def test_repo_owner_name_splits_repo() -> None:
    assert graphql_module._repo_owner_name("example/repo") == ("example", "repo")


def test_graphql_reviews_and_comments_supports_pagination() -> None:
    payloads = iter(
        [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviews": {
                                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                                "nodes": [
                                    {
                                        "databaseId": 10,
                                        "state": "COMMENTED",
                                        "body": "review body",
                                        "submittedAt": "2026-03-17T12:00:00+00:00",
                                        "author": {"login": "bot"},
                                        "commit": {"oid": "head-sha"},
                                        "comments": {
                                            "nodes": [
                                                {
                                                    "author": {"login": "bot"},
                                                    "path": "file.py",
                                                    "line": 12,
                                                    "originalLine": 11,
                                                    "body": "comment body",
                                                    "url": "https://example.invalid/comment/1",
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        }
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviews": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [
                                    {
                                        "databaseId": 11,
                                        "state": "APPROVED",
                                        "body": "",
                                        "submittedAt": "2026-03-17T12:05:00+00:00",
                                        "author": None,
                                        "commit": None,
                                        "comments": {
                                            "nodes": [
                                                {
                                                    "author": None,
                                                    "path": "other.py",
                                                    "line": None,
                                                    "originalLine": 7,
                                                    "body": "second comment",
                                                    "url": "https://example.invalid/comment/2",
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        }
                    }
                }
            },
        ]
    )
    calls: list[tuple[str, dict[str, str], str]] = []

    def load_graphql(query: str, fields: dict[str, str], context: str) -> object:
        calls.append((query, fields, context))
        return next(payloads)

    reviews, comments = graphql_module.graphql_reviews_and_comments(
        repo="example/repo",
        pr_number=215,
        load_graphql=load_graphql,
        error_factory=RuntimeError,
    )

    assert len(calls) == 2
    assert calls[0][1]["after"] == ""
    assert calls[1][1]["after"] == "cursor-1"
    assert reviews == [
        {
            "id": 10,
            "state": "COMMENTED",
            "body": "review body",
            "submitted_at": "2026-03-17T12:00:00+00:00",
            "commit_id": "head-sha",
            "user": {"login": "bot"},
        },
        {
            "id": 11,
            "state": "APPROVED",
            "body": "",
            "submitted_at": "2026-03-17T12:05:00+00:00",
            "commit_id": None,
            "user": {},
        },
    ]
    assert comments == [
        {
            "pull_request_review_id": 10,
            "path": "file.py",
            "line": 12,
            "original_line": 11,
            "html_url": "https://example.invalid/comment/1",
            "body": "comment body",
            "user": {"login": "bot"},
        },
        {
            "pull_request_review_id": 11,
            "path": "other.py",
            "line": None,
            "original_line": 7,
            "html_url": "https://example.invalid/comment/2",
            "body": "second comment",
            "user": {},
        },
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "unexpected pull request reviews payload from gh graphql"),
        (
            {"data": {"repository": {"pullRequest": {"reviews": {"pageInfo": [], "nodes": []}}}}},
            "unexpected pull request reviews payload from gh graphql",
        ),
        (
            {"data": {"repository": {"pullRequest": {"reviews": {"pageInfo": {}, "nodes": [1]}}}}},
            "unexpected pull request review entry from gh graphql",
        ),
        (
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviews": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [
                                    {
                                        "databaseId": 1,
                                        "state": "COMMENTED",
                                        "body": "",
                                        "submittedAt": "",
                                        "author": {"login": "bot"},
                                        "commit": {"oid": "head"},
                                        "comments": [],
                                    }
                                ],
                            }
                        }
                    }
                }
            },
            "unexpected pull request review comments payload from gh graphql",
        ),
        (
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviews": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [
                                    {
                                        "databaseId": 1,
                                        "state": "COMMENTED",
                                        "body": "",
                                        "submittedAt": "",
                                        "author": {"login": "bot"},
                                        "commit": {"oid": "head"},
                                        "comments": {"nodes": {}},
                                    }
                                ],
                            }
                        }
                    }
                }
            },
            "unexpected pull request review comments payload from gh graphql",
        ),
        (
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviews": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [
                                    {
                                        "databaseId": 1,
                                        "state": "COMMENTED",
                                        "body": "",
                                        "submittedAt": "",
                                        "author": {"login": "bot"},
                                        "commit": {"oid": "head"},
                                        "comments": {"nodes": [1]},
                                    }
                                ],
                            }
                        }
                    }
                }
            },
            "unexpected pull request review comment entry from gh graphql",
        ),
    ],
)
def test_graphql_reviews_and_comments_rejects_invalid_payloads(
    payload: object, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        graphql_module.graphql_reviews_and_comments(
            repo="example/repo",
            pr_number=215,
            load_graphql=lambda *_args: payload,
            error_factory=RuntimeError,
        )


def test_graphql_reviews_and_comments_rejects_incomplete_pagination() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviews": {
                        "pageInfo": {"hasNextPage": True, "endCursor": None},
                        "nodes": [],
                    }
                }
            }
        }
    }

    with pytest.raises(RuntimeError, match="pull request reviews pagination is incomplete"):
        graphql_module.graphql_reviews_and_comments(
            repo="example/repo",
            pr_number=215,
            load_graphql=lambda *_args: payload,
            error_factory=RuntimeError,
        )


def test_graphql_reactions_supports_pagination_and_thumbs_up_mapping() -> None:
    payloads = iter(
        [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reactions": {
                                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                                "nodes": [
                                    {
                                        "content": "THUMBS_UP",
                                        "createdAt": "2026-03-17T12:00:00+00:00",
                                        "user": {"login": "bot"},
                                    }
                                ],
                            }
                        }
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reactions": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [{"content": "EYES", "createdAt": None, "user": None}],
                            }
                        }
                    }
                }
            },
        ]
    )

    reactions = graphql_module.graphql_reactions(
        repo="example/repo",
        pr_number=215,
        load_graphql=lambda *_args: next(payloads),
        error_factory=RuntimeError,
    )

    assert reactions == [
        {"content": "+1", "created_at": "2026-03-17T12:00:00+00:00", "user": {"login": "bot"}},
        {"content": "EYES", "created_at": None, "user": {}},
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "unexpected PR summary reactions payload from gh graphql"),
        (
            {"data": {"repository": {"pullRequest": {"reactions": {"pageInfo": [], "nodes": []}}}}},
            "unexpected PR summary reactions payload from gh graphql",
        ),
        (
            {
                "data": {
                    "repository": {"pullRequest": {"reactions": {"pageInfo": {}, "nodes": [1]}}}
                }
            },
            "unexpected PR summary reaction entry from gh graphql",
        ),
    ],
)
def test_graphql_reactions_reject_invalid_payloads(payload: object, message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        graphql_module.graphql_reactions(
            repo="example/repo",
            pr_number=215,
            load_graphql=lambda *_args: payload,
            error_factory=RuntimeError,
        )


def test_graphql_reactions_rejects_incomplete_pagination() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reactions": {
                        "pageInfo": {"hasNextPage": True, "endCursor": None},
                        "nodes": [],
                    }
                }
            }
        }
    }

    with pytest.raises(RuntimeError, match="PR summary reactions pagination is incomplete"):
        graphql_module.graphql_reactions(
            repo="example/repo",
            pr_number=215,
            load_graphql=lambda *_args: payload,
            error_factory=RuntimeError,
        )
