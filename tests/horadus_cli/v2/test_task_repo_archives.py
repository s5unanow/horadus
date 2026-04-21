from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module

pytestmark = pytest.mark.unit


def _seed_archive_task_repo(tmp_path: Path, archive_lines: list[str]) -> None:
    archive_path = tmp_path / "archive" / "closed_tasks" / "2026-Q1.md"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text("\n".join(archive_lines), encoding="utf-8")
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "BACKLOG.md").write_text("# Backlog\n", encoding="utf-8")
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n## Active Tasks\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")


def test_closed_task_archive_record_handles_adjacent_headers_without_separator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_archive_task_repo(
        tmp_path,
        [
            "# Closed Task Archive",
            "",
            "**Status**: Archived closed-task ledger (non-authoritative)",
            "**Quarter**: 2026-Q1",
            "",
            "### TASK-311: Tooling split",
            "**Priority**: P1",
            "**Estimate**: 2d",
            "",
            "Archive text that was missing the usual separator.",
            "",
            "### TASK-080: Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "**Priority**: P2",
            "**Estimate**: 3h",
            "",
            "Wire Telegram.",
            "",
            "---",
            "",
        ],
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    task_311 = task_repo_module.closed_task_archive_record("TASK-311")
    task_080 = task_repo_module.closed_task_archive_record("TASK-080")

    assert task_311 is not None
    assert "### TASK-080" not in "\n".join(task_311.description)
    assert task_080 is not None
    assert task_080.title == "Telegram Collector Task Wiring [REQUIRES_HUMAN]"


def test_closed_task_archive_record_keeps_trailing_space_separator_inside_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_archive_task_repo(
        tmp_path,
        [
            "# Closed Task Archive",
            "",
            "**Status**: Archived closed-task ledger (non-authoritative)",
            "**Quarter**: 2026-Q1",
            "",
            "### TASK-311: Tooling split",
            "**Priority**: P1",
            "**Estimate**: 2d",
            "",
            "Archive text that should keep the padded separator.",
            "",
            "---   ",
            "### TASK-080: Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "**Priority**: P2",
            "**Estimate**: 3h",
            "",
            "Wire Telegram.",
            "",
            "---",
            "",
        ],
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    task_311 = task_repo_module.closed_task_archive_record("TASK-311")
    task_080 = task_repo_module.closed_task_archive_record("TASK-080")

    assert task_311 is not None
    assert "---" in task_311.description
    assert task_080 is not None


def test_task_record_marks_closed_archive_tasks_completed_without_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_archive_task_repo(
        tmp_path,
        [
            "# Closed Task Archive",
            "",
            "**Status**: Archived closed-task ledger (non-authoritative)",
            "**Quarter**: 2026-Q1",
            "",
            "### TASK-294: Archive closure",
            "**Priority**: P1",
            "**Estimate**: 1d",
            "",
            "Archived.",
            "",
            "---",
            "",
        ],
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    archived = task_repo_module.task_record("TASK-294", include_archive=True)

    assert archived is not None
    assert archived.archived is True
    assert archived.source_path == "archive/closed_tasks/2026-Q1.md"
    assert archived.status == "completed"


def test_search_task_records_prefers_closed_archive_record_for_duplicate_task_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_archive_task_repo(
        tmp_path,
        [
            "# Closed Task Archive",
            "",
            "**Status**: Archived closed-task ledger (non-authoritative)",
            "**Quarter**: 2026-Q1",
            "",
            "### TASK-080: Telegram Collector Task Wiring [REQUIRES_HUMAN]",
            "**Priority**: P2",
            "**Estimate**: 3h",
            "",
            "Closed archive version.",
            "",
            "---",
            "",
        ],
    )
    archived_backlog = tmp_path / "archive" / "2026-03-10-sprint-3-close" / "tasks" / "BACKLOG.md"
    archived_backlog.parent.mkdir(parents=True, exist_ok=True)
    archived_backlog.write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-080: Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "**Priority**: P2",
                "**Estimate**: 3h",
                "",
                "Historical backlog version.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)

    matches = task_repo_module.search_task_records("TASK-080", include_archive=True)

    assert [record.task_id for record in matches] == ["TASK-080"]
    assert matches[0].source_path == "archive/closed_tasks/2026-Q1.md"
    assert matches[0].status == "completed"
