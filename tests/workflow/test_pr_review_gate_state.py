from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.pr_review_gate_state as review_gate_state_module


def test_persisted_wait_window_started_at_reuses_same_head_state(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "review-gate-state.json"
    original_started_at = datetime(2026, 3, 15, 18, 0, tzinfo=UTC)
    state_path.write_text(
        json.dumps(
            {
                "example/repo#215#bot": {
                    "head_oid": "head-sha",
                    "started_at": original_started_at.isoformat(),
                }
            }
        )
    )
    monkeypatch.setenv("HORADUS_REVIEW_GATE_STATE_PATH", str(state_path))

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
        now=datetime(2026, 3, 15, 19, 0, tzinfo=UTC),
    )

    assert persisted_started_at == original_started_at


def test_persisted_wait_window_started_at_resets_for_new_head(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "review-gate-state.json"
    state_path.write_text(
        json.dumps(
            {
                "example/repo#215#bot": {
                    "head_oid": "head-old",
                    "started_at": "2026-03-15T18:00:00+00:00",
                }
            }
        )
    )
    monkeypatch.setenv("HORADUS_REVIEW_GATE_STATE_PATH", str(state_path))
    now = datetime(2026, 3, 15, 19, 0, tzinfo=UTC)

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-new",
        now=now,
    )

    assert persisted_started_at == now
    payload = json.loads(state_path.read_text())
    assert payload["example/repo#215#bot"]["head_oid"] == "head-new"


def test_persisted_wait_window_started_at_recovers_from_invalid_state_payload(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "review-gate-state.json"
    state_path.write_text("{bad")
    monkeypatch.setenv("HORADUS_REVIEW_GATE_STATE_PATH", str(state_path))
    now = datetime(2026, 3, 15, 19, 0, tzinfo=UTC)

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
        now=now,
    )

    assert persisted_started_at == now


def test_parse_github_timestamp_rejects_blank_and_invalid_values() -> None:
    assert review_gate_state_module._parse_github_timestamp("") is None
    assert review_gate_state_module._parse_github_timestamp("not-a-timestamp") is None


def test_persisted_wait_window_started_at_handles_missing_file_and_invalid_timestamp(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "review-gate-state.json"
    monkeypatch.setenv("HORADUS_REVIEW_GATE_STATE_PATH", str(state_path))
    now = datetime(2026, 3, 15, 19, 0, tzinfo=UTC)

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
        now=now,
    )

    assert persisted_started_at == now

    state_path.write_text(
        json.dumps(
            {
                "example/repo#215#bot": {
                    "head_oid": "head-sha",
                    "started_at": "bad-timestamp",
                }
            }
        )
    )

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
        now=now,
    )

    assert persisted_started_at == now


def test_persisted_wait_window_started_at_returns_now_when_state_write_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "review-gate-state.json"
    monkeypatch.setenv("HORADUS_REVIEW_GATE_STATE_PATH", str(state_path))
    now = datetime(2026, 3, 15, 19, 0, tzinfo=UTC)

    def _raise_write_error(self: Path, *_args, **_kwargs) -> int:
        if self == state_path:
            raise OSError("disk full")
        return original_write_text(self, *_args, **_kwargs)

    original_write_text = Path.write_text
    monkeypatch.setattr(Path, "write_text", _raise_write_error)

    persisted_started_at = review_gate_state_module.persisted_wait_window_started_at(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
        now=now,
    )

    assert persisted_started_at == now


def test_review_gate_state_path_defaults_under_repo_git_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HORADUS_REVIEW_GATE_STATE_PATH", raising=False)

    state_path = review_gate_state_module._review_gate_state_path()

    assert state_path.name == "review_gate_windows.json"
    assert state_path.parent.name == "horadus"
    assert state_path.parent.parent.name == ".git"


def test_start_wait_window_delegates_with_utc_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = datetime(2026, 3, 15, 19, 0, tzinfo=UTC)
    captured: dict[str, object] = {}

    def _fake_persisted_wait_window_started_at(**kwargs: object) -> datetime:
        captured.update(kwargs)
        return expected

    def _fake_now(*, tz: object) -> datetime:
        assert tz == UTC
        return expected

    fake_datetime = type(
        "FakeDateTime",
        (),
        {"now": staticmethod(_fake_now)},
    )
    monkeypatch.setattr(
        review_gate_state_module,
        "persisted_wait_window_started_at",
        _fake_persisted_wait_window_started_at,
    )
    monkeypatch.setattr(review_gate_state_module, "datetime", fake_datetime)

    started_at = review_gate_state_module.start_wait_window(
        repo="example/repo",
        pr_number=215,
        reviewer_login="bot",
        head_oid="head-sha",
    )

    assert started_at == expected
    assert captured == {
        "repo": "example/repo",
        "pr_number": 215,
        "reviewer_login": "bot",
        "head_oid": "head-sha",
        "now": expected,
    }
