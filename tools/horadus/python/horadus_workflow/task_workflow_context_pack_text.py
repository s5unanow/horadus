from __future__ import annotations

from typing import TYPE_CHECKING

from tools.horadus.python.horadus_workflow.result import CommandResult
from tools.horadus.python.horadus_workflow.task_workflow_context_pack_support import (
    append_planning_context_lines,
    context_pack_payload,
)

if TYPE_CHECKING:
    from tools.horadus.python.horadus_workflow.task_workflow_completion_contract import (
        CompletionContract,
    )
    from tools.horadus.python.horadus_workflow.task_workflow_query import (
        CallerAwareValidationPackMatch,
        PrePushReviewGuidance,
    )


def default_context_pack_result(
    *,
    task_id: str,
    task_payload: dict[str, object],
    raw_block: str,
    sprint_lines: list[str],
    spec_paths: list[str],
    planning: dict[str, object],
    likely_code_areas: list[str],
    workflow_commands: list[str],
    suggested_validation_commands: list[str],
    completion_contract: CompletionContract,
    validation_packs: list[CallerAwareValidationPackMatch],
    pre_push_review: PrePushReviewGuidance,
    canonical_spec_example_path: str,
) -> CommandResult:
    lines = [
        f"# Context Pack: {task_id}",
        "",
        "## Backlog Entry",
        raw_block,
        "",
        "## Sprint Status",
    ]
    lines.extend(sprint_lines or ["(not listed in current sprint)"])
    lines.extend(["", "## Matching Spec"])
    lines.extend(spec_paths or ["(none)"])
    lines.extend(
        [
            "",
            "## Spec Contract Template",
            "tasks/specs/TEMPLATE.md",
            canonical_spec_example_path,
        ]
    )
    append_planning_context_lines(lines, planning)
    lines.extend(["", "## Likely Code Areas"])
    lines.extend(likely_code_areas or ["(not specified in backlog entry)"])
    lines.extend(["", "## Suggested Workflow Commands", *workflow_commands])
    lines.extend(["", "## Suggested Validation Commands", *suggested_validation_commands])
    append_completion_contract_lines(lines, completion_contract)
    append_caller_aware_validation_pack_lines(lines, validation_packs)
    append_pre_push_review_guidance_lines(lines, pre_push_review)
    return CommandResult(
        lines=lines,
        data=context_pack_payload(
            task_payload=task_payload,
            sprint_lines=sprint_lines,
            spec_paths=spec_paths,
            planning=planning,
            workflow_commands=workflow_commands,
            suggested_validation_commands=suggested_validation_commands,
            completion_contract=completion_contract,
            validation_packs=validation_packs,
            pre_push_review=pre_push_review,
            canonical_spec_example_path=canonical_spec_example_path,
        ),
    )


def append_completion_contract_lines(lines: list[str], contract: CompletionContract) -> None:
    lines.extend(["", "## Completion Contract", "Already enforced by tooling:"])
    for requirement in contract["enforced_requirements"]:
        lines.append(f"- {requirement['summary']}")
        lines.append(f"  Reason: {requirement['reason']}")
        if requirement["commands"]:
            lines.append(f"  Commands: {', '.join(requirement['commands'])}")
        lines.append(f"  Note: {requirement['note']}")
    lines.append("")
    lines.append("Still documented / operator-owned expectations:")
    for requirement in contract["documented_requirements"]:
        lines.append(f"- [{requirement['status']}] {requirement['summary']}")
        lines.append(f"  Reason: {requirement['reason']}")
        if requirement["commands"]:
            lines.append(f"  Commands: {', '.join(requirement['commands'])}")
        lines.append(f"  Note: {requirement['note']}")


def append_caller_aware_validation_pack_lines(
    lines: list[str], validation_packs: list[CallerAwareValidationPackMatch]
) -> None:
    if not validation_packs:
        return
    lines.extend(["", "## Caller-Aware Validation Packs", "Applicability: recommended"])
    for pack in validation_packs:
        lines.append(f"- {pack['pack_id']}: {pack['rationale']}")
        lines.append(f"  Matched paths: {', '.join(pack['matched_paths'])}")
        lines.append("  Commands:")
        lines.extend(f"  {command}" for command in pack["commands"])


def append_pre_push_review_guidance_lines(
    lines: list[str], guidance: PrePushReviewGuidance
) -> None:
    if not guidance["recommended"]:
        return
    lines.extend(["", "## Pre-Push Review Guidance", "Applicability: recommended"])
    lines.extend(f"- {reason}" for reason in guidance["risk_reasons"])
    lines.extend(["", "Suggested commands:"])
    lines.extend(guidance["commands"])
    lines.extend(["", "Fallback guidance:"])
    lines.extend(f"- {note}" for note in guidance["fallback_notes"])
    lines.extend(["", "Re-review discipline:"])
    lines.extend(f"- {note}" for note in guidance["batching_notes"])


__all__ = [
    "append_caller_aware_validation_pack_lines",
    "append_completion_contract_lines",
    "append_pre_push_review_guidance_lines",
    "default_context_pack_result",
]
