from __future__ import annotations

from pathlib import Path

import pytest

import src.horadus_cli.v1.task_repo as task_repo_module
import src.horadus_cli.v1.task_workflow_core as task_commands_module

LIVE_TASK_ID = "TASK-301"
ARCHIVED_TASK_ID = "TASK-302"
BACKLOG_ONLY_TASK_ID = "TASK-303"


def seed_task_repo_layout(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "specs").mkdir(parents=True, exist_ok=True)
    (repo_root / "archive" / "closed_tasks").mkdir(parents=True, exist_ok=True)

    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-301: Stable live fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "",
                "Exercise live task lookups without depending on the repo backlog.",
                "",
                "**Files**: `tests/unit/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] live task lookup works",
                "",
                "---",
                "",
                "### TASK-303: Backlog-only fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "",
                "Exercise placeholder paths when a task is not in the active sprint.",
                "",
                "**Files**: `tests/unit/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] backlog-only lookup works",
                "",
                "---",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Number**: 4",
                "",
                "## Active Tasks",
                "- `TASK-301` Stable live fixture",
                "",
                "## Completed This Sprint",
                "- `TASK-302` Stable archived fixture ✅",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-302: Stable archived fixture ✅\n",
        encoding="utf-8",
    )
    (tasks_dir / "specs" / "301-stable-live-fixture.md").write_text(
        "# TASK-301 fixture spec\n",
        encoding="utf-8",
    )
    (repo_root / "archive" / "closed_tasks" / "2026-Q1.md").write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "**Quarter**: 2026-Q1",
                "",
                task_repo_module.CLOSED_TASK_ARCHIVE_GUIDANCE,
                "",
                "---",
                "",
                "### TASK-302: Stable archived fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "",
                "Exercise archive-gated task lookups without depending on repo history.",
                "",
                "**Files**: `tests/unit/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] archived task lookup works",
                "",
                "---",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return repo_root


def patch_task_repo_root(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: repo_root)


@pytest.fixture
def synthetic_task_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = seed_task_repo_layout(tmp_path)
    patch_task_repo_root(monkeypatch, repo_root)
    return repo_root
