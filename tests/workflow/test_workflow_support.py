from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.horadus.python.horadus_workflow.pr_review_gate as pr_review_gate_module
import tools.horadus.python.horadus_workflow.review_defaults as review_defaults_module
import tools.horadus.python.horadus_workflow.task_repo as task_repo_module
import tools.horadus.python.horadus_workflow.triage as triage_module

pytestmark = pytest.mark.unit


def _fixed_cwd(_cls: type[Path], discovered_root: Path) -> Path:
    return discovered_root


def _fake_subprocess_ok(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout='{"ok": true}\n', stderr="")


def _fake_subprocess_error(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="", stderr="boom")


def test_compatibility_wrappers_alias_new_owners() -> None:
    assert importlib.import_module("src.core.docs_freshness") is importlib.import_module(
        "tools.horadus.python.horadus_workflow.docs_freshness"
    )
    assert importlib.import_module("src.core.repo_workflow") is importlib.import_module(
        "tools.horadus.python.horadus_workflow.repo_workflow"
    )
    assert importlib.import_module(
        "src.horadus_cli.v2.task_workflow_policy"
    ) is importlib.import_module("tools.horadus.python.horadus_workflow.task_workflow_policy")


def test_task_repo_root_override_env_and_discovery_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_root = tmp_path / "env-root"
    env_root.mkdir()
    monkeypatch.setenv("HORADUS_REPO_ROOT", str(env_root))
    task_repo_module.clear_repo_root_override()
    assert task_repo_module.repo_root() == env_root.resolve()

    monkeypatch.delenv("HORADUS_REPO_ROOT", raising=False)
    override_root = tmp_path / "override-root"
    override_root.mkdir()
    task_repo_module.set_repo_root_override(override_root)
    assert task_repo_module.repo_root() == override_root.resolve()
    monkeypatch.setenv("HORADUS_REPO_ROOT", str(env_root))
    assert task_repo_module.repo_root() == override_root.resolve()
    monkeypatch.delenv("HORADUS_REPO_ROOT", raising=False)
    task_repo_module.clear_repo_root_override()
    assert task_repo_module._REPO_ROOT_OVERRIDE is None

    discovered_root = tmp_path / "discovered-root"
    (discovered_root / "tasks").mkdir(parents=True)
    (discovered_root / "pyproject.toml").write_text("[project]\nname='horadus'\n", encoding="utf-8")
    monkeypatch.setattr(
        task_repo_module.Path, "cwd", classmethod(lambda _cls: _fixed_cwd(_cls, discovered_root))
    )
    monkeypatch.setattr(
        task_repo_module, "_looks_like_repo_root", lambda path: path == discovered_root
    )
    assert task_repo_module._discover_repo_root() == discovered_root


def test_task_repo_root_discovery_raises_when_no_repo_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HORADUS_REPO_ROOT", raising=False)
    task_repo_module.clear_repo_root_override()
    monkeypatch.setattr(task_repo_module, "_looks_like_repo_root", lambda _path: False)
    with pytest.raises(RuntimeError, match="Unable to locate Horadus repo root"):
        task_repo_module._discover_repo_root()


def test_workflow_triage_helpers_cover_recent_paths_and_patterns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    triage = importlib.reload(triage_module)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: UTC | None = None) -> datetime:
            assert tz is UTC
            return cls(2026, 3, 11, tzinfo=UTC)

    daily_dir = tmp_path / "artifacts" / "assessments" / "alpha" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-03-10.md").write_text("recent\n", encoding="utf-8")
    (daily_dir / "2026-02-01.md").write_text("old\n", encoding="utf-8")
    (daily_dir / "not-a-date.md").write_text("skip\n", encoding="utf-8")

    monkeypatch.setattr(triage, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage, "datetime", _FakeDatetime)

    assert triage._recent_assessment_paths(lookback_days=7) == [
        "artifacts/assessments/alpha/daily/2026-03-10.md"
    ]
    assert triage._compile_or_pattern([" ", "alpha", "beta?"]) == "alpha|beta\\?"
    assert triage._compile_or_pattern([" ", ""]) is None


def test_workflow_triage_handle_collect_returns_expected_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    triage = importlib.reload(triage_module)

    @dataclass
    class _ActiveTask:
        task_id: str

    @dataclass
    class _Urgency:
        is_overdue: bool

    @dataclass
    class _Blocker:
        task_id: str
        urgency: _Urgency | None

    @dataclass
    class _Hit:
        path: str
        line_number: int
        line_text: str

    active_task = _ActiveTask(task_id="TASK-123")
    overdue = _Blocker(task_id="TASK-123", urgency=_Urgency(is_overdue=True))

    monkeypatch.setattr(triage, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage, "completed_path", lambda: tmp_path / "tasks" / "COMPLETED.md")
    monkeypatch.setattr(
        triage,
        "current_sprint_path",
        lambda: tmp_path / "tasks" / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(triage, "_recent_assessment_paths", lambda _days: ["artifacts/x.md"])
    monkeypatch.setattr(
        triage,
        "line_search",
        lambda path, pattern: [
            _Hit(path=str(path), line_number=1, line_text=f"{pattern}:{Path(path).name}")
        ],
    )
    monkeypatch.setattr(triage, "parse_active_tasks", lambda: [active_task])
    monkeypatch.setattr(triage, "parse_human_blockers", lambda **_kwargs: [overdue])

    result = triage.handle_collect(
        SimpleNamespace(
            keyword=["alpha"],
            path=["src/core"],
            proposal_id=["P-1"],
            lookback_days=14,
        )
    )

    assert result.exit_code == 0
    assert result.data is not None
    assert result.data["recent_assessments"] == ["artifacts/x.md"]
    assert result.data["current_sprint"]["overdue_human_blockers"][0]["task_id"] == "TASK-123"
    assert result.lines is not None
    assert any("keyword_hits=2" in line for line in result.lines)


def test_pr_review_gate_helper_functions_cover_success_and_error_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        pr_review_gate_module.DEFAULT_REVIEW_TIMEOUT_SECONDS
        == review_defaults_module.DEFAULT_REVIEW_TIMEOUT_SECONDS
    )

    monkeypatch.setattr(
        pr_review_gate_module.subprocess,
        "run",
        _fake_subprocess_ok,
    )
    assert pr_review_gate_module._run_gh("api", "x") == '{"ok": true}\n'
    assert pr_review_gate_module._run_gh_json("api", "x") == {"ok": True}

    monkeypatch.setattr(
        pr_review_gate_module.subprocess,
        "run",
        _fake_subprocess_error,
    )
    with pytest.raises(pr_review_gate_module.GhError, match="gh api x failed: boom"):
        pr_review_gate_module._run_gh("api", "x")

    monkeypatch.setattr(
        pr_review_gate_module,
        "_run_gh",
        lambda *args: "" if args[-1] == "empty" else '{"nameWithOwner":"example/repo"}',
    )
    assert pr_review_gate_module._run_gh_json("api", "empty") is None

    payloads: dict[tuple[str, ...], object] = {
        ("repo", "view", "--json", "nameWithOwner"): {"nameWithOwner": "example/repo"},
        ("pr", "view", "https://example.invalid/pr/1", "--json", "number,headRefOid,url"): {
            "number": 1,
            "headRefOid": "head-sha",
            "url": "https://example.invalid/pr/1",
        },
        ("repos/example/repo/pulls/1/reviews",): [
            [
                {
                    "id": 11,
                    "commit_id": "head-sha",
                    "state": "APPROVED",
                    "body": "",
                    "user": {"login": "bot"},
                },
                {"id": 12, "commit_id": "old-sha", "user": {"login": "bot"}},
            ]
        ],
        ("repos/example/repo/pulls/1/comments",): [
            [{"pull_request_review_id": 11, "user": {"login": "bot"}, "path": "a.py", "line": 7}]
        ],
        ("repos/example/repo/issues/1/reactions",): [
            [
                {
                    "content": "+1",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                    "user": {"login": "bot"},
                }
            ]
        ],
    }
    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json", lambda *args: payloads[args])
    monkeypatch.setattr(
        pr_review_gate_module, "_run_gh_paginated_json", lambda *args: payloads[args]
    )

    assert pr_review_gate_module._review_context("https://example.invalid/pr/1") == (
        "example/repo",
        1,
        "head-sha",
    )
    matching_reviews, matching_comments, actionable_reviews = (
        pr_review_gate_module._matching_review_comments(
            repo="example/repo",
            pr_number=1,
            head_oid="head-sha",
            reviewer_login="bot",
        )
    )
    assert len(matching_reviews) == 1
    assert len(matching_comments) == 1
    assert actionable_reviews == []
    assert pr_review_gate_module._parse_github_timestamp("bad-timestamp") is None
    assert pr_review_gate_module._parse_github_timestamp(" ") is None
    assert pr_review_gate_module._has_pr_summary_thumbs_up(
        repo="example/repo",
        pr_number=1,
        reviewer_login="bot",
        wait_window_started_at=datetime.now(tz=UTC) - timedelta(seconds=1),
    )

    pr_review_gate_module._print_actionable_comments(
        [
            {
                "path": "a.py",
                "line": 7,
                "html_url": "https://example.invalid/c/1",
                "body": " Needs fix ",
            }
        ]
    )
    assert "a.py:7" in capsys.readouterr().out
    pr_review_gate_module._print_actionable_comments(
        [{"path": "b.py", "original_line": 9, "html_url": "", "body": ""}]
    )
    assert "b.py:9" in capsys.readouterr().out

    bad_payloads = dict(payloads)
    bad_payloads[("repo", "view", "--json", "nameWithOwner")] = {}
    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json", lambda *args: bad_payloads[args])
    with pytest.raises(pr_review_gate_module.GhError, match="repository name"):
        pr_review_gate_module._review_context("https://example.invalid/pr/1")

    bad_pr_payloads = dict(payloads)
    bad_pr_payloads[
        ("pr", "view", "https://example.invalid/pr/1", "--json", "number,headRefOid,url")
    ] = {}
    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json", lambda *args: bad_pr_payloads[args])
    with pytest.raises(pr_review_gate_module.GhError, match="PR number/headRefOid"):
        pr_review_gate_module._review_context("https://example.invalid/pr/1")

    monkeypatch.setattr(
        pr_review_gate_module,
        "_run_gh_paginated_json",
        lambda *args: {} if args[-1].endswith("/reviews") else [[]],
    )
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected reviews payload"):
        pr_review_gate_module._matching_review_comments(
            repo="example/repo",
            pr_number=1,
            head_oid="head-sha",
            reviewer_login="bot",
        )

    monkeypatch.setattr(
        pr_review_gate_module,
        "_run_gh_paginated_json",
        lambda *args: [[]] if args[-1].endswith("/reviews") else {},
    )
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected comments payload"):
        pr_review_gate_module._matching_review_comments(
            repo="example/repo",
            pr_number=1,
            head_oid="head-sha",
            reviewer_login="bot",
        )

    monkeypatch.setattr(pr_review_gate_module, "_run_gh_paginated_json", lambda *_args: {})
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected reactions payload"):
        pr_review_gate_module._has_pr_summary_thumbs_up(
            repo="example/repo",
            pr_number=1,
            reviewer_login="bot",
            wait_window_started_at=datetime.now(tz=UTC),
        )


def test_pr_review_gate_uses_latest_current_head_review_state_for_summary_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: dict[tuple[str, ...], object] = {
        ("repos/example/repo/pulls/1/reviews",): [
            [
                {
                    "id": 11,
                    "commit_id": "head-sha",
                    "state": "COMMENTED",
                    "body": "Please revise",
                    "submitted_at": "2026-03-12T10:00:00Z",
                    "user": {"login": "bot"},
                },
                {
                    "id": 12,
                    "commit_id": "head-sha",
                    "state": "APPROVED",
                    "body": "",
                    "submitted_at": "2026-03-12T10:05:00Z",
                    "user": {"login": "bot"},
                },
            ]
        ],
        ("repos/example/repo/pulls/1/comments",): [[]],
    }
    monkeypatch.setattr(
        pr_review_gate_module, "_run_gh_paginated_json", lambda *args: payloads[args]
    )

    matching_reviews, matching_comments, actionable_reviews = (
        pr_review_gate_module._matching_review_comments(
            repo="example/repo",
            pr_number=1,
            head_oid="head-sha",
            reviewer_login="bot",
        )
    )

    assert len(matching_reviews) == 2
    assert matching_comments == []
    assert actionable_reviews == []


def test_pr_review_gate_helper_functions_cover_additional_contract_edges(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pr_review_gate_module, "_run_gh", lambda *_args: "")
    assert (
        pr_review_gate_module._run_gh_paginated_json("repos/example/repo/pulls/1/reviews") is None
    )
    monkeypatch.setattr(pr_review_gate_module, "_run_gh", lambda *_args: '[{"id": 1}]')
    assert pr_review_gate_module._run_gh_paginated_json("repos/example/repo/pulls/1/reviews") == [
        {"id": 1}
    ]

    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json", lambda *_args: {})
    with pytest.raises(pr_review_gate_module.GhError, match="current PR headRefOid"):
        pr_review_gate_module._current_head_oid("https://example.invalid/pr/1")

    monkeypatch.setattr(pr_review_gate_module, "_run_gh_json", lambda *_args: {"headRefOid": " "})
    with pytest.raises(pr_review_gate_module.GhError, match="current PR headRefOid"):
        pr_review_gate_module._current_head_oid("https://example.invalid/pr/1")
    monkeypatch.setattr(
        pr_review_gate_module, "_run_gh_json", lambda *_args: {"headRefOid": "head-a"}
    )
    assert pr_review_gate_module._current_head_oid("https://example.invalid/pr/1") == "head-a"

    assert pr_review_gate_module._flatten_paginated_list([], label="reviews") == []
    assert pr_review_gate_module._flatten_paginated_list([{"id": 1}], label="reviews") == [
        {"id": 1}
    ]
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected reviews payload"):
        pr_review_gate_module._flatten_paginated_list({}, label="reviews")
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected reviews payload"):
        pr_review_gate_module._flatten_paginated_list([{"id": 1}, "bad"], label="reviews")
    with pytest.raises(pr_review_gate_module.GhError, match="unexpected reviews payload"):
        pr_review_gate_module._flatten_paginated_list([["bad"]], label="reviews")
    assert pr_review_gate_module._user_login({"user": {"login": "bot"}}) == "bot"
    assert pr_review_gate_module._user_login({"user": {}}) is None
    assert pr_review_gate_module._user_login({}) is None
    assert pr_review_gate_module._actionable_review_lines([{"state": "COMMENTED"}]) == [
        "- COMMENTED"
    ]

    outcome = pr_review_gate_module.ReviewGateOutcome(
        status="block",
        reason="actionable_reviews",
        reviewer_login="bot",
        reviewed_head_oid="head-a",
        current_head_oid="head-a",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=1,
        timeout_seconds=600,
        timed_out=False,
        summary="summary",
        actionable_lines=("line",),
    )
    assert pr_review_gate_module._emit_outcome(outcome, output_format="json") == 2
    payload = capsys.readouterr().out
    assert '"status": "block"' in payload

    timeout_outcome = pr_review_gate_module.ReviewGateOutcome(
        status="block",
        reason="timeout_fail",
        reviewer_login="bot",
        reviewed_head_oid="head-a",
        current_head_oid="head-a",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=600,
        timed_out=True,
        summary="timed out",
    )
    assert pr_review_gate_module._emit_outcome(timeout_outcome, output_format="json") == 1
    assert '"reason": "timeout_fail"' in capsys.readouterr().out

    head_changed_outcome = pr_review_gate_module.ReviewGateOutcome(
        status="head_changed",
        reason="head_changed",
        reviewer_login="bot",
        reviewed_head_oid="head-a",
        current_head_oid="head-b",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=600,
        timed_out=False,
        summary="head changed",
    )
    assert pr_review_gate_module._emit_outcome(head_changed_outcome, output_format="json") == 3
    assert '"status": "head_changed"' in capsys.readouterr().out

    pass_outcome = pr_review_gate_module.ReviewGateOutcome(
        status="pass",
        reason="silent_timeout_allow",
        reviewer_login="bot",
        reviewed_head_oid="head-a",
        current_head_oid="head-a",
        clean_current_head_review=False,
        summary_thumbs_up=False,
        actionable_comment_count=0,
        actionable_review_count=0,
        timeout_seconds=600,
        timed_out=True,
        summary="ok",
    )
    assert pr_review_gate_module._emit_outcome(pass_outcome, output_format="json") == 0
    assert '"status": "pass"' in capsys.readouterr().out

    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: (_ for _ in ()).throw(pr_review_gate_module.GhError("boom")),
    )
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 1
    assert "boom" in capsys.readouterr().err

    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: ("example/repo", 1, "head-a"),
    )
    monkeypatch.setattr(
        pr_review_gate_module,
        "_current_head_oid",
        lambda _pr_url: (_ for _ in ()).throw(pr_review_gate_module.GhError("head failed")),
    )
    monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: 0.0)
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 1
    assert "head failed" in capsys.readouterr().err


def test_pr_review_gate_main_covers_review_outcomes_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _install_fake_time(values: list[float]) -> None:
        iterator = iter(values)
        fallback = values[-1]
        monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: next(iterator, fallback))

    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: ("example/repo", 1, "head-sha"),
    )
    monkeypatch.setattr(pr_review_gate_module, "_current_head_oid", lambda _pr_url: "head-sha")

    _install_fake_time([0.0, 601.0])
    monkeypatch.setattr(pr_review_gate_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        pr_review_gate_module,
        "_matching_review_comments",
        lambda **_kwargs: (
            [],
            [{"path": "a.py", "line": 3, "html_url": "", "body": "comment"}],
            [],
        ),
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: False)
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 2

    monkeypatch.setattr(
        pr_review_gate_module,
        "_matching_review_comments",
        lambda **_kwargs: ([{"state": "APPROVED"}], [], []),
    )
    _install_fake_time([0.0, 601.0])
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 0

    monkeypatch.setattr(
        pr_review_gate_module, "_matching_review_comments", lambda **_kwargs: ([], [], [])
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: True)
    _install_fake_time([0.0])
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 0

    monkeypatch.setattr(
        pr_review_gate_module,
        "_matching_review_comments",
        lambda **_kwargs: ([{"state": "APPROVED"}], [], []),
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: True)
    _install_fake_time([0.0])
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 0

    monkeypatch.setattr(
        pr_review_gate_module, "_matching_review_comments", lambda **_kwargs: ([], [], [])
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: False)
    _install_fake_time([0.0, 0.0, 2.0])
    sleep_calls: list[int] = []
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
            ]
        )
        == 0
    )
    assert sleep_calls == [1]

    monkeypatch.setattr(
        pr_review_gate_module, "_matching_review_comments", lambda **_kwargs: ([], [], [])
    )
    _install_fake_time([0.0, 601.0])
    assert (
        pr_review_gate_module.main(
            [
                "--pr-url",
                "https://example.invalid/pr/1",
                "--timeout-seconds",
                "1",
                "--timeout-policy",
                "fail",
            ]
        )
        == 1
    )

    with pytest.raises(SystemExit):
        pr_review_gate_module.main(
            ["--pr-url", "https://example.invalid/pr/1", "--timeout-seconds", "0"]
        )
    with pytest.raises(SystemExit):
        pr_review_gate_module.main(
            ["--pr-url", "https://example.invalid/pr/1", "--poll-seconds", "-1"]
        )


def test_pr_review_gate_main_detects_head_change_and_summary_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pr_review_gate_module,
        "_review_context",
        lambda _pr_url: ("example/repo", 1, "head-a"),
    )
    monkeypatch.setattr(pr_review_gate_module, "_current_head_oid", lambda _pr_url: "head-b")
    monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: 0.0)
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 3

    monkeypatch.setattr(pr_review_gate_module, "_current_head_oid", lambda _pr_url: "head-a")
    monkeypatch.setattr(pr_review_gate_module.time, "time", lambda: 601.0)
    monkeypatch.setattr(pr_review_gate_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        pr_review_gate_module,
        "_matching_review_comments",
        lambda **_kwargs: (
            [
                {
                    "state": "COMMENTED",
                    "body": "Please revise",
                    "html_url": "https://example.invalid/r/1",
                }
            ],
            [],
            [
                {
                    "state": "COMMENTED",
                    "body": "Please revise",
                    "html_url": "https://example.invalid/r/1",
                }
            ],
        ),
    )
    monkeypatch.setattr(pr_review_gate_module, "_has_pr_summary_thumbs_up", lambda **_kwargs: False)
    assert pr_review_gate_module.main(["--pr-url", "https://example.invalid/pr/1"]) == 2
