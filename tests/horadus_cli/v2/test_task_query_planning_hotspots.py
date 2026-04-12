from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_planning_context as planning_context_module

pytestmark = pytest.mark.unit

HOTSPOT_TASK_ID = "TASK-909"


def test_handle_context_pack_surfaces_hotspot_requirement_from_code_shape_policy(
    synthetic_task_repo: Path,
) -> None:
    (synthetic_task_repo / "config" / "quality").mkdir(parents=True, exist_ok=True)
    (synthetic_task_repo / "config" / "quality" / "code_shape.toml").write_text(
        "\n".join(
            [
                "[budgets]",
                "production_module_lines = 700",
                "test_module_lines = 1200",
                "production_function_lines = 100",
                "test_function_lines = 160",
                "production_member_complexity = 20",
                "test_member_complexity = 25",
                "",
                "[paths]",
                'include_roots = ["src", "tools", "tests", "scripts"]',
                'exclude_globs = ["**/__pycache__/**"]',
                "",
                "[[legacy_files]]",
                'path = "tools/horadus/python/horadus_workflow/_docs_freshness_planning.py"',
                "[legacy_files.member_max_lines]",
                '"_validate_planning_artifact" = 180',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    backlog_path = synthetic_task_repo / "tasks" / "BACKLOG.md"
    backlog_path.write_text(
        backlog_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                f"### {HOTSPOT_TASK_ID}: Hotspot context-pack fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "",
                "Exercise hotspot-derived planning requirements.",
                "",
                "**Files**: `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] hotspot requirement is surfaced",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id=HOTSPOT_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "State: applicable_backlog_only_missing_artifact" in result.lines
    assert (
        "Allowlisted production hotspots: "
        "tools/horadus/python/horadus_workflow/_docs_freshness_planning.py"
    ) in result.lines
    assert any(line.startswith("Hotspot outcome notice:") for line in result.lines)
    assert result.data is not None
    planning = result.data["planning_gates"]
    assert planning["required"] is True
    assert planning["hotspot_paths"] == [
        "tools/horadus/python/horadus_workflow/_docs_freshness_planning.py"
    ]
    assert planning["hotspot_outcome_notice"] is not None


def test_hotspot_outcome_notice_mentions_authoritative_artifact() -> None:
    notice = planning_context_module._hotspot_outcome_notice(
        hotspot_paths=["src/core/hotspot.py"],
        authoritative_path="tasks/exec_plans/TASK-999.md",
        hotspot_outcome_value=None,
    )

    assert notice is not None
    assert "tasks/exec_plans/TASK-999.md" in notice
