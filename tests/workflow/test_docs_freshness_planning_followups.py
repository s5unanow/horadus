from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow._docs_freshness_planning_followups as followups_module
import tools.horadus.python.horadus_workflow.docs_freshness as docs_freshness_module
from tests.workflow.test_docs_freshness_planning_hotspots import _seed_hotspot_exec_plan_fixture

pytestmark = pytest.mark.unit


def test_known_followup_task_ids_handles_missing_history_ledgers(tmp_path: Path) -> None:
    backlog_text, _ = _seed_hotspot_exec_plan_fixture(tmp_path)

    assert followups_module.known_followup_task_ids(tmp_path, backlog_text) == {
        "TASK-320",
        "TASK-321",
    }


def test_validate_planning_artifact_accepts_completed_followup_tasks(tmp_path: Path) -> None:
    backlog_text, base_exec_plan = _seed_hotspot_exec_plan_fixture(tmp_path)
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n- TASK-330: Cleanup hotspot follow-up ✅\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-330 cleanup later\n",
        encoding="utf-8",
    )

    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TASK-320.md",
            backlog_text=backlog_text,
        )
        == ()
    )


def test_validate_planning_artifact_accepts_archived_followup_tasks(tmp_path: Path) -> None:
    backlog_text, base_exec_plan = _seed_hotspot_exec_plan_fixture(tmp_path)
    archive_root = tmp_path / "archive" / "closed_tasks"
    archive_root.mkdir(parents=True, exist_ok=True)
    (archive_root / "2026-Q2.md").write_text(
        "# Closed Tasks\n\n### TASK-330: Archived cleanup follow-up\n**Priority**: P2\n\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-330 cleanup later\n",
        encoding="utf-8",
    )

    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TASK-320.md",
            backlog_text=backlog_text,
        )
        == ()
    )


def test_validate_planning_artifact_still_rejects_unknown_followup_with_history_ledgers(
    tmp_path: Path,
) -> None:
    backlog_text, base_exec_plan = _seed_hotspot_exec_plan_fixture(tmp_path)
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n- TASK-330: Cleanup hotspot follow-up ✅\n",
        encoding="utf-8",
    )
    archive_root = tmp_path / "archive" / "closed_tasks"
    archive_root.mkdir(parents=True, exist_ok=True)
    (archive_root / "2026-Q2.md").write_text(
        "# Closed Tasks\n\n### TASK-331: Archived cleanup follow-up\n**Priority**: P2\n\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-999 cleanup later\n",
        encoding="utf-8",
    )

    issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )

    assert {issue.rule_id for issue in issues} == {"planning_hotspot_followup_unknown_task"}
