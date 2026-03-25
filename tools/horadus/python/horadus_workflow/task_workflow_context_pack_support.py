from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.horadus.python.horadus_workflow.task_workflow_completion_contract import (
        CompletionContract,
    )


def append_planning_context_lines(lines: list[str], planning: dict[str, object]) -> None:
    if not planning["required"]:
        return
    lines.extend(
        ["", "## Planning Gates", "Applicability: required", f"State: {planning['state']}"]
    )
    if planning["marker_value"] is not None:
        lines.append(
            f"Marker: {planning['marker_value']} ({planning['marker_source'] or 'unknown source'})"
        )
    if planning["authoritative_artifact_path"] is not None:
        lines.append(f"Authoritative planning artifact: {planning['authoritative_artifact_path']}")
    if planning["gate_home_path"] is not None:
        lines.append(f"Phase -1 gates home: {planning['gate_home_path']}")
    if planning["waiver_home_path"] is not None:
        lines.append(f"Gate Outcomes / Waivers home: {planning['waiver_home_path']}")
    if planning["missing_artifact_notice"] is not None:
        lines.append(f"Missing artifact notice: {planning['missing_artifact_notice']}")
    lines.append(f"Canonical example: {planning['canonical_example_path']}")


def context_pack_payload(
    *,
    task_payload: dict[str, object],
    sprint_lines: list[str],
    spec_paths: list[str],
    planning: dict[str, object],
    workflow_commands: list[str],
    suggested_validation_commands: list[str],
    completion_contract: CompletionContract,
    validation_packs: Sequence[Mapping[str, object]],
    pre_push_review: Mapping[str, object],
    canonical_spec_example_path: str,
) -> dict[str, object]:
    return {
        "task": task_payload,
        "sprint_lines": sprint_lines,
        "spec_paths": spec_paths,
        "spec_template_path": "tasks/specs/TEMPLATE.md",
        "canonical_spec_example_path": canonical_spec_example_path,
        "planning_gates": planning,
        "suggested_workflow_commands": workflow_commands,
        "suggested_validation_commands": suggested_validation_commands,
        "completion_contract": completion_contract,
        "caller_aware_validation_packs": validation_packs,
        "pre_push_review_guidance": pre_push_review,
    }


__all__ = ["append_planning_context_lines", "context_pack_payload"]
