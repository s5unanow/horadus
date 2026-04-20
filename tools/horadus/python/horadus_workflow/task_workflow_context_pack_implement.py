from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from tools.horadus.python.horadus_workflow import task_workflow_context_pack_spec
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode
from tools.horadus.python.horadus_workflow.task_workflow_context_pack_implement_support import (
    current_sprint_extract,
    derive_test_candidates,
    derived_task_status,
    implement_mode_orientation_documents,
    included_sources_for_implement_mode,
    task_autonomous_eligible,
)
from tools.horadus.python.horadus_workflow.task_workflow_policy import (
    dependency_aware_guidance_statements,
    fallback_guidance_statements,
    workflow_policy_guardrail_statements,
)

if TYPE_CHECKING:
    from tools.horadus.python.horadus_workflow.task_workflow_completion_contract import (
        CompletionContract,
    )

CONTEXT_PACK_DEFAULT_MODE = "default"
CONTEXT_PACK_IMPLEMENT_MODE = "implement"
CONTEXT_PACK_MODES = (CONTEXT_PACK_DEFAULT_MODE, CONTEXT_PACK_IMPLEMENT_MODE)


@dataclass(frozen=True, slots=True)
class ImplementModePolicySource:
    path: str
    source_type: str
    rationale: str


IMPLEMENT_MODE_LEGACY_POLICY_REGISTRY: tuple[ImplementModePolicySource, ...] = (
    ImplementModePolicySource(
        path="AGENTS.md",
        source_type="canonical-policy",
        rationale="Canonical source-of-truth hierarchy, workflow, branching, and completion rules.",
    ),
    ImplementModePolicySource(
        path="docs/AGENT_RUNBOOK.md",
        source_type="operator-runbook",
        rationale="Command index and validation guidance for task implementation workflows.",
    ),
    ImplementModePolicySource(
        path="docs/rfc/001-agent-context-retrieval.md",
        source_type="retrieval-rfc",
        rationale="Approved RFC-001 Phase 1 context-pack retrieval contract.",
    ),
    ImplementModePolicySource(
        path="tasks/specs/TEMPLATE.md",
        source_type="planning-template",
        rationale="Planning-gate and task-spec contract while policy front matter is deferred.",
    ),
)


def implement_mode_legacy_policy_registry() -> tuple[ImplementModePolicySource, ...]:
    return IMPLEMENT_MODE_LEGACY_POLICY_REGISTRY


def context_pack_mode_result(args: Any) -> str | CommandResult:
    mode = getattr(args, "mode", CONTEXT_PACK_DEFAULT_MODE)
    if mode not in CONTEXT_PACK_MODES:
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=[
                "--mode must be one of: " + ", ".join(CONTEXT_PACK_MODES),
            ],
        )
    if mode == CONTEXT_PACK_IMPLEMENT_MODE and getattr(args, "output_format", "text") != "json":
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=["context-pack --mode implement requires --format json"],
        )
    return mode


def implement_mode_context_pack_result(
    *,
    task_payload: dict[str, object],
    declared_paths: list[str],
    sprint_lines: list[str],
    spec_paths: list[str],
    spec_resolution: Mapping[str, object],
    planning: dict[str, object],
    workflow_commands: list[str],
    suggested_validation_commands: list[str],
    completion_contract: CompletionContract,
    validation_packs: Sequence[Mapping[str, object]],
    pre_push_review: Mapping[str, object],
    include_archive: bool,
) -> CommandResult:
    return task_workflow_context_pack_spec.ambiguous_spec_resolution_result(
        spec_resolution
    ) or CommandResult(
        data=_implement_context_pack_payload(
            task_payload=task_payload,
            declared_paths=declared_paths,
            sprint_lines=sprint_lines,
            spec_paths=spec_paths,
            spec_resolution=spec_resolution,
            planning=planning,
            workflow_commands=workflow_commands,
            suggested_validation_commands=suggested_validation_commands,
            completion_contract=completion_contract,
            validation_packs=validation_packs,
            pre_push_review=pre_push_review,
            policy_payload=_implement_mode_policy_payload(workflow_commands=workflow_commands),
            excluded_sources=task_workflow_context_pack_spec.implement_mode_excluded_sources(
                include_archive
            ),
        ),
    )


def implement_mode_workflow_commands(
    *, task_id: str, workflow_commands: list[str], include_archive: bool, archived: bool
) -> list[str]:
    default_context_pack = f"uv run --no-sync horadus tasks context-pack {task_id}"
    implement_context_pack = (
        f"{default_context_pack} --mode implement --format json"
        if not (include_archive and archived)
        else f"{default_context_pack} --include-archive --mode implement --format json"
    )
    return [
        implement_context_pack if command.startswith(default_context_pack) else command
        for command in workflow_commands
    ]


def _implement_context_pack_payload(
    *,
    task_payload: dict[str, object],
    declared_paths: list[str],
    sprint_lines: list[str],
    spec_paths: list[str],
    spec_resolution: Mapping[str, object],
    planning: dict[str, object],
    workflow_commands: list[str],
    suggested_validation_commands: list[str],
    completion_contract: CompletionContract,
    validation_packs: Sequence[Mapping[str, object]],
    pre_push_review: Mapping[str, object],
    policy_payload: Mapping[str, object],
    excluded_sources: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    autonomous_eligible = task_autonomous_eligible(
        title=task_payload.get("title"),
        sprint_lines=sprint_lines,
    )
    return {
        "mode_metadata": {
            "mode": "implement",
            "schema_version": "context_pack_implement_v1",
            "format": "json",
            "default_mode_preserved": True,
        },
        "task_metadata": _implement_task_metadata(
            task_payload,
            declared_paths,
            autonomous_eligible=autonomous_eligible,
        ),
        "orientation": {
            "documents": [asdict(document) for document in implement_mode_orientation_documents()],
            "current_sprint": current_sprint_extract(str(task_payload.get("task_id") or "")),
        },
        "derived_test_candidates": derive_test_candidates(declared_paths=declared_paths),
        "retrieval_sources": {
            "included": _included_sources(
                task_payload,
                sprint_lines,
                spec_paths,
                planning,
            ),
            "excluded": list(excluded_sources),
            "task_spec_resolution": dict(spec_resolution),
        },
        "planning_gates": planning,
        "workflow": {
            "commands": workflow_commands,
            "suggested_validation_commands": suggested_validation_commands,
            "completion_contract": completion_contract,
            "caller_aware_validation_packs": list(validation_packs),
            "pre_push_review_guidance": dict(pre_push_review),
        },
        "policy": policy_payload,
    }


def _implement_task_metadata(
    task_payload: Mapping[str, object],
    declared_paths: list[str],
    *,
    autonomous_eligible: bool,
) -> dict[str, object]:
    return {
        "task_id": task_payload.get("task_id"),
        "title": task_payload.get("title"),
        "status": task_payload.get("status"),
        "task_status": derived_task_status(task_payload),
        "autonomous_eligible": autonomous_eligible,
        "archived": task_payload.get("archived", False),
        "priority": task_payload.get("priority"),
        "estimate": task_payload.get("estimate"),
        "source_path": task_payload.get("source_path"),
        "backlog_path": task_payload.get("backlog_path"),
        "current_sprint_path": task_payload.get("current_sprint_path"),
        "description": task_payload.get("description", []),
        "acceptance_criteria": task_payload.get("acceptance_criteria", []),
        "declared_paths": declared_paths,
    }


def _included_sources(
    task_payload: Mapping[str, object],
    sprint_lines: Sequence[str],
    spec_paths: Sequence[str],
    planning: Mapping[str, object],
) -> list[dict[str, object]]:
    return included_sources_for_implement_mode(
        task_payload=task_payload,
        sprint_lines=sprint_lines,
        spec_paths=spec_paths,
        planning=planning,
    )


def _implement_mode_policy_payload(
    *,
    workflow_commands: list[str],
) -> dict[str, object]:
    return {
        "source_modules": {
            "policy_registry": (
                "tools.horadus.python.horadus_workflow.task_workflow_context_pack_implement"
            ),
            "policy_projection": "tools.horadus.python.horadus_workflow.task_workflow_policy",
        },
        "legacy_policy_registry": {
            "registry_id": "implement-mode-legacy-policy-v1",
            "front_matter_required": False,
            "entries": [asdict(source) for source in implement_mode_legacy_policy_registry()],
        },
        "code_backed_policy": {
            "workflow_commands": workflow_commands,
            "workflow_payload_refs": [
                "workflow.completion_contract",
                "workflow.caller_aware_validation_packs",
                "workflow.pre_push_review_guidance",
            ],
            "dependency_aware_guidance": list(dependency_aware_guidance_statements()),
            "fallback_guidance": list(fallback_guidance_statements()),
            "workflow_policy_guardrails": list(workflow_policy_guardrail_statements()),
        },
    }


__all__ = [
    "CONTEXT_PACK_DEFAULT_MODE",
    "CONTEXT_PACK_IMPLEMENT_MODE",
    "CONTEXT_PACK_MODES",
    "IMPLEMENT_MODE_LEGACY_POLICY_REGISTRY",
    "ImplementModePolicySource",
    "context_pack_mode_result",
    "implement_mode_context_pack_result",
    "implement_mode_legacy_policy_registry",
    "implement_mode_workflow_commands",
]
