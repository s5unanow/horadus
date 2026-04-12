from __future__ import annotations

import pytest

import tools.horadus.python.horadus_workflow.task_workflow_context_pack_support as context_pack_support_module

pytestmark = pytest.mark.unit


def test_append_planning_context_lines_skips_non_required_planning_state() -> None:
    lines = ["header"]

    context_pack_support_module.append_planning_context_lines(
        lines,
        {
            "required": False,
            "state": "non_applicable",
            "marker_value": None,
            "marker_source": None,
            "authoritative_artifact_path": None,
            "gate_home_path": None,
            "waiver_home_path": None,
            "missing_artifact_notice": None,
            "canonical_example_path": "tasks/specs/275-finish-review-gate-timeout.md",
        },
    )

    assert lines == ["header"]


def test_append_planning_context_lines_renders_hotspot_outcome_without_notice() -> None:
    lines: list[str] = []

    context_pack_support_module.append_planning_context_lines(
        lines,
        {
            "required": True,
            "state": "applicable_with_authoritative_artifact_present",
            "marker_value": "Required — fixture",
            "marker_source": "tasks/exec_plans/TASK-912.md",
            "authoritative_artifact_path": "tasks/exec_plans/TASK-912.md",
            "gate_home_path": "tasks/exec_plans/TASK-912.md",
            "waiver_home_path": "tasks/exec_plans/TASK-912.md",
            "missing_artifact_notice": None,
            "canonical_example_path": "tasks/specs/275-finish-review-gate-timeout.md",
            "hotspot_paths": ["src/core/hotspot.py"],
            "hotspot_outcome_value": "reduce — fixture",
            "hotspot_outcome_source": "tasks/exec_plans/TASK-912.md",
            "hotspot_outcome_notice": None,
        },
    )

    assert "Allowlisted production hotspots: src/core/hotspot.py" in lines
    assert any(line.startswith("Hotspot Outcome: reduce — fixture") for line in lines)
    assert not any(line.startswith("Hotspot outcome notice:") for line in lines)


def test_context_pack_payload_keeps_expected_keys() -> None:
    payload = context_pack_support_module.context_pack_payload(
        task_payload={"task_id": "TASK-912"},
        sprint_lines=["- TASK-912"],
        spec_paths=["tasks/specs/912.md"],
        planning={"required": False},
        workflow_commands=["uv run --no-sync horadus tasks context-pack TASK-912"],
        suggested_validation_commands=["make agent-check"],
        completion_contract={"enforced_requirements": [], "documented_requirements": []},
        validation_packs=[],
        pre_push_review={"recommended": False},
        canonical_spec_example_path="tasks/specs/275-finish-review-gate-timeout.md",
    )

    assert payload["task"] == {"task_id": "TASK-912"}
    assert payload["spec_template_path"] == "tasks/specs/TEMPLATE.md"
    assert payload["pre_push_review_guidance"] == {"recommended": False}
