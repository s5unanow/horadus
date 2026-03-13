from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit

PR_URL = "https://example.invalid/pr/290"
DEFAULT_REPO = "example/repo\n"
DEFAULT_PR_NUMBER = 290
DEFAULT_HEAD = "head-sha-290"
DEFAULT_CURRENT_HEAD = "head-sha-current"


def _finish_config(
    *, review_bot_login: str = "chatgpt-codex-connector[bot]"
) -> task_commands_module.FinishConfig:
    return task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login=review_bot_login,
        review_timeout_policy="allow",
    )


def _pr_payload(*, number: int = DEFAULT_PR_NUMBER, head_oid: str = DEFAULT_HEAD) -> str:
    return json.dumps({"number": number, "headRefOid": head_oid}) + "\n"


def _timeline_payload(
    *nodes: dict[str, object], has_next_page: bool = False, end_cursor: str | None = None
) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "timelineItems": {
                            "pageInfo": {
                                "hasNextPage": has_next_page,
                                "endCursor": end_cursor,
                            },
                            "nodes": list(nodes),
                        }
                    }
                }
            }
        }
    )


def _issue_comment_node(body: str) -> dict[str, object]:
    return {
        "__typename": "IssueComment",
        "id": "IC_1",
        "body": body,
        "createdAt": "2026-03-13T10:00:00Z",
        "author": {"login": "s5unanow"},
    }


def _commit_node(oid: str) -> dict[str, object]:
    return {
        "__typename": "PullRequestCommit",
        "commit": {
            "oid": oid,
            "committedDate": "2026-03-13T09:59:00Z",
        },
    }


def _timeline_after(args: list[str]) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == "-F" and args[index + 1].startswith("after="):
            after = args[index + 1].split("=", 1)[1]
            return after or None
    return None


def _refresh_run_command_factory(
    *,
    pr_stdout: str = _pr_payload(),
    pr_returncode: int = 0,
    repo_stdout: str = DEFAULT_REPO,
    repo_returncode: int = 0,
    timeline_stdout: str = "",
    timeline_returncode: int = 0,
    on_comment: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", PR_URL]:
            return _completed(args, stdout=pr_stdout, returncode=pr_returncode)
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout=repo_stdout, returncode=repo_returncode)
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=timeline_stdout, returncode=timeline_returncode)
        if on_comment is not None:
            return on_comment(args)
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    return fake_run_command


def _pre_review_run_command_factory(
    *,
    pr_stdout: str = _pr_payload(head_oid=DEFAULT_CURRENT_HEAD),
    pr_returncode: int = 0,
    first_repo_stdout: str = DEFAULT_REPO,
    first_repo_returncode: int = 0,
    second_repo_stdout: str = DEFAULT_REPO,
    second_repo_returncode: int = 0,
    timeline_stdout: str = _timeline_payload(),
    timeline_returncode: int = 0,
    reviews_stdout: str = "[]\n",
    reviews_returncode: int = 0,
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    repo_calls = {"count": 0}

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", PR_URL]:
            return _completed(args, stdout=pr_stdout, returncode=pr_returncode)
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            repo_calls["count"] += 1
            if repo_calls["count"] == 1:
                return _completed(
                    args,
                    stdout=first_repo_stdout,
                    returncode=first_repo_returncode,
                )
            return _completed(
                args,
                stdout=second_repo_stdout,
                returncode=second_repo_returncode,
            )
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=timeline_stdout, returncode=timeline_returncode)
        return _completed(args, stdout=reviews_stdout, returncode=reviews_returncode)

    return fake_run_command


def test_maybe_request_fresh_review_posts_codex_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    called: dict[str, object] = {}

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", PR_URL]:
            return _completed(args, stdout=_pr_payload())
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout=DEFAULT_REPO)
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=_timeline_payload())
        called["args"] = args
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == [
        f"Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head {DEFAULT_HEAD}."
    ]
    assert called["args"] == [
        "gh",
        "pr",
        "comment",
        PR_URL,
        "--body",
        f"@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head={DEFAULT_HEAD} -->",
    ]


def test_maybe_request_fresh_review_handles_non_codex_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    non_codex_config = _finish_config(review_bot_login="other-reviewer")
    non_codex_calls: list[list[str]] = []

    def fake_non_codex_run_command(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", PR_URL]:
            return _completed(args, stdout=_pr_payload())
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout=DEFAULT_REPO)
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=_timeline_payload())
        non_codex_calls.append(args)
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_non_codex_run_command)
    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=non_codex_config,
    ) == [
        f"Requested a fresh review from `other-reviewer` with `@other-reviewer review` for head {DEFAULT_HEAD}."
    ]
    assert non_codex_calls[-1] == [
        "gh",
        "pr",
        "comment",
        PR_URL,
        "--body",
        f"@other-reviewer review\n<!-- horadus:fresh-review reviewer=other-reviewer head={DEFAULT_HEAD} -->",
    ]

    codex_config = _finish_config()
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        _refresh_run_command_factory(
            timeline_stdout=_timeline_payload(),
            on_comment=lambda args: _completed(args, returncode=1, stderr="comment failed"),
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=codex_config,
    ) == [
        "Failed to request a fresh review from `chatgpt-codex-connector[bot]` automatically.",
        "comment failed",
    ]


def test_maybe_request_fresh_review_dedupes_current_head_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        _refresh_run_command_factory(
            timeline_stdout=_timeline_payload(
                _issue_comment_node(
                    f"@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head={DEFAULT_HEAD} -->"
                )
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == [
        f"Fresh review already requested for `chatgpt-codex-connector[bot]` on current head {DEFAULT_HEAD}."
    ]


@pytest.mark.parametrize(
    ("stub_kwargs", "expected"),
    [
        (
            {"pr_returncode": 1},
            "Failed to determine PR metadata for automatic fresh-review request.",
        ),
        ({"pr_stdout": "{bad"}, "Failed to parse PR metadata for automatic fresh-review request."),
        (
            {"pr_stdout": '["bad"]\n'},
            "Failed to parse PR metadata for automatic fresh-review request.",
        ),
        (
            {
                "pr_stdout": '{"number":"bad","headRefOid":""}\n',
                "repo_stdout": "not-a-repo\n",
                "timeline_stdout": _timeline_payload(),
            },
            "Failed to determine PR metadata for automatic fresh-review request.",
        ),
        (
            {"timeline_returncode": 1},
            "Failed to inspect existing fresh-review requests automatically.",
        ),
        (
            {"timeline_stdout": "{bad"},
            "Failed to inspect existing fresh-review requests automatically.",
        ),
        (
            {"timeline_stdout": '["bad"]\n'},
            "Failed to inspect existing fresh-review requests automatically.",
        ),
        (
            {"timeline_stdout": _timeline_payload("bad")},  # type: ignore[arg-type]
            "Failed to inspect existing fresh-review requests automatically.",
        ),
    ],
)
def test_maybe_request_fresh_review_handles_metadata_and_comment_parse_failures(
    monkeypatch: pytest.MonkeyPatch,
    stub_kwargs: dict[str, object],
    expected: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        _refresh_run_command_factory(**stub_kwargs),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=_finish_config(),
    ) == [expected]


@pytest.mark.parametrize(
    ("timeline_stdout"),
    [
        _timeline_payload(_issue_comment_node("@codex review")),
        _timeline_payload(
            _issue_comment_node("unrelated"),
            _commit_node(DEFAULT_HEAD),
            _issue_comment_node("@codex review"),
        ),
    ],
)
def test_maybe_request_fresh_review_dedupes_plain_current_head_requests(
    monkeypatch: pytest.MonkeyPatch,
    timeline_stdout: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        _refresh_run_command_factory(timeline_stdout=timeline_stdout),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=_finish_config(),
    ) == [
        f"Fresh review already requested for `chatgpt-codex-connector[bot]` on current head {DEFAULT_HEAD}."
    ]


def test_maybe_request_fresh_review_dedupes_paginated_current_head_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", PR_URL]:
            return _completed(args, stdout=_pr_payload())
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout=DEFAULT_REPO)
        if args[:3] == ["gh", "api", "graphql"]:
            after = _timeline_after(args)
            if after is None:
                return _completed(
                    args,
                    stdout=_timeline_payload(
                        _issue_comment_node("unrelated"),
                        _commit_node(DEFAULT_HEAD),
                        has_next_page=True,
                        end_cursor="cursor-1",
                    ),
                )
            assert after == "cursor-1"
            return _completed(
                args,
                stdout=_timeline_payload(_issue_comment_node("@codex review")),
            )
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == [
        f"Fresh review already requested for `chatgpt-codex-connector[bot]` on current head {DEFAULT_HEAD}."
    ]


def test_maybe_request_fresh_review_rejects_incomplete_timeline_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout=_pr_payload())
            if args[:4] == ["gh", "pr", "view", PR_URL]
            else _completed(args, stdout=DEFAULT_REPO)
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _commit_node(DEFAULT_HEAD),
                    has_next_page=True,
                    end_cursor=None,
                ),
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_maybe_request_fresh_review_rejects_non_dict_timeline_items_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout=_pr_payload())
            if args[:4] == ["gh", "pr", "view", PR_URL]
            else _completed(args, stdout=DEFAULT_REPO)
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "timelineItems": [],
                                }
                            }
                        }
                    }
                ),
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_maybe_request_fresh_review_handles_graphql_null_data_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout=_pr_payload())
            if args[:4] == ["gh", "pr", "view", PR_URL]
            else _completed(args, stdout=DEFAULT_REPO)
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout='{"data":null,"errors":[{"message":"boom"}]}')
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


@pytest.mark.parametrize(
    ("timeline_payload"),
    [
        {"data": {"repository": None}},
        {"data": {"repository": {"pullRequest": None}}},
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "timelineItems": {
                            "pageInfo": None,
                            "nodes": [],
                        }
                    }
                }
            }
        },
    ],
)
def test_maybe_request_fresh_review_rejects_nested_invalid_timeline_shapes(
    monkeypatch: pytest.MonkeyPatch, timeline_payload: dict[str, object]
) -> None:
    config = _finish_config()

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout=_pr_payload())
            if args[:4] == ["gh", "pr", "view", PR_URL]
            else _completed(args, stdout=DEFAULT_REPO)
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=json.dumps(timeline_payload))
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url=PR_URL,
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_needs_pre_review_fresh_review_request_detects_stale_review_context(
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
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _issue_comment_node(
                        "@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head=head-sha-old -->"
                    )
                ),
            )
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(
                args,
                stdout=(
                    "[["
                    '{"user":{"login":"chatgpt-codex-connector[bot]"},"commit_id":"head-sha-old"},'
                    '{"user":{"login":"other-reviewer"},"commit_id":"head-sha-old"},'
                    '{"user":{"login":"chatgpt-codex-connector[bot]"},"commit_id":""},'
                    '{"user":"bad","commit_id":"head-sha-old"}'
                    "]]\n"
                ),
            )
        ),
    )
    assert (
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        is True
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _issue_comment_node(
                        "@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head=head-sha-current -->"
                    )
                ),
            )
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(
                args,
                stdout=(
                    "["
                    '{"user":{"login":"chatgpt-codex-connector[bot]"},"commit_id":"head-sha-old"},'
                    '{"user":{"login":"chatgpt-codex-connector[bot]"},"commit_id":"head-sha-current"}'
                    "]\n"
                ),
            )
        ),
    )
    assert (
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        is False
    )


def test_needs_pre_review_fresh_review_request_detects_plain_request_on_older_head(
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
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _issue_comment_node("@codex review"),
                    {
                        "__typename": "HeadRefForcePushedEvent",
                        "createdAt": "2026-03-13T10:05:00Z",
                        "beforeCommit": {"oid": "head-sha-old"},
                        "afterCommit": {"oid": "head-sha-current"},
                    },
                ),
            )
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )

    assert (
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        is True
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    assert (
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        is False
    )


def test_maybe_request_fresh_review_ignores_non_matching_head_events(
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
    called: dict[str, object] = {}

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout="example/repo\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=_timeline_payload(
                    {
                        "__typename": "HeadRefForcePushedEvent",
                        "createdAt": "2026-03-13T10:00:00Z",
                        "beforeCommit": {"oid": "old-head"},
                        "afterCommit": {"oid": "other-head"},
                    },
                    _commit_node("other-head"),
                ),
            )
        called["args"] = args
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review` for head head-sha-290."
    ]
    assert called["args"] == [
        "gh",
        "pr",
        "comment",
        "https://example.invalid/pr/290",
        "--body",
        "@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head=head-sha-290 -->",
    ]


@pytest.mark.parametrize(
    ("stub_kwargs", "expected"),
    [
        ({"pr_returncode": 1}, "Unable to determine PR metadata"),
        ({"pr_stdout": "{bad"}, "Unable to parse PR metadata"),
        ({"pr_stdout": '["bad"]\n'}, "Unable to parse PR metadata"),
        (
            {
                "pr_stdout": '{"number":"bad","headRefOid":""}\n',
                "first_repo_stdout": "not-a-repo\n",
            },
            "Unable to determine PR metadata",
        ),
        ({"timeline_returncode": 1}, "Unable to inspect prior reviewer activity"),
        ({"timeline_stdout": "{bad"}, "Unable to parse prior reviewer activity"),
        (
            {"timeline_stdout": '{"body":"not-a-list"}\n'},
            "Unexpected prior reviewer activity payload",
        ),
        (
            {"timeline_stdout": '{"data":null,"errors":[{"message":"boom"}]}'},
            "Unexpected prior reviewer activity payload",
        ),
        ({"second_repo_returncode": 1}, "Unable to determine PR metadata"),
        ({"first_repo_returncode": 1}, "Unable to determine PR metadata"),
        ({"reviews_returncode": 1}, "Unable to inspect prior reviewer activity"),
        ({"reviews_stdout": "{bad"}, "Unable to parse prior reviewer activity"),
        (
            {"reviews_stdout": '{"bad":"payload"}\n'},
            "Unexpected prior reviewer activity payload",
        ),
        (
            {"reviews_stdout": '["bad"]\n'},
            "Unexpected prior reviewer activity payload",
        ),
        (
            {"reviews_stdout": "[[1]]\n"},
            "Unexpected prior reviewer activity payload",
        ),
    ],
)
def test_needs_pre_review_fresh_review_request_handles_metadata_and_review_failures(
    monkeypatch: pytest.MonkeyPatch,
    stub_kwargs: dict[str, object],
    expected: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        _pre_review_run_command_factory(**stub_kwargs),
    )

    with pytest.raises(ValueError, match=expected):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url=PR_URL,
            config=_finish_config(),
        )


def test_prepare_current_head_review_window_uses_compat_exports_across_split_modules(
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
    context = task_commands_module.FinishContext(
        branch_name="codex/task-317-split-review-modules",
        branch_task_id="TASK-317",
        task_id="TASK-317",
    )

    monkeypatch.setattr(
        task_commands_module, "_current_head_finish_blocker", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        task_commands_module,
        "_outdated_unresolved_review_thread_ids",
        lambda **_kwargs: ["thread-stale-1"],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_review_threads",
        lambda **_kwargs: (True, ["Resolved outdated review thread automatically: thread-stale-1"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_fresh_review_request_blocker",
        lambda **_kwargs: (["Requested fresh review."], None),
    )

    refresh_lines, blocker = task_commands_module._prepare_current_head_review_window(
        context=context,
        pr_url="https://example.invalid/pr/317",
        config=config,
    )

    assert blocker is None
    assert refresh_lines == [
        "Resolved outdated review thread automatically: thread-stale-1",
        "Requested fresh review.",
        "Refreshed stale review state for the current head; discarding the previous review window and starting a fresh 5s review window.",
    ]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout='["bad"]\n')
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unexpected prior reviewer activity payload"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout="[[1]]\n")
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unexpected prior reviewer activity payload"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
