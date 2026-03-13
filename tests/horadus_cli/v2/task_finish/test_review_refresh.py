from __future__ import annotations

import json
import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


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


def test_maybe_request_fresh_review_posts_codex_comment(
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
            return _completed(args, stdout=_timeline_payload())
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


def test_maybe_request_fresh_review_handles_non_codex_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    non_codex_config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="other-reviewer",
        review_timeout_policy="allow",
    )
    non_codex_calls: list[list[str]] = []

    def fake_non_codex_run_command(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout="example/repo\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=_timeline_payload())
        non_codex_calls.append(args)
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_non_codex_run_command)
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=non_codex_config,
    ) == [
        "Requested a fresh review from `other-reviewer` with `@other-reviewer review` for head head-sha-290."
    ]
    assert non_codex_calls[-1] == [
        "gh",
        "pr",
        "comment",
        "https://example.invalid/pr/290",
        "--body",
        "@other-reviewer review\n<!-- horadus:fresh-review reviewer=other-reviewer head=head-sha-290 -->",
    ]

    codex_config = task_commands_module.FinishConfig(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, returncode=1, stderr="comment failed")
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=codex_config,
    ) == [
        "Failed to request a fresh review from `chatgpt-codex-connector[bot]` automatically.",
        "comment failed",
    ]


def test_maybe_request_fresh_review_dedupes_current_head_request(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _issue_comment_node(
                        "@codex review\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head=head-sha-290 -->"
                    )
                ),
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-290."
    ]


def test_maybe_request_fresh_review_handles_metadata_and_comment_parse_failures(
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
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="boom"),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to determine PR metadata for automatic fresh-review request."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout="{bad")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to parse PR metadata for automatic fresh-review request."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='["bad"]\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to parse PR metadata for automatic fresh-review request."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":"bad","headRefOid":""}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="not-a-repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload())
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to determine PR metadata for automatic fresh-review request."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, returncode=1, stderr="timeline failed")
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout="{bad")
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout='["bad"]\n')
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload("bad"))  # type: ignore[arg-type]
        ),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_maybe_request_fresh_review_dedupes_plain_current_head_request(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload(_issue_comment_node("@codex review")))
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-290."
    ]


def test_maybe_request_fresh_review_dedupes_plain_request_after_current_head_commit(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _issue_comment_node("unrelated"),
                    _commit_node("head-sha-290"),
                    _issue_comment_node("@codex review"),
                ),
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-290."
    ]


def test_maybe_request_fresh_review_dedupes_paginated_current_head_request(
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
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            return _completed(args, stdout="example/repo\n")
        if args[:3] == ["gh", "api", "graphql"]:
            after = _timeline_after(args)
            if after is None:
                return _completed(
                    args,
                    stdout=_timeline_payload(
                        _issue_comment_node("unrelated"),
                        _commit_node("head-sha-290"),
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
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "Fresh review already requested for `chatgpt-codex-connector[bot]` on current head head-sha-290."
    ]


def test_maybe_request_fresh_review_rejects_incomplete_timeline_pagination(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(
                args,
                stdout=_timeline_payload(
                    _commit_node("head-sha-290"),
                    has_next_page=True,
                    end_cursor=None,
                ),
            )
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_maybe_request_fresh_review_rejects_non_dict_timeline_items_payload(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
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
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Failed to inspect existing fresh-review requests automatically."]


def test_maybe_request_fresh_review_handles_graphql_null_data_payload(
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout='{"data":null,"errors":[{"message":"boom"}]}')
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
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
            _completed(args, stdout='{"number":290,"headRefOid":"head-sha-290"}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=json.dumps(timeline_payload))
        ),
    )

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
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


def test_needs_pre_review_fresh_review_request_handles_metadata_and_review_failures(
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
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="boom"),
    )
    with pytest.raises(ValueError, match="Unable to determine PR metadata"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout="{bad")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
        ),
    )
    with pytest.raises(ValueError, match="Unable to parse PR metadata"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='["bad"]\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="example/repo\n")
        ),
    )
    with pytest.raises(ValueError, match="Unable to parse PR metadata"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout='{"number":"bad","headRefOid":""}\n')
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]
            else _completed(args, stdout="not-a-repo\n")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload())
        ),
    )
    with pytest.raises(ValueError, match="Unable to determine PR metadata"):
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
            else _completed(args, returncode=1, stderr="timeline failed")
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, returncode=1, stderr="reviews failed")
        ),
    )
    with pytest.raises(ValueError, match="Unable to inspect prior reviewer activity"):
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
            else _completed(args, stdout="{bad")
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unable to parse prior reviewer activity"):
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
            else _completed(args, stdout='{"body":"not-a-list"}\n')
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
            else _completed(args, stdout='{"data":null,"errors":[{"message":"boom"}]}')
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unexpected prior reviewer activity payload"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )

    repo_calls = {"count": 0}

    def fake_second_repo_failure(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout='{"number":290,"headRefOid":"head-sha-current"}\n')
        if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]:
            repo_calls["count"] += 1
            if repo_calls["count"] == 1:
                return _completed(args, stdout="example/repo\n")
            return _completed(args, returncode=1, stderr="repo failed")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout=_timeline_payload())
        return _completed(args, stdout="[]\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_second_repo_failure)
    with pytest.raises(ValueError, match="Unable to determine PR metadata"):
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
            else _completed(args, returncode=1, stderr="repo failed")
            if args[:6] == ["gh", "repo", "view", "--json", "nameWithOwner", "--jq"]
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unable to determine PR metadata"):
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
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, returncode=1, stderr="reviews failed")
        ),
    )
    with pytest.raises(ValueError, match="Unable to inspect prior reviewer activity"):
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
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="{bad")
        ),
    )
    with pytest.raises(ValueError, match="Unable to parse prior reviewer activity"):
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
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout='{"bad":"payload"}\n')
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
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout='["bad"]\n')
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
            else _completed(args, stdout=_timeline_payload())
            if args[:3] == ["gh", "api", "graphql"]
            else _completed(args, stdout="[[1]]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unexpected prior reviewer activity payload"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
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
