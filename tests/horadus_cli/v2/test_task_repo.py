from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _seed_close_ledgers_repo

pytestmark = pytest.mark.unit


def test_parse_human_blockers_derives_urgency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    blockers = task_repo_module.parse_human_blockers()

    assert blockers
    urgency = blockers[0].urgency
    assert urgency is not None
    assert urgency.as_of == "2026-03-06"
    assert urgency.state == "overdue"
    assert urgency.days_until_next_action == -1
    assert urgency.is_overdue is True
    assert urgency.days_since_last_touched == 3


def test_parse_human_blockers_can_filter_to_active_task_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-189` Active blocker `[REQUIRES_HUMAN]`",
                "",
                "## Human Blocker Metadata",
                "- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
                "- TASK-999 | owner=human-operator | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path, task_ids={"TASK-189"})

    assert [blocker.task_id for blocker in blockers] == ["TASK-189"]


def test_task_repo_helper_functions_cover_validation_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text("# Current Sprint\n", encoding="utf-8")

    assert task_repo_module.normalize_task_id("253") == "TASK-253"
    assert task_repo_module.slugify_name(" Coverage Plan ") == "coverage-plan"
    with pytest.raises(ValueError, match="Invalid branch suffix"):
        task_repo_module.slugify_name("   ")
    with pytest.raises(ValueError, match="Unable to locate Active Tasks"):
        task_repo_module.active_section_text(sprint_path)
    assert task_repo_module.human_blocker_section_text(sprint_path) == ""

    urgency = task_repo_module.blocker_urgency(
        last_touched="bad-date",
        next_action="2026-03-06",
        escalate_after_days=0,
        as_of=task_repo_module.date(2026, 3, 6),
    )
    assert urgency.state == "due_today"
    assert urgency.days_since_last_touched is None


def test_task_repo_planning_helpers_cover_marker_and_path_edges(tmp_path: Path) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-905",
        title="fixture",
        priority=None,
        estimate=None,
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="**Planning Gates**: Required — fixture\n**Exec Plan**: Required (`tasks/exec_plans/README.md`)\n",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
        source_path="tasks/BACKLOG.md",
    )
    repo_tasks = tmp_path / "tasks" / "exec_plans"
    repo_tasks.mkdir(parents=True)
    (repo_tasks / "TASK-905.md").write_text("# plan\n", encoding="utf-8")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    try:
        assert task_repo_module.exec_plan_paths_for_task("TASK-905") == [
            "tasks/exec_plans/TASK-905.md"
        ]
    finally:
        monkeypatch.undo()

    assert task_repo_module.planning_gates_value_from_text(record.raw_block) == "Required — fixture"
    assert task_repo_module.planning_gates_value_from_text("no marker") is None
    assert task_repo_module.planning_gates_required("Required — reason") is True
    assert task_repo_module.planning_gates_required("`Required` — reason") is True
    assert task_repo_module.planning_gates_required("Not Required — reason") is False
    assert task_repo_module.planning_gates_required("`Not Required` — reason") is False
    assert task_repo_module.planning_gates_required("Maybe") is None
    assert task_repo_module.task_planning_gates_value(record) == "Required — fixture"
    assert task_repo_module.task_requires_exec_plan(record) is True
    assert task_repo_module.task_id_from_spec_path("tasks/specs/275-example.md") == "TASK-275"
    assert task_repo_module.task_id_from_spec_path("tasks/specs/bad.md") is None
    assert (
        task_repo_module.task_id_from_exec_plan_path("tasks/exec_plans/TASK-905.md") == "TASK-905"
    )
    assert task_repo_module.task_id_from_exec_plan_path("tasks/exec_plans/bad.md") is None


def test_parse_human_blockers_skips_malformed_rows(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-253` Coverage task",
                "",
                "## Human Blocker Metadata",
                "- malformed",
                "- TASK-253 | owner=human | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=bad",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert len(blockers) == 1
    assert blockers[0].task_id == "TASK-253"
    assert blockers[0].escalate_after_days == 0


def test_parse_task_block_ignores_metadata_lines_in_description() -> None:
    raw_block = "\n".join(
        [
            "### TASK-905: Fixture",
            "**Priority**: P1",
            "**Estimate**: 2h",
            "**Planning Gates**: Required — fixture",
            "**Canonical Example**: `tasks/specs/275-finish-review-gate-timeout.md`",
            "",
            "Description line.",
            "",
            "**Files**: `src/example.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] works",
        ]
    )

    record = task_repo_module._parse_task_block("TASK-905", "Fixture", raw_block)

    assert record.description == ["Description line."]


def test_planning_marker_from_relative_path_returns_none_for_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    assert task_commands_module._planning_marker_from_relative_path("tasks/specs/missing.md") == (
        None,
        None,
    )


def test_planning_context_uses_later_marker_when_earlier_artifact_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-999",
        title="Fixture",
        priority="P1",
        estimate="1h",
        description=["fixture"],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="",
        status="backlog",
        sprint_lines=[],
        spec_paths=["tasks/specs/999-fixture.md"],
        source_path="tasks/BACKLOG.md",
    )

    monkeypatch.setattr(
        task_commands_module,
        "exec_plan_paths_for_task",
        lambda _task_id: ["tasks/exec_plans/TASK-999.md"],
    )
    monkeypatch.setattr(task_commands_module, "task_planning_gates_value", lambda _: None)

    def fake_marker(relative_path: str) -> tuple[str | None, str | None]:
        if relative_path == "tasks/exec_plans/TASK-999.md":
            return None, None
        return "Required — later spec marker", relative_path

    monkeypatch.setattr(task_commands_module, "_planning_marker_from_relative_path", fake_marker)

    planning = task_commands_module._planning_context("TASK-999", record)

    assert planning["required"] is True
    assert planning["marker_value"] == "Required — later spec marker"
    assert planning["marker_source"] == "tasks/specs/999-fixture.md"
    assert planning["authoritative_artifact_path"] == "tasks/exec_plans/TASK-999.md"


def test_blocker_urgency_defaults_to_pending_without_next_action() -> None:
    urgency = task_repo_module.blocker_urgency(
        last_touched="2026-03-01",
        next_action="",
        escalate_after_days=0,
        as_of=date(2026, 3, 7),
    )

    assert urgency.state == "pending"
    assert urgency.days_until_next_action is None
    assert urgency.is_overdue is False


def test_parse_human_blockers_skips_non_kv_chunks(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Human Blocker Metadata\n"
        "- TASK-253 | owner=alice | malformed | next_action=2026-03-10 | escalate_after_days=3\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert len(blockers) == 1
    assert blockers[0].owner == "alice"
    assert blockers[0].last_touched == ""


def test_parse_human_blockers_ignores_non_bullet_lines(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Human Blocker Metadata\n"
        "TASK-253 | owner=alice | last_touched=2026-03-06 | next_action=2026-03-10 | escalate_after_days=3\n"
        "- TASK-254 | owner=bob | last_touched=2026-03-06 | next_action=2026-03-10 | escalate_after_days=3\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert [blocker.task_id for blocker in blockers] == ["TASK-254"]


def test_parse_active_tasks_ignores_non_task_lines(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "Narrative line",
                "- sequencing note without a task id",
                "- `TASK-292` Ledger reset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    tasks = task_repo_module.parse_active_tasks(sprint_path)

    assert [task.task_id for task in tasks] == ["TASK-292"]


def test_archive_backlog_paths_returns_empty_when_archive_root_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    assert task_repo_module.archive_backlog_paths() == []


def test_task_closure_state_reports_live_open_and_archived_closed_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_close_ledgers_repo(tmp_path)
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    live_state = task_repo_module.task_closure_state("TASK-294")

    assert live_state.present_in_backlog is True
    assert live_state.present_in_active_sprint is True
    assert live_state.present_in_completed is False
    assert live_state.present_in_closed_archive is False
    assert live_state.ready_for_merge is False

    archive_path = tmp_path / "archive" / "closed_tasks" / "2026-Q1.md"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "**Quarter**: 2026-Q1",
                "",
                "Do not read `archive/closed_tasks/` during normal implementation flow unless a user explicitly asks for historical context or an archive-aware CLI flag is used.",
                "",
                "---",
                "",
                "### TASK-294: Archive closure",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Archived.",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "# Backlog\n\n### TASK-295: Keep me live\n**Priority**: P1\n**Estimate**: 1d\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n**Sprint Number**: 4\n\n## Active Tasks\n- `TASK-295` Keep me live\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-294: Archive closure ✅\n",
        encoding="utf-8",
    )

    closed_state = task_repo_module.task_closure_state("TASK-294")

    assert closed_state.present_in_backlog is False
    assert closed_state.present_in_active_sprint is False
    assert closed_state.present_in_completed is True
    assert closed_state.present_in_closed_archive is True
    assert closed_state.closed_archive_path == "archive/closed_tasks/2026-Q1.md"
    assert closed_state.ready_for_merge is True


def test_closed_task_archive_record_scans_multiple_quarter_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_dir = tmp_path / "archive" / "closed_tasks"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "BACKLOG.md").write_text("# Backlog\n", encoding="utf-8")
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n**Sprint Number**: 4\n\n## Active Tasks\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")
    (archive_dir / "2026-Q2.md").write_text(
        "# Closed Task Archive\n\n**Status**: Archived closed-task ledger (non-authoritative)\n",
        encoding="utf-8",
    )
    (archive_dir / "2026-Q1.md").write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "",
                "### TASK-295: Enforce closure",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    record = task_repo_module.closed_task_archive_record("TASK-295")

    assert record is not None
    assert record.source_path == "archive/closed_tasks/2026-Q1.md"


def test_archived_task_records_include_closed_task_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "archive" / "closed_tasks" / "2026-Q1.md"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "**Quarter**: 2026-Q1",
                "",
                "Do not read `archive/closed_tasks/` during normal implementation flow unless a user explicitly asks for historical context or an archive-aware CLI flag is used.",
                "",
                "---",
                "",
                "### TASK-294: Archive closure",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Archived.",
                "",
                "**Files**: `tasks/BACKLOG.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] archived",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-294: Archive closure ✅\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-295` Keep me live\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    record = task_repo_module.archived_task_record("TASK-294")

    assert record is not None
    assert record.archived is True
    assert record.source_path == "archive/closed_tasks/2026-Q1.md"


def test_closed_tasks_archive_paths_returns_empty_when_closed_task_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    assert task_repo_module.closed_tasks_archive_paths() == []


def test_task_block_match_returns_none_when_task_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "# Backlog\n\n### TASK-295: Keep me live\n**Priority**: P1\n**Estimate**: 1d\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    assert task_repo_module.task_block_match("TASK-294") is None


def test_completed_task_ids_returns_empty_when_completed_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_completed = tmp_path / "COMPLETED.md"
    monkeypatch.setattr(task_repo_module, "completed_path", lambda: missing_completed)

    assert task_repo_module.completed_task_ids() == set()


def test_search_task_records_can_include_archive_without_matching_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived_record = task_repo_module.TaskRecord(
        task_id="TASK-164",
        title="Agent smoke run",
        priority="P1",
        estimate="1d",
        description=["smoke"],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="completed",
        sprint_lines=[],
        spec_paths=[],
        source_path="archive/2026-03-10-sprint-3-close/tasks/BACKLOG.md",
        archived=True,
    )
    monkeypatch.setattr(task_repo_module, "backlog_task_records", lambda _path=None: {})
    monkeypatch.setattr(
        task_repo_module,
        "archived_task_records",
        lambda: {"TASK-164": archived_record},
    )
    monkeypatch.setattr(
        task_repo_module,
        "task_record",
        lambda task_id, **_kwargs: archived_record if task_id == "TASK-164" else None,
    )

    assert (
        task_repo_module.search_task_records("smoke", status="active", include_archive=True) == []
    )


def test_parse_task_block_stops_description_at_unknown_heading() -> None:
    raw_block = """### TASK-253: Coverage
**Priority**: P0
**Estimate**: 2d
This is part of the description.
**Unexpected**
This should not stay in the description.
"""

    record = task_repo_module._parse_task_block("TASK-253", "Coverage", raw_block)

    assert record.description == ["This is part of the description."]


def test_task_record_stays_backlog_without_sprint_or_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-253",
        title="Coverage",
        priority="P0",
        estimate="2d",
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )
    monkeypatch.setattr(task_repo_module, "backlog_task_records", lambda: {"TASK-253": record})
    monkeypatch.setattr(task_repo_module, "sprint_lines_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "spec_paths_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "is_task_completed", lambda _task_id: False)

    resolved = task_repo_module.task_record("TASK-253")

    assert resolved is not None
    assert resolved.status == "backlog"


def test_task_repo_helper_limit_and_line_search_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backlog_file = tmp_path / "tasks" / "BACKLOG.md"
    backlog_file.parent.mkdir(parents=True, exist_ok=True)
    backlog_file.write_text("### TASK-253: Coverage\nNeedle path\n", encoding="utf-8")
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        task_repo_module,
        "backlog_task_records",
        lambda: {
            "TASK-253": task_repo_module.TaskRecord(
                task_id="TASK-253",
                title="Coverage",
                priority="P1",
                estimate="S",
                description=["Needle path"],
                status="backlog",
                files=[],
                acceptance_criteria=[],
                raw_block="raw",
                spec_paths=[],
                sprint_lines=[],
                assessment_refs=[],
            )
        },
    )
    monkeypatch.setattr(task_repo_module, "sprint_lines_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "spec_paths_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "is_task_completed", lambda _task_id: False)

    limited = task_repo_module.search_task_records("coverage", limit=1)
    hits = task_repo_module.line_search(backlog_file, "needle")

    assert len(limited) == 1
    assert limited[0].task_id == "TASK-253"
    assert hits[0].source == "tasks/BACKLOG.md"
    assert hits[0].line_number == 2
