from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _seed_close_ledgers_repo

pytestmark = pytest.mark.unit


def test_close_ledgers_task_data_archives_task_and_updates_live_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_close_ledgers_repo(tmp_path)
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "current_date", lambda: date(2026, 3, 10))

    exit_code, data, lines = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["archive_path"] == "archive/closed_tasks/2026-Q1.md"
    assert "Archived task block" in lines[-1]

    backlog_text = (tmp_path / "tasks" / "BACKLOG.md").read_text(encoding="utf-8")
    sprint_text = (tmp_path / "tasks" / "CURRENT_SPRINT.md").read_text(encoding="utf-8")
    completed_text = (tmp_path / "tasks" / "COMPLETED.md").read_text(encoding="utf-8")
    archive_text = (tmp_path / "archive" / "closed_tasks" / "2026-Q1.md").read_text(
        encoding="utf-8"
    )
    active_section = task_repo_module.active_section_text(tmp_path / "tasks" / "CURRENT_SPRINT.md")

    assert "### TASK-294: Archive closure" not in backlog_text
    assert "### TASK-295: Keep me live" in backlog_text
    assert "- `TASK-294` Archive closure" not in active_section
    assert "- `TASK-295` Keep me live" in sprint_text
    assert "- `TASK-294` Archive closure ✅" in sprint_text
    assert "TASK-999" in sprint_text
    assert "TASK-294 | owner=ops" not in sprint_text
    assert "## Sprint 4" in completed_text
    assert "- TASK-294: Archive closure ✅" in completed_text
    assert "**Quarter**: 2026-Q1" in archive_text
    assert "### TASK-294: Archive closure" in archive_text

    show_blocked = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-294"))
    assert show_blocked.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert show_blocked.error_lines == [
        "TASK-294 is archived; re-run with --include-archive to inspect its history"
    ]

    archived = task_repo_module.task_record("TASK-294", include_archive=True)
    assert archived is not None
    assert archived.archived is True
    assert archived.status == "completed"


def test_close_ledgers_task_data_supports_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_close_ledgers_repo(tmp_path)
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "current_date", lambda: date(2026, 3, 10))

    exit_code, data, lines = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert lines[-1] == "Dry run: would archive the full task block and update live ledgers."
    assert (tmp_path / "archive" / "closed_tasks" / "2026-Q1.md").exists() is False
    assert "### TASK-294: Archive closure" in (tmp_path / "tasks" / "BACKLOG.md").read_text(
        encoding="utf-8"
    )


def test_close_ledgers_task_data_removes_only_exact_task_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_close_ledgers_repo(tmp_path)
    sprint_path = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Number**: 4",
                "",
                "## Active Tasks",
                "- `TASK-294` Archive closure",
                "- `TASK-295` Keep me live (blocked by TASK-294 handoff)",
                "",
                "## Human Blocker Metadata",
                "- TASK-294 | owner=ops | last_touched=2026-03-10 | next_action=2026-03-11 | escalate_after_days=7",
                "- TASK-295 | owner=ops | note=depends on TASK-294 archive landing",
                "",
                "## Completed This Sprint",
                "- Sprint opened on 2026-03-10 with carry-over work only; no Sprint 4 tasks are complete yet.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "current_date", lambda: date(2026, 3, 10))

    exit_code, _, _ = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    sprint_text = sprint_path.read_text(encoding="utf-8")
    active_section = task_repo_module.active_section_text(sprint_path)

    assert exit_code == task_commands_module.ExitCode.OK
    assert "- `TASK-294` Archive closure" not in active_section
    assert "- `TASK-295` Keep me live (blocked by TASK-294 handoff)" in active_section
    assert "- TASK-294 | owner=ops" not in sprint_text
    assert "- TASK-295 | owner=ops | note=depends on TASK-294 archive landing" in sprint_text


def test_close_ledgers_task_data_tolerates_missing_human_blocker_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_close_ledgers_repo(tmp_path)
    sprint_path = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Number**: 4",
                "",
                "## Active Tasks",
                "- `TASK-294` Archive closure",
                "- `TASK-295` Keep me live",
                "",
                "## Completed This Sprint",
                "- Sprint opened on 2026-03-10 with carry-over work only; no Sprint 4 tasks are complete yet.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "current_date", lambda: date(2026, 3, 10))

    exit_code, _, _ = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    sprint_text = sprint_path.read_text(encoding="utf-8")
    assert exit_code == task_commands_module.ExitCode.OK
    assert "## Completed This Sprint" in sprint_text
    assert "- `TASK-294` Archive closure ✅" in sprint_text


def test_close_ledgers_task_data_rejects_already_archived_task(
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
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "BACKLOG.md").write_text("# Backlog\n", encoding="utf-8")
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n## Active Tasks\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-294: Archive closure ✅\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {"task_id": "TASK-294", "already_archived": True}
    assert lines == ["TASK-294 is already closed and archived."]


def test_close_ledgers_task_data_reports_not_found_when_task_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "task_record", lambda _task_id: None)
    monkeypatch.setattr(task_commands_module, "archived_task_record", lambda _task_id: None)

    exit_code, data, lines = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert data == {"task_id": "TASK-294"}
    assert lines == ["TASK-294 not found in tasks/BACKLOG.md"]


def test_close_ledgers_task_data_requires_backlog_block(monkeypatch: pytest.MonkeyPatch) -> None:
    live_record = task_repo_module.TaskRecord(
        task_id="TASK-294",
        title="Archive closure",
        priority="P1",
        estimate="1d",
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="### TASK-294: Archive closure\n",
        status="active",
        sprint_lines=[],
        spec_paths=[],
        source_path="tasks/BACKLOG.md",
        archived=False,
    )
    monkeypatch.setattr(task_commands_module, "task_record", lambda _task_id: live_record)
    monkeypatch.setattr(task_commands_module, "archived_task_record", lambda _task_id: None)
    monkeypatch.setattr(task_commands_module, "task_block_match", lambda *_args, **_kwargs: None)

    exit_code, data, lines = task_commands_module.close_ledgers_task_data("TASK-294", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert data == {"task_id": "TASK-294"}
    assert lines == ["TASK-294 not found in tasks/BACKLOG.md"]


def test_handle_close_ledgers_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_close_ledgers(
        argparse.Namespace(task_id="bad", dry_run=False)
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad'. Expected TASK-XXX or XXX."]


def test_handle_close_ledgers_returns_close_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "close_ledgers_task_data",
        lambda task_id, dry_run: (
            task_commands_module.ExitCode.OK,
            {"task_id": task_id, "dry_run": dry_run},
            ["closed"],
        ),
    )

    result = task_commands_module.handle_close_ledgers(
        argparse.Namespace(task_id="TASK-294", dry_run=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"task_id": "TASK-294", "dry_run": True}
    assert result.lines == ["closed"]


def test_replace_h2_section_requires_matching_heading() -> None:
    with pytest.raises(ValueError, match="Unable to locate section 'Active Tasks'"):
        task_commands_module._replace_h2_section("# Current Sprint\n", "Active Tasks", "")


def test_extract_h2_section_body_requires_matching_heading() -> None:
    with pytest.raises(ValueError, match="Unable to locate section 'Completed This Sprint'"):
        task_commands_module._extract_h2_section_body("# Current Sprint\n", "Completed This Sprint")


def test_extract_sprint_number_requires_marker() -> None:
    with pytest.raises(
        ValueError,
        match=r"Unable to determine sprint number from tasks/CURRENT_SPRINT\.md",
    ):
        task_commands_module._extract_sprint_number("# Current Sprint\n")


def test_append_completed_sprint_line_does_not_duplicate_existing_entry() -> None:
    section_body = "\n".join(
        [
            "- Sprint opened on 2026-03-10 with carry-over work only; no Sprint 4 tasks are complete yet.",
            "- `TASK-294` Archive closure ✅",
        ]
    )

    updated = task_commands_module._append_completed_sprint_line(
        section_body, "TASK-294", "Archive closure"
    )

    assert updated == "- `TASK-294` Archive closure ✅"


def test_upsert_completed_ledger_entry_initializes_empty_completed_file() -> None:
    updated = task_commands_module._upsert_completed_ledger_entry(
        "",
        sprint_number="4",
        task_id="TASK-294",
        title="Archive closure",
    )

    assert updated == "# Completed Tasks\n## Sprint 4\n- TASK-294: Archive closure ✅\n"


def test_upsert_completed_ledger_entry_adds_missing_header() -> None:
    updated = task_commands_module._upsert_completed_ledger_entry(
        "## Sprint 3\n- TASK-292: Already done ✅\n",
        sprint_number="4",
        task_id="TASK-294",
        title="Archive closure",
    )

    assert updated.startswith("# Completed Tasks\n\n## Sprint 3\n- TASK-292: Already done ✅\n")
    assert updated.endswith("\n## Sprint 4\n- TASK-294: Archive closure ✅\n")


def test_upsert_completed_ledger_entry_appends_once_within_existing_sprint_section() -> None:
    content = "# Completed Tasks\n\n## Sprint 4\n- TASK-290: Existing task ✅\n- TASK-294: Archive closure ✅\n"

    updated = task_commands_module._upsert_completed_ledger_entry(
        content,
        sprint_number="4",
        task_id="TASK-294",
        title="Archive closure",
    )

    assert updated.count("- TASK-294: Archive closure ✅") == 1
    assert "- TASK-290: Existing task ✅" in updated


def test_upsert_completed_ledger_entry_appends_to_existing_sprint_section() -> None:
    content = "# Completed Tasks\n\n## Sprint 4\n- TASK-290: Existing task ✅\n"

    updated = task_commands_module._upsert_completed_ledger_entry(
        content,
        sprint_number="4",
        task_id="TASK-294",
        title="Archive closure",
    )

    assert "- TASK-290: Existing task ✅" in updated
    assert "- TASK-294: Archive closure ✅" in updated


def test_append_archived_task_block_does_not_duplicate_existing_task(tmp_path: Path) -> None:
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

    task_commands_module._append_archived_task_block(
        archive_path,
        archive_label="2026-Q1",
        task_id="TASK-294",
        raw_block="### TASK-294: Archive closure\n**Priority**: P1\n**Estimate**: 1d\n",
    )

    archive_text = archive_path.read_text(encoding="utf-8")
    assert archive_text.count("### TASK-294: Archive closure") == 1


def test_remove_backlog_task_block_requires_matching_task() -> None:
    with pytest.raises(
        ValueError,
        match=r"Unable to remove TASK-294 from tasks/BACKLOG\.md",
    ):
        task_commands_module._remove_backlog_task_block(
            "# Backlog\n\n### TASK-295: Keep me live\n",
            "TASK-294",
        )
