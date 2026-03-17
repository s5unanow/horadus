from __future__ import annotations

from datetime import UTC, datetime

import pytest

import tools.horadus.python.horadus_workflow.pr_review_gate as pr_review_gate_module
import tools.horadus.python.horadus_workflow.pr_review_gate_outcomes as pr_review_gate_outcomes


def test_pr_review_gate_context_inference_and_json_decode_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert pr_review_gate_module._infer_json_context(("repo", "view")) == "repository metadata"
    assert (
        pr_review_gate_module._infer_json_context(
            ("pr", "view", "x", "--json", "number,headRefOid")
        )
        == "pull request metadata"
    )
    assert (
        pr_review_gate_module._infer_json_context(("api", "repos/example/repo/pulls/1/comments"))
        == "review comments"
    )
    assert (
        pr_review_gate_module._infer_json_context(("api", "repos/example/repo/issues/1/reactions"))
        == "PR summary reactions"
    )
    assert (
        pr_review_gate_module._infer_json_context(("api", "repos/example/repo/issues/1/comments"))
        == "issue comments"
    )
    assert pr_review_gate_module._infer_json_context(("git", "status")) == "GitHub JSON payload"
    assert (
        pr_review_gate_module._infer_json_context(("api", "repos/example/repo/other"))
        == "GitHub JSON payload"
    )

    attempts = {"count": 0}

    def fake_run_gh(*_args: str) -> str:
        attempts["count"] += 1
        return "{bad"

    monkeypatch.setattr(pr_review_gate_module, "_run_gh", fake_run_gh)

    with pytest.raises(pr_review_gate_module.GhError, match="Unable to parse PR summary reactions"):
        pr_review_gate_module._run_gh_paginated_json("repos/example/repo/issues/1/reactions")

    assert attempts["count"] == 2


def test_initial_review_loop_state_keeps_present_started_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: ("example/repo", 1, "head-sha"),
    )
    monkeypatch.setattr(
        pr_review_gate_module.pr_review_gate_state,
        "start_wait_window",
        lambda **_kwargs: started_at,
    )
    monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: started_at.timestamp())

    loop_context = pr_review_gate_module._initial_review_loop_state(
        pr_url="https://example.invalid/pr/1",
        reviewer_login="bot",
        timeout_seconds=30,
    )

    assert loop_context.wait_window_started_at == started_at
    assert loop_context.deadline_epoch == started_at.timestamp() + 30


def test_emit_outcome_waiting_prints_informational_lines_and_json_wait_branch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    waiting_outcome = pr_review_gate_module.ReviewGateOutcome(
        status="waiting",
        reason="waiting",
        reviewer_login="bot",
        reviewed_head_oid="head-sha",
        current_head_oid="head-sha",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=1,
        timed_out=False,
        summary="Waiting for review gate ...",
        informational_lines=("info-line",),
    )
    assert pr_review_gate_module._emit_outcome(waiting_outcome, output_format="text") == 0
    assert "info-line" in capsys.readouterr().out

    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: ("example/repo", 1, "head-sha"),
    )
    monkeypatch.setattr(pr_review_gate_module, "_current_head_oid", lambda _pr_url: "head-sha")
    monkeypatch.setattr(
        pr_review_gate_module,
        "_matching_review_comments",
        lambda **_kwargs: ([], [], []),
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: False)
    values = iter([0.0, 0.0, 2.0, 2.0, 2.0, 2.0])
    sleep_calls: list[int] = []
    monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: next(values, 2.0))
    monkeypatch.setattr(
        pr_review_gate_module.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    assert (
        pr_review_gate_module.main(
            [
                "--pr-url",
                "https://example.invalid/pr/1",
                "--timeout-seconds",
                "1",
                "--poll-seconds",
                "1",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert sleep_calls == [1]


def test_pr_review_gate_outcomes_waiting_path_uses_current_time() -> None:
    loop_context = pr_review_gate_module.pr_review_gate_window.ReviewLoopContext(
        repo="example/repo",
        pr_number=1,
        head_oid="head-sha",
        wait_window_started_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
        deadline_epoch=10.0,
    )

    outcome = pr_review_gate_outcomes.approval_or_timeout_outcome(
        reviewer_login="bot",
        loop_context=loop_context,
        timeout_seconds=30,
        timeout_policy="allow",
        informational_lines=(),
        has_pr_summary_thumbs_up=False,
        saw_clean_current_head_review=False,
        current_time=0.0,
    )

    assert outcome.status == "waiting"


def test_run_gh_graphql_json_builds_expected_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_gh_json_command(args: tuple[str, ...] | list[str], *, context: str) -> object:
        captured["args"] = list(args)
        captured["context"] = context
        return {"ok": True}

    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json_command", fake_run_gh_json_command)

    payload = pr_review_gate_module._run_gh_graphql_json(
        query="query { viewer { login } }",
        fields={"owner": "example", "repo": "repo"},
        context="graphql test",
    )

    assert payload == {"ok": True}
    assert captured == {
        "args": [
            "api",
            "graphql",
            "-f",
            "query=query { viewer { login } }",
            "-F",
            "owner=example",
            "-F",
            "repo=repo",
        ],
        "context": "graphql test",
    }


def test_matching_review_comments_falls_back_to_graphql_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_paginated(endpoint: str) -> object:
        calls.append(("rest", endpoint))
        raise pr_review_gate_module.GhError("gh api failed: API rate limit exceeded")

    def fake_graphql_reviews_and_comments(
        **kwargs: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        calls.append(("graphql", str(kwargs["repo"])))
        return (
            [{"id": 1, "state": "COMMENTED", "user": {"login": "bot"}, "commit_id": "head"}],
            [],
        )

    monkeypatch.setattr(pr_review_gate_module, "_run_gh_paginated_json", fake_paginated)
    monkeypatch.setattr(
        pr_review_gate_module.pr_review_gate_graphql,
        "graphql_reviews_and_comments",
        fake_graphql_reviews_and_comments,
    )

    matching_reviews, matching_comments, actionable_reviews = (
        pr_review_gate_module._matching_review_comments(
            repo="example/repo",
            pr_number=215,
            head_oid="head",
            reviewer_login="bot",
        )
    )

    assert len(matching_reviews) == 1
    assert matching_comments == []
    assert actionable_reviews == []
    assert calls == [
        ("rest", "repos/example/repo/pulls/215/reviews"),
        ("graphql", "example/repo"),
    ]


def test_has_pr_summary_thumbs_up_falls_back_to_graphql_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pr_review_gate_module,
        "_run_gh_paginated_json",
        lambda _endpoint: (_ for _ in ()).throw(
            pr_review_gate_module.GhError("gh api failed: API rate limit exceeded")
        ),
    )
    monkeypatch.setattr(
        pr_review_gate_module.pr_review_gate_graphql,
        "graphql_reactions",
        lambda **_kwargs: [
            {
                "content": "+1",
                "created_at": "2026-03-17T12:00:00+00:00",
                "user": {"login": "bot"},
            }
        ],
    )
    monkeypatch.setattr(
        pr_review_gate_module,
        "_latest_current_head_review_request_at",
        lambda **_kwargs: datetime(2026, 3, 17, 11, 59, tzinfo=UTC),
    )

    assert (
        pr_review_gate_module._has_pr_summary_thumbs_up(
            repo="example/repo",
            pr_number=215,
            reviewer_login="bot",
            head_oid="head",
            wait_window_started_at=datetime(2026, 3, 17, 11, 58, tzinfo=UTC),
        )
        is True
    )
