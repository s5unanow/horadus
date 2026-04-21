from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.task_repo as task_repo_module
import tools.horadus.python.horadus_workflow.triage as triage_module

pytestmark = pytest.mark.unit


def test_triage_fallback_task_details_preserves_closed_archive_completed_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
                "### TASK-201: Archived fixture",
                "**Priority**: P1",
                "**Estimate**: 1d",
                "",
                "Closed archive fixture.",
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
    (tmp_path / "tasks" / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")

    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_module, "task_record", task_repo_module.task_record)

    title, status = triage_module._fallback_task_details(
        "TASK-201",
        active_task_ids=set(),
        completed_ids=set(),
    )

    assert title == "Archived fixture"
    assert status == "completed"
