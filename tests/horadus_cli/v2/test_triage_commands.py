from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.triage_commands as triage_commands_module
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


def test_main_triage_collect_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "triage",
            "collect",
            "--keyword",
            "agent",
            "--lookback-days",
            "14",
            "--format",
            "json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["lookback_days"] == 14
    assert "current_sprint" in payload["data"]
    assert payload["data"]["searches"]["include_raw"] is False
    assert "keyword_hits" in payload["data"]["searches"]


def test_main_triage_collect_includes_overdue_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = main(["triage", "collect", "--lookback-days", "14", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    overdue = payload["data"]["current_sprint"]["overdue_human_blockers"]
    assert overdue == []


def test_main_triage_collect_ignores_stale_metadata_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-189` Restrict `/health` `[REQUIRES_HUMAN]`",
                "",
                "## Human Blocker Metadata",
                "- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
                "- TASK-999 | owner=human-operator | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "current_sprint_path", lambda: sprint_path)
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = main(["triage", "collect", "--lookback-days", "14", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    blockers = payload["data"]["current_sprint"]["human_blockers"]
    overdue = payload["data"]["current_sprint"]["overdue_human_blockers"]
    assert [item["task_id"] for item in blockers] == ["TASK-189"]
    assert [item["task_id"] for item in overdue] == ["TASK-189"]


def test_main_triage_collect_text_highlights_overdue_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = main(["triage", "collect", "--lookback-days", "14"])

    assert result == 0
    output = capsys.readouterr().out
    assert "- overdue_human_blockers=0" in output
    assert "- overdue_tasks=" not in output


def test_recent_assessment_paths_skips_invalid_dates_and_honors_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment_dir = tmp_path / "artifacts" / "assessments" / "ops" / "daily"
    assessment_dir.mkdir(parents=True)
    (assessment_dir / "2026-03-06.md").write_text("ok", encoding="utf-8")
    (assessment_dir / "2026-02-10.md").write_text("old", encoding="utf-8")
    (assessment_dir / "invalid.md").write_text("bad", encoding="utf-8")

    class _FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 3, 7, tzinfo=UTC)

    monkeypatch.setattr(triage_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_commands_module, "datetime", _FakeDatetime)

    paths = triage_commands_module._recent_assessment_paths(lookback_days=7)

    assert paths == ["artifacts/assessments/ops/daily/2026-03-06.md"]


def test_compile_or_pattern_and_handle_collect_cover_optional_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert triage_commands_module._compile_or_pattern([" ", "alpha", "beta?"]) == "alpha|beta\\?"
    assert triage_commands_module._compile_or_pattern([" ", ""]) is None

    active_task = task_repo_module.ActiveTask(
        task_id="TASK-253",
        title="Coverage task",
        requires_human=False,
        note=None,
        raw_line="- `TASK-253` Coverage task",
    )
    record = task_repo_module.TaskRecord(
        task_id="TASK-253",
        title="Coverage task",
        priority="P2",
        estimate="1-2 hours",
        description=["Agent-focused backlog review support."],
        files=["`src/core`"],
        acceptance_criteria=["- [ ] Preserve agent-friendly JSON"],
        assessment_refs=[],
        raw_block="### TASK-253: Coverage task",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
        source_path="tasks/BACKLOG.md",
    )

    monkeypatch.setattr(triage_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_commands_module, "backlog_path", lambda: tmp_path / "BACKLOG.md")
    monkeypatch.setattr(
        triage_commands_module,
        "backlog_task_records",
        lambda: {"TASK-253": record},
    )
    monkeypatch.setattr(triage_commands_module, "completed_path", lambda: tmp_path / "COMPLETED.md")
    monkeypatch.setattr(triage_commands_module, "completed_task_ids", lambda: set())
    monkeypatch.setattr(
        triage_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        triage_commands_module,
        "_recent_assessment_paths",
        lambda _lookback_days: ["artifacts/assessments/ops/daily/2026-03-06.md"],
    )
    monkeypatch.setattr(
        triage_commands_module,
        "line_search",
        lambda path, _pattern: (
            [
                task_repo_module.SearchHit(
                    source="artifacts/assessments/ops/daily/2026-03-06.md",
                    line_number=1,
                    line="PROPOSAL-1 references TASK-253",
                )
            ]
            if path == tmp_path / "artifacts" / "assessments" / "ops" / "daily" / "2026-03-06.md"
            else []
        ),
    )
    monkeypatch.setattr(triage_commands_module, "parse_active_tasks", lambda: [active_task])
    monkeypatch.setattr(triage_commands_module, "parse_human_blockers", lambda **_kwargs: [])

    def _task_record(
        task_id: str,
        *,
        include_archive: bool = False,
    ) -> task_repo_module.TaskRecord | None:
        assert include_archive is False or include_archive is True
        return record if task_id == "TASK-253" else None

    monkeypatch.setattr(
        triage_commands_module,
        "task_record",
        _task_record,
    )

    result = triage_commands_module.handle_collect(
        argparse.Namespace(
            keyword=["agent"],
            path=["src/core"],
            proposal_id=["PROPOSAL-1"],
            lookback_days=14,
            include_raw=False,
        )
    )

    assert result.lines is not None
    assert "- paths=src/core" in result.lines
    assert "- proposal_ids=PROPOSAL-1" in result.lines
    assert "- keyword_tasks=TASK-253" in result.lines
    assert all("overdue_tasks=" not in line for line in result.lines)
    assert result.data is not None
    assert result.data["searches"]["include_raw"] is False
    assert result.data["searches"]["keyword_hits"][0]["matched_fields"] == [
        "description",
        "acceptance_criteria",
    ]
    assert result.data["searches"]["path_hits"][0]["contexts"][0]["field"] == "files"
    assert result.data["searches"]["proposal_hits"][0]["task_id"] == "TASK-253"
    assert "raw_hits" not in result.data["searches"]["keyword_hits"][0]


def test_handle_collect_can_include_raw_line_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backlog_path = tmp_path / "BACKLOG.md"
    backlog_path.write_text(
        "\n".join(
            [
                "### TASK-253: Coverage task",
                "**Priority**: P2",
                "**Estimate**: 1-2 hours",
                "Agent-focused backlog review support.",
                "",
                "---",
            ]
        ),
        encoding="utf-8",
    )
    record = task_repo_module.TaskRecord(
        task_id="TASK-253",
        title="Coverage task",
        priority="P2",
        estimate="1-2 hours",
        description=["Agent-focused backlog review support."],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="### TASK-253: Coverage task",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
        source_path="tasks/BACKLOG.md",
    )

    monkeypatch.setattr(triage_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_commands_module, "backlog_path", lambda: backlog_path)
    monkeypatch.setattr(
        triage_commands_module,
        "backlog_task_records",
        lambda: {"TASK-253": record},
    )
    monkeypatch.setattr(triage_commands_module, "completed_path", lambda: tmp_path / "COMPLETED.md")
    monkeypatch.setattr(triage_commands_module, "completed_task_ids", lambda: set())
    monkeypatch.setattr(
        triage_commands_module,
        "_recent_assessment_paths",
        lambda _lookback_days: [],
    )
    monkeypatch.setattr(
        triage_commands_module,
        "line_search",
        lambda path, _pattern: (
            [
                task_repo_module.SearchHit(
                    source="tasks/BACKLOG.md",
                    line_number=4,
                    line="Agent-focused backlog review support.",
                )
            ]
            if path == backlog_path
            else []
        ),
    )
    monkeypatch.setattr(triage_commands_module, "parse_active_tasks", list)
    monkeypatch.setattr(triage_commands_module, "parse_human_blockers", lambda **_kwargs: [])

    result = triage_commands_module.handle_collect(
        argparse.Namespace(
            keyword=["agent"],
            path=[],
            proposal_id=[],
            lookback_days=14,
            include_raw=True,
        )
    )

    assert result.data is not None
    keyword_hit = result.data["searches"]["keyword_hits"][0]
    assert result.data["searches"]["include_raw"] is True
    assert keyword_hit["raw_hits"][0]["source"] == "tasks/BACKLOG.md"
    assert keyword_hit["raw_hits"][0]["line_number"] == 4
