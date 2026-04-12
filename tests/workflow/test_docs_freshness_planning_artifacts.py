from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.docs_freshness as docs_freshness_module
from tests.workflow.test_docs_freshness import _seed_repo_layout

pytestmark = pytest.mark.unit


def test_validate_planning_artifact_covers_templates_and_complete_artifacts(
    tmp_path: Path,
) -> None:
    backlog_text = _seed_planning_artifact_fixture(tmp_path)

    _assert_template_validation(tmp_path, backlog_text)
    assert _validate_planning(tmp_path, "tasks/specs/275-example.md", backlog_text) == ()
    assert _validate_planning(tmp_path, "tasks/exec_plans/TASK-298.md", backlog_text) == ()
    assert _validate_planning(tmp_path, "tasks/BACKLOG.md", backlog_text) == ()
    assert _validate_planning(tmp_path, "tasks/specs/missing.md", backlog_text) == ()


def test_validate_planning_artifact_handles_quiet_and_incomplete_specs(tmp_path: Path) -> None:
    backlog_text = _seed_planning_artifact_fixture(tmp_path)
    (tmp_path / "tasks" / "specs" / "276-not-required.md").write_text(
        "\n".join(["# spec", "", "**Planning Gates**: Not Required — tiny follow-up", ""]),
        encoding="utf-8",
    )
    backlog_with_quiet = backlog_text + "\n".join(
        [
            "### TASK-276: Quiet fixture",
            "**Priority**: P3",
            "**Estimate**: 15m",
            "**Planning Gates**: Not Required — tiny follow-up",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/276-not-required.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )

    assert _validate_planning(tmp_path, "tasks/specs/276-not-required.md", backlog_with_quiet) == ()

    (tmp_path / "tasks" / "specs" / "277-incomplete.md").write_text(
        "\n".join(["# spec", "", "## Phase -1 / Pre-Implementation Gates", ""]),
        encoding="utf-8",
    )
    backlog_with_incomplete = backlog_with_quiet + "\n".join(
        [
            "### TASK-277: Incomplete spec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/277-incomplete.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    incomplete_spec_issues = _validate_planning(
        tmp_path,
        "tasks/specs/277-incomplete.md",
        backlog_with_incomplete,
    )
    assert {issue.rule_id for issue in incomplete_spec_issues} >= {
        "planning_marker_missing",
        "planning_core_gate_missing",
        "planning_conditional_gate_missing",
        "planning_integration_proof_incomplete",
    }

    (tmp_path / "tasks" / "specs" / "278-no-section.md").write_text(
        "\n".join(["# spec", "", "**Planning Gates**: Required — spec fixture", ""]),
        encoding="utf-8",
    )
    backlog_with_no_section = backlog_with_incomplete + "\n".join(
        [
            "### TASK-278: Missing section fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/278-no-section.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    missing_section_issues = _validate_planning(
        tmp_path,
        "tasks/specs/278-no-section.md",
        backlog_with_no_section,
    )
    assert {issue.rule_id for issue in missing_section_issues} == {"planning_spec_section_missing"}


def test_validate_planning_artifact_flags_incomplete_exec_and_non_planning_paths(
    tmp_path: Path,
) -> None:
    backlog_text = _seed_planning_artifact_fixture(tmp_path)
    (tmp_path / "tasks" / "exec_plans" / "TASK-299.md").write_text("# plan\n", encoding="utf-8")
    backlog_with_missing_exec = backlog_text + "\n".join(
        [
            "### TASK-299: Incomplete exec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `tasks/exec_plans/TASK-299.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    incomplete_exec_issues = _validate_planning(
        tmp_path,
        "tasks/exec_plans/TASK-299.md",
        backlog_with_missing_exec,
    )
    assert {issue.rule_id for issue in incomplete_exec_issues} >= {
        "planning_gate_outcomes_missing",
        "planning_gate_outcome_field_missing",
    }
    assert _validate_planning(tmp_path, "README.md", backlog_text) == ()
    (tmp_path / "tasks" / "notes.md").write_text("notes\n", encoding="utf-8")
    assert _validate_planning(tmp_path, "tasks/notes.md", backlog_text) == ()


def _seed_planning_artifact_fixture(tmp_path: Path) -> str:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    backlog_text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-275: Spec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/275-example.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
            "### TASK-298: Exec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `tasks/exec_plans/TASK-298.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text(backlog_text, encoding="utf-8")
    (tmp_path / "tasks" / "specs" / "275-example.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "**Planning Gates**: Required — spec fixture",
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
    (tmp_path / "tasks" / "exec_plans" / "TASK-298.md").write_text(
        "\n".join(
            [
                "# plan",
                "",
                "## Gate Outcomes / Waivers",
                "",
                "- Accepted design / smallest safe shape: ok",
                "- Rejected simpler alternative: ok",
                "- First integration proof: ok",
                "- Waivers: none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return backlog_text


def _validate_planning(
    tmp_path: Path, relative_path: str, backlog_text: str
) -> tuple[docs_freshness_module.DocsFreshnessIssue, ...]:
    return docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path=relative_path,
        backlog_text=backlog_text,
    )


def _assert_template_validation(tmp_path: Path, backlog_text: str) -> None:
    missing_template = _validate_planning(tmp_path, "tasks/specs/TEMPLATE.md", backlog_text)
    assert {issue.rule_id for issue in missing_template} == {
        "planning_marker_missing",
        "planning_spec_section_missing",
        "planning_hotspot_template_missing",
    }

    (tmp_path / "tasks" / "specs" / "TEMPLATE.md").write_text(
        "\n".join(
            [
                "**Planning Gates**: Required",
                "## Phase -1 / Pre-Implementation Gates",
                "- Hotspot Outcome: reduce — template fixture",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert _validate_planning(tmp_path, "tasks/specs/TEMPLATE.md", backlog_text) == ()

    (tmp_path / "tasks" / "exec_plans" / "TEMPLATE.md").write_text("", encoding="utf-8")
    missing_exec_template = _validate_planning(
        tmp_path, "tasks/exec_plans/TEMPLATE.md", backlog_text
    )
    assert {issue.rule_id for issue in missing_exec_template} == {
        "planning_marker_missing",
        "planning_gate_outcomes_missing",
        "planning_hotspot_template_missing",
    }

    (tmp_path / "tasks" / "exec_plans" / "TEMPLATE.md").write_text(
        "\n".join(
            [
                "Planning Gates: Required",
                "## Gate Outcomes / Waivers",
                "- Hotspot Outcome: reduce — template fixture",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert _validate_planning(tmp_path, "tasks/exec_plans/TEMPLATE.md", backlog_text) == ()
