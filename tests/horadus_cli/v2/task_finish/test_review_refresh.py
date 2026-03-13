from __future__ import annotations

import subprocess

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


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
        if args[:3] == ["gh", "api", "--paginate"]:
            return _completed(args, stdout="[]\n")
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
        if args[:3] == ["gh", "api", "--paginate"]:
            return _completed(args, stdout="[]\n")
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
            else _completed(args, stdout="[]\n")
            if args[:3] == ["gh", "api", "--paginate"]
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
                stdout='[[{"body":"@codex review\\n<!-- horadus:fresh-review reviewer=chatgpt-codex-connector[bot] head=head-sha-290 -->"}]]\n',
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
            else _completed(args, stdout="[]\n")
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
            else _completed(args, returncode=1, stderr="comments failed")
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
            else _completed(args, stdout='[["ok"], ["bad"]]\n')
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
            else _completed(args, stdout='{"body":"not-a-list"}\n')
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
            else _completed(args, stdout="[[1]]\n")
        ),
    )
    with pytest.raises(ValueError, match="Unexpected prior reviewer activity payload"):
        task_commands_module._needs_pre_review_fresh_review_request(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
