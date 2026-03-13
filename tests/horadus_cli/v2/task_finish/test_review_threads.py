from __future__ import annotations

import json
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def test_unresolved_review_thread_lines_reports_unresolved_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [
                                                        {
                                                            "author": {
                                                                "login": "chatgpt-codex-connector[bot]"
                                                            },
                                                            "body": "Please resolve this thread.",
                                                            "path": "tools/horadus/python/horadus_cli/task_commands.py",
                                                            "line": 2201,
                                                            "originalLine": 2201,
                                                            "url": "https://example.invalid/comment/290",
                                                        }
                                                    ],
                                                },
                                            },
                                            {
                                                "isResolved": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [
                                                        {
                                                            "author": {"login": "reviewer"},
                                                            "body": "Already resolved.",
                                                            "path": "README.md",
                                                            "line": 10,
                                                            "originalLine": 10,
                                                            "url": "https://example.invalid/comment/resolved",
                                                        }
                                                    ],
                                                },
                                            },
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._unresolved_review_thread_lines(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "- tools/horadus/python/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
        "  Please resolve this thread.",
    ]


def test_unresolved_review_thread_lines_ignores_outdated_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [
                                                        {
                                                            "author": {"login": "reviewer"},
                                                            "body": "Old comment.",
                                                            "path": "README.md",
                                                            "line": 10,
                                                            "originalLine": 10,
                                                            "url": "https://example.invalid/comment/stale",
                                                        }
                                                    ],
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )


def test_outdated_unresolved_review_thread_ids_reports_only_stale_unresolved_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "id": "thread-stale-1",
                                                "isResolved": False,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            },
                                            {
                                                "id": "thread-open-1",
                                                "isResolved": False,
                                                "isOutdated": False,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            },
                                            {
                                                "id": "thread-resolved-1",
                                                "isResolved": True,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            },
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._outdated_unresolved_review_thread_ids(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["thread-stale-1"]

    def fake_run_command_without_id(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command_without_id)
    assert (
        task_commands_module._outdated_unresolved_review_thread_ids(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )


def test_resolve_review_threads_reports_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    calls: list[list[str]] = []

    def fake_run_command_ok(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(
            args, stdout='{"data":{"resolveReviewThread":{"thread":{"id":"x","isResolved":true}}}}'
        )

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command_ok)
    ok, lines = task_commands_module._resolve_review_threads(
        thread_ids=["thread-1", "thread-2"],
        config=config,
    )
    assert ok is True
    assert lines == [
        "Resolved outdated review thread automatically: thread-1",
        "Resolved outdated review thread automatically: thread-2",
    ]
    assert all(call[:3] == ["gh", "api", "graphql"] for call in calls)
    assert task_commands_module._resolve_review_threads(thread_ids=[], config=config) == (True, [])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="boom"),
    )
    ok, lines = task_commands_module._resolve_review_threads(
        thread_ids=["thread-3"],
        config=config,
    )
    assert ok is False
    assert lines[0] == "Failed to resolve outdated review threads automatically."
    assert lines[-1] == "boom"


def test_unresolved_review_thread_lines_handles_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="repo failed"),
    )
    with pytest.raises(ValueError, match="repo failed"):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout="invalid\n")
            if args[:4] == ["gh", "repo", "view", "--json"]
            else _completed(args)
        ),
    )
    with pytest.raises(ValueError, match=r"Unable to determine repository name\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_invalid_pr(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, returncode=1, stderr="pr failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_invalid_pr)
    with pytest.raises(ValueError, match="pr failed"):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_non_numeric_pr(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="not-a-number\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_non_numeric_pr)
    with pytest.raises(ValueError, match=r"Unable to determine PR number\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_bad_graphql(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, returncode=1, stderr="graphql failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_graphql)
    with pytest.raises(ValueError, match="graphql failed"):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_bad_json(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout="{bad")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_json)
    with pytest.raises(ValueError, match=r"Unable to parse PR review threads payload\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_bad_nodes(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": "not-a-list",
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_nodes)
    with pytest.raises(ValueError, match=r"Unexpected PR review threads payload\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    def fake_bad_review_threads(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {"data": {"repository": {"pullRequest": {"reviewThreads": "bad"}}}}
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_review_threads)
    with pytest.raises(ValueError, match=r"Unexpected PR review threads payload\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_unresolved_review_thread_lines_handles_sparse_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [
                                                        {
                                                            "author": None,
                                                            "body": "",
                                                            "path": "README.md",
                                                            "line": None,
                                                            "originalLine": None,
                                                            "url": "",
                                                        }
                                                    ],
                                                },
                                            },
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._unresolved_review_thread_lines(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["- README.md:?"]


def test_unresolved_review_thread_lines_fail_closed_on_invalid_comment_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": "bad",
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match=r"Unexpected PR review thread comments payload\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_unresolved_review_thread_lines_fail_closed_on_invalid_thread_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": ["bad"],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match=r"Unexpected PR review thread entry\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_unresolved_review_thread_lines_fail_closed_on_incomplete_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": True, "endCursor": ""},
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": True},
                                                    "nodes": [],
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match=r"PR review thread comments pagination is incomplete\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_outdated_review_thread_ids_fail_closed_on_missing_thread_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": True, "endCursor": ""},
                                        "nodes": [
                                            {
                                                "id": "thread-stale-1",
                                                "isResolved": False,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match=r"PR review thread pagination is incomplete\."):
        task_commands_module._outdated_unresolved_review_thread_ids(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_outdated_review_thread_ids_follow_pagination_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )
    graphql_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal graphql_calls
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            graphql_calls += 1
            if graphql_calls == 1:
                assert any(arg == "after=" for arg in args)
                return _completed(
                    args,
                    stdout=json.dumps(
                        {
                            "data": {
                                "repository": {
                                    "pullRequest": {
                                        "reviewThreads": {
                                            "pageInfo": {
                                                "hasNextPage": True,
                                                "endCursor": "cursor-1",
                                            },
                                            "nodes": [
                                                {
                                                    "id": "thread-stale-1",
                                                    "isResolved": False,
                                                    "isOutdated": True,
                                                    "comments": {
                                                        "pageInfo": {"hasNextPage": False},
                                                        "nodes": [],
                                                    },
                                                }
                                            ],
                                        }
                                    }
                                }
                            }
                        }
                    ),
                )
            assert any(arg == "after=cursor-1" for arg in args)
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "id": "thread-stale-2",
                                                "isResolved": False,
                                                "isOutdated": True,
                                                "comments": {
                                                    "pageInfo": {"hasNextPage": False},
                                                    "nodes": [],
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._outdated_unresolved_review_thread_ids(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["thread-stale-1", "thread-stale-2"]


def test_unresolved_review_thread_lines_fail_closed_on_non_dict_comments_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [{"isResolved": False, "comments": "bad"}],
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match=r"Unexpected PR review thread comments payload\."):
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )


def test_review_thread_lines_skip_non_list_and_non_dict_comments() -> None:
    assert (
        task_commands_module._review_thread_lines(
            [
                {"isResolved": False, "comments": {"nodes": "bad"}},
                {"isResolved": False, "comments": {"nodes": ["bad"]}},
            ],
            include_outdated=False,
        )
        == []
    )


def test_parse_review_gate_result_rejects_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="Unable to parse review gate payload: Expecting"):
        task_commands_module._parse_review_gate_result(_completed(["review"], stdout="{bad"))

    with pytest.raises(ValueError, match="expected a JSON object"):
        task_commands_module._parse_review_gate_result(_completed(["review"], stdout='["bad"]'))

    with pytest.raises(ValueError, match="actionable_lines must be a string list"):
        task_commands_module._parse_review_gate_result(
            _completed(
                ["review"],
                stdout=json.dumps(
                    {
                        "status": "pass",
                        "reason": "thumbs_up",
                        "reviewer_login": "bot",
                        "reviewed_head_oid": "head-a",
                        "current_head_oid": "head-a",
                        "summary": "ok",
                        "actionable_lines": "bad",
                    }
                ),
            )
        )

    with pytest.raises(ValueError, match="informational_lines must be a string list"):
        task_commands_module._parse_review_gate_result(
            _completed(
                ["review"],
                stdout=json.dumps(
                    {
                        "status": "pass",
                        "reason": "thumbs_up",
                        "reviewer_login": "bot",
                        "reviewed_head_oid": "head-a",
                        "current_head_oid": "head-a",
                        "summary": "ok",
                        "actionable_lines": [],
                        "informational_lines": "bad",
                    }
                ),
            )
        )

    with pytest.raises(ValueError, match="missing status"):
        task_commands_module._parse_review_gate_result(
            _completed(["review"], stdout=json.dumps({"reason": "thumbs_up"}))
        )

    with pytest.raises(ValueError, match="invalid field types"):
        task_commands_module._parse_review_gate_result(
            _completed(
                ["review"],
                stdout=json.dumps(
                    {
                        "status": "pass",
                        "reason": "thumbs_up",
                        "reviewer_login": "bot",
                        "reviewed_head_oid": "head-a",
                        "current_head_oid": "head-a",
                        "summary": "ok",
                        "actionable_lines": [],
                        "actionable_comment_count": "bad-int",
                    }
                ),
            )
        )
