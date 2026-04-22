from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.docs_freshness as docs_freshness_module
from tests.workflow.test_docs_freshness import _seed_repo_layout
from tests.workflow.test_docs_freshness_planning_artifacts import _seed_planning_artifact_fixture

pytestmark = pytest.mark.unit


def test_validate_planning_artifact_fails_closed_for_spec_without_marker(tmp_path: Path) -> None:
    backlog_text = _seed_planning_artifact_fixture(tmp_path)
    (tmp_path / "tasks" / "specs" / "900-missing-marker.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
                "- `Simplicity Gate`: ok",
                "- `Anti-Abstraction Gate`: ok",
                "- `Integration-First Gate`:",
                "  - Validation target: ok",
                "  - Exercises: ok",
                "- `Determinism Gate`: Not applicable — fixture",
                "- `LLM Budget/Safety Gate`: Not applicable — fixture",
                "- `Observability Gate`: Not applicable — fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )
    backlog_with_missing_marker = backlog_text + "\n".join(
        [
            "### TASK-900: Missing marker fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/900-missing-marker.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )

    issues = _validate_planning(
        tmp_path,
        "tasks/specs/900-missing-marker.md",
        backlog_with_missing_marker,
    )

    assert {issue.rule_id for issue in issues} == {"planning_marker_missing"}


def test_docs_freshness_warns_for_spec_backed_task_missing_marker(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-900: Missing marker fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "",
                "Planning fixture body.",
                "",
                "**Files**: `tasks/specs/900-missing-marker.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] planning warning appears",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "specs" / "900-missing-marker.md").write_text(
        "\n".join(
            [
                "# TASK-900: Missing marker fixture",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
                "- `Simplicity Gate`: Extend the fixture.",
                "- `Anti-Abstraction Gate`: Keep it simple.",
                "- `Integration-First Gate`:",
                "  - Validation target: docs freshness explicit artifact run.",
                "  - Exercises: spec-backed planning validation without a marker.",
                "- `Determinism Gate`: Not applicable — fixture",
                "- `LLM Budget/Safety Gate`: Not applicable — fixture",
                "- `Observability Gate`: Not applicable — fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = docs_freshness_module.run_docs_freshness_check(
        repo_root=tmp_path,
        planning_artifact_paths=("tasks/specs/900-missing-marker.md",),
    )

    assert {issue.rule_id for issue in result.warnings} == {"planning_marker_missing"}


def test_docs_freshness_keeps_quiet_not_required_spec_green(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-901: Quiet fixture",
                "**Priority**: P3",
                "**Estimate**: 15m",
                "**Planning Gates**: Not Required — tiny docs-only follow-up",
                "",
                "Planning fixture body.",
                "",
                "**Files**: `tasks/specs/901-quiet.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] planning warning stays quiet",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "specs" / "901-quiet.md").write_text(
        "\n".join(
            [
                "# TASK-901: Quiet fixture",
                "",
                "**Planning Gates**: Not Required — tiny docs-only follow-up",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = docs_freshness_module.run_docs_freshness_check(
        repo_root=tmp_path,
        planning_artifact_paths=("tasks/specs/901-quiet.md",),
    )

    assert result.warnings == ()


def _validate_planning(
    tmp_path: Path, relative_path: str, backlog_text: str
) -> tuple[docs_freshness_module.DocsFreshnessIssue, ...]:
    return docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path=relative_path,
        backlog_text=backlog_text,
    )
