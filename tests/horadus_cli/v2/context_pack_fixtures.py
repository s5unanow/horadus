from __future__ import annotations

from pathlib import Path

import pytest

from tools.horadus.python.horadus_workflow import task_repo as workflow_task_repo_module


def seed_human_gated_task_repo(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    docs_dir = repo_root / "docs"
    workflow_tests_dir = repo_root / "tests" / "workflow"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    workflow_tests_dir.mkdir(parents=True, exist_ok=True)

    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-189: Human-gated fixture [REQUIRES_HUMAN]",
                "**Priority**: P1",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — human-gated fixture",
                "",
                "Exercise derived autonomous eligibility and current sprint extraction.",
                "",
                "**Files**: `tasks/CURRENT_SPRINT.md`, `tools/horadus/python/horadus_workflow/` (shared helper)",
                "",
                "**Acceptance Criteria**:",
                "- [ ] implement mode marks the task ineligible for autonomous callers",
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
                "**Sprint Goal**: Exercise human-gated implement-mode retrieval.",
                "**Sprint Number**: 12",
                "**Sprint Dates**: 2026-04-20 to 2026-05-03",
                "",
                "## Active Tasks",
                "- `TASK-189` Human-gated fixture [REQUIRES_HUMAN]",
                "",
                "## Selection Notes",
                "- `TASK-189` remains human-gated until the operator signs off.",
                "",
                "## Suggested Sequence",
                "1. `TASK-189` Exercise the ineligible path.",
                "",
                "## Human Blocker Metadata",
                "- TASK-189 | owner=human-operator | last_touched=2026-04-19 | next_action=2026-04-20 | escalate_after_days=7",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
                "## Completed This Sprint",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")
    (docs_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "DATA_MODEL.md").write_text("# Data Model\n", encoding="utf-8")
    (workflow_tests_dir / "test_docs_freshness.py").write_text(
        "def test_fixture() -> None:\n    pass\n",
        encoding="utf-8",
    )
    return repo_root


def seed_context_pack_orientation_files(repo_root: Path) -> None:
    docs_dir = repo_root / "docs"
    cli_tests_dir = repo_root / "tests" / "horadus_cli" / "v2"
    docs_dir.mkdir(parents=True, exist_ok=True)
    cli_tests_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "DATA_MODEL.md").write_text("# Data Model\n", encoding="utf-8")
    (cli_tests_dir / "test_cli.py").write_text(
        "def test_fixture() -> None:\n    pass\n", encoding="utf-8"
    )


def seed_context_pack_archive_fixture(repo_root: Path) -> None:
    (repo_root / "archive" / "closed_tasks" / "2026-Q1.md").write_text(
        "\n".join(
            [
                "# Closed Task Archive",
                "",
                "**Status**: Archived closed-task ledger (non-authoritative)",
                "**Quarter**: 2026-Q1",
                "",
                workflow_task_repo_module.CLOSED_TASK_ARCHIVE_GUIDANCE,
                "",
                "---",
                "",
                "### TASK-902: Stable archived fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "",
                "Exercise archive-gated task lookups without depending on repo history.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
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


def patch_context_pack_workflow_repo_root(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(workflow_task_repo_module, "repo_root", lambda: repo_root)
