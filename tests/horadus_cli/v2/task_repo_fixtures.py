from __future__ import annotations

from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tools.horadus.python.horadus_workflow import task_repo as workflow_task_repo_module

LIVE_TASK_ID = "TASK-901"
ARCHIVED_TASK_ID = "TASK-902"
BACKLOG_ONLY_TASK_ID = "TASK-903"
NON_APPLICABLE_TASK_ID = "TASK-904"
EXEC_PLAN_TASK_ID = "TASK-905"
EXEC_PLAN_NO_MARKER_TASK_ID = "TASK-906"
HIGH_RISK_TASK_ID = "TASK-907"
SHARED_HELPER_TASK_ID = "TASK-908"


def _backlog_fixture_text() -> str:
    return (
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-901: Stable live fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "**Planning Gates**: Required — spec-backed workflow fixture",
                "",
                "Exercise live task lookups without depending on the repo backlog.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] live task lookup works",
                "",
                "---",
                "",
                "### TASK-903: Backlog-only fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — backlog-only applicable fixture",
                "",
                "Exercise placeholder paths when a task is not in the active sprint.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] backlog-only lookup works",
                "",
                "---",
                "",
                "### TASK-904: Quiet-path fixture",
                "**Priority**: P3",
                "**Estimate**: 15m",
                "",
                "Exercise the non-applicable planning quiet path.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] non-applicable context pack stays quiet",
                "",
                "---",
                "",
                "### TASK-905: Exec-plan fixture",
                "**Priority**: P1",
                "**Estimate**: 3h",
                "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
                "",
                "Exercise exec-plan-backed planning applicability.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] exec-plan context pack surfaces planning homes",
                "",
                "---",
                "",
                "### TASK-906: Exec-plan fallback fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
                "",
                "Exercise required planning surfacing when no explicit marker exists.",
                "",
                "**Files**: `tests/horadus_cli/v2/test_cli.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] required planning output omits marker when none is declared",
                "",
                "---",
                "",
                "### TASK-907: High-risk review fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "**Planning Gates**: Required — shared workflow tooling fixture",
                "",
                "Exercise pre-push adversarial review guidance for workflow tooling.",
                "",
                "**Files**: `AGENTS.md`, `tools/horadus/python/horadus_workflow/task_workflow_query.py`, `tests/workflow/`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] high-risk context pack recommends pre-push review",
                "",
                "---",
                "",
                "### TASK-908: Shared helper validation fixture",
                "**Priority**: P1",
                "**Estimate**: 2h",
                "**Planning Gates**: Required — shared helper validation-pack fixture",
                "",
                "Exercise caller-aware validation guidance for a shared workflow helper.",
                "",
                "**Files**: `tools/horadus/python/horadus_workflow/task_workflow_shared.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] context-pack recommends dependent workflow and CLI validation",
                "",
                "---",
                "",
            ]
        )
        + "\n"
    )


def _current_sprint_fixture_text() -> str:
    return (
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Number**: 4",
                "",
                "## Active Tasks",
                "- `TASK-901` Stable live fixture",
                "",
                "## Completed This Sprint",
                "- `TASK-902` Stable archived fixture ✅",
                "",
            ]
        )
        + "\n"
    )


def seed_task_repo_layout(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "specs").mkdir(parents=True, exist_ok=True)
    (repo_root / "archive" / "closed_tasks").mkdir(parents=True, exist_ok=True)

    (tasks_dir / "BACKLOG.md").write_text(_backlog_fixture_text(), encoding="utf-8")
    (tasks_dir / "CURRENT_SPRINT.md").write_text(_current_sprint_fixture_text(), encoding="utf-8")
    (tasks_dir / "COMPLETED.md").write_text(
        "# Completed Tasks\n\n## Sprint 4\n- TASK-902: Stable archived fixture ✅\n",
        encoding="utf-8",
    )
    (tasks_dir / "specs" / "901-stable-live-fixture.md").write_text(
        "\n".join(
            [
                "# TASK-901 fixture spec",
                "",
                "**Planning Gates**: Required — spec-backed fixture",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
                "- `Simplicity Gate`: Extend the existing fixture layout.",
                "- `Anti-Abstraction Gate`: Reuse the shared synthetic task repo.",
                "- `Integration-First Gate`:",
                "  - Validation target: `pytest tests/horadus_cli/v2/test_cli.py`",
                "  - Exercises: context-pack planning surfacing.",
                "- `Determinism Gate`: Not applicable — fixture-only task.",
                "- `LLM Budget/Safety Gate`: Not applicable — no LLM path.",
                "- `Observability Gate`: Not applicable — no runtime behavior.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "exec_plans").mkdir(parents=True, exist_ok=True)
    (tasks_dir / "exec_plans" / "TASK-905.md").write_text(
        "\n".join(
            [
                "# TASK-905: Exec-plan fixture",
                "",
                "## Status",
                "",
                "- Owner: Fixture",
                "- Started: 2026-03-11",
                "- Current state: In progress",
                "- Planning Gates: Required — exec-plan-backed fixture",
                "",
                "## Goal (1-3 lines)",
                "",
                "Exercise exec-plan-backed planning surfacing.",
                "",
                "## Gate Outcomes / Waivers",
                "",
                "- Accepted design / smallest safe shape: use one exec plan file.",
                "- Rejected simpler alternative: omit the planning section entirely.",
                "- First integration proof: context-pack output for TASK-905.",
                "- Waivers: none.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "exec_plans" / "TASK-906.md").write_text(
        "\n".join(
            [
                "# TASK-906: Exec-plan fallback fixture",
                "",
                "## Status",
                "",
                "- Owner: Fixture",
                "- Started: 2026-03-11",
                "- Current state: In progress",
                "",
                "## Goal (1-3 lines)",
                "",
                "Exercise required planning surfacing without an explicit marker.",
                "",
                "## Gate Outcomes / Waivers",
                "",
                "- Accepted design / smallest safe shape: rely on exec-plan-required fallback.",
                "- Rejected simpler alternative: adding a redundant planning marker line.",
                "- First integration proof: context-pack output for TASK-906.",
                "- Waivers: none.",
                "",
            ]
        )
        + "\n",
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
    return repo_root


def patch_task_repo_root(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: repo_root)


@pytest.fixture
def synthetic_task_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = seed_task_repo_layout(tmp_path)
    patch_task_repo_root(monkeypatch, repo_root)
    return repo_root
