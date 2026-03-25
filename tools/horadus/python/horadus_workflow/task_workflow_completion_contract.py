from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from tools.horadus.python.horadus_workflow.task_workflow_policy import (
    default_validation_commands,
    targeted_integration_validation_command,
)

_CODE_OR_CONFIG_PREFIXES = (
    "src/",
    "tools/",
    "scripts/",
    "alembic/",
    ".github/workflows/",
    "config/",
)
_CODE_OR_CONFIG_EXACT_PATHS = (
    "Makefile",
    ".pre-commit-config.yaml",
    "pyproject.toml",
)
_INTEGRATION_REQUIRED_PREFIXES = (
    "src/",
    "alembic/",
    "tools/horadus/python/horadus_cli/",
    "tools/horadus/python/horadus_workflow/",
    "scripts/prepush_",
    "scripts/finish_task_",
    "scripts/test_integration_",
)
_INTEGRATION_REQUIRED_EXACT_PATHS = (
    "Makefile",
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
)
_DOC_UPDATE_REQUIRED_PREFIXES = (
    "docs/",
    "ops/skills/",
    "agents/automation/",
    "tools/horadus/python/horadus_cli/",
    "tools/horadus/python/horadus_workflow/",
)
_DOC_UPDATE_REQUIRED_EXACT_PATHS = (
    "AGENTS.md",
    "README.md",
    "PROJECT_STATUS.md",
    "Makefile",
    ".github/workflows/ci.yml",
)
_SHARED_WORKFLOW_PREFIXES = (
    "tools/horadus/python/horadus_workflow/task_workflow_",
    "tools/horadus/python/horadus_workflow/_task_",
    "tools/horadus/python/horadus_workflow/_docs_freshness_",
    "tools/horadus/python/horadus_workflow/pr_review_gate",
    "tools/horadus/python/horadus_cli/task_",
    "tools/horadus/python/horadus_cli/_task_",
)


class CompletionContractRequirement(TypedDict):
    requirement_id: str
    status: str
    summary: str
    reason: str
    commands: list[str]
    note: str


class CompletionContract(TypedDict):
    enforced_requirements: list[CompletionContractRequirement]
    documented_requirements: list[CompletionContractRequirement]


def _matches_path_rule(
    paths: list[str], *, prefixes: tuple[str, ...], exact_paths: tuple[str, ...]
) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes for path in paths) or any(
        path in exact_paths for path in paths
    )


def _documented_requirements(
    *,
    normalized_paths: list[str],
    validation_pack_commands: list[str],
    waiver_home_display: str,
) -> list[CompletionContractRequirement]:
    targeted_test_required = _matches_path_rule(
        normalized_paths,
        prefixes=_CODE_OR_CONFIG_PREFIXES,
        exact_paths=_CODE_OR_CONFIG_EXACT_PATHS,
    )
    integration_required = _matches_path_rule(
        normalized_paths,
        prefixes=_INTEGRATION_REQUIRED_PREFIXES,
        exact_paths=_INTEGRATION_REQUIRED_EXACT_PATHS,
    )
    docs_update_required = _matches_path_rule(
        normalized_paths,
        prefixes=_DOC_UPDATE_REQUIRED_PREFIXES,
        exact_paths=_DOC_UPDATE_REQUIRED_EXACT_PATHS,
    ) or any(
        path.startswith(prefix) for prefix in _SHARED_WORKFLOW_PREFIXES for path in normalized_paths
    )

    return [
        {
            "requirement_id": "targeted-tests",
            "status": "required" if targeted_test_required else "not_applicable",
            "summary": (
                "Run relevant targeted tests for code, config, or workflow changes before "
                "claiming completion."
            ),
            "reason": (
                "task files declare code/config/runtime surfaces"
                if targeted_test_required
                else "task files only declare docs/ledger-style surfaces"
            ),
            "commands": validation_pack_commands,
            "note": (
                "`make agent-check` and `uv run --no-sync horadus tasks local-gate --full` "
                "remain the baseline gates."
                if targeted_test_required
                else f"Record the targeted-test N/A in {waiver_home_display}."
            ),
        },
        {
            "requirement_id": "integration-proof",
            "status": "required" if integration_required else "not_applicable",
            "summary": (
                "Run local integration proof when the task touches integration-covered or "
                "push/PR workflow surfaces."
            ),
            "reason": (
                "task files declare integration-covered or push/PR workflow paths"
                if integration_required
                else "task files do not declare integration-covered or push/PR workflow paths"
            ),
            "commands": [targeted_integration_validation_command()] if integration_required else [],
            "note": (
                "`uv run --no-sync horadus tasks local-gate --full` stays the canonical "
                "strict gate; this is the focused integration proof."
                if integration_required
                else f"Record the integration-proof N/A in {waiver_home_display}."
            ),
        },
        {
            "requirement_id": "docs-updates",
            "status": "required" if docs_update_required else "conditional",
            "summary": (
                "Update docs in the same branch when behavior, workflow, or operator-facing "
                "contracts change."
            ),
            "reason": (
                "task files declare workflow/policy/operator-facing surfaces"
                if docs_update_required
                else "docs applicability depends on whether the implementation changes user-facing behavior"
            ),
            "commands": [],
            "note": (
                "Update AGENTS/runbook/README or other operator-facing docs alongside the code."
                if docs_update_required
                else f"If docs are unchanged, record that N/A decision in {waiver_home_display}."
            ),
        },
        {
            "requirement_id": "n-a-recording",
            "status": "required",
            "summary": "Document any skipped normal proof as an explicit N/A or waiver.",
            "reason": (
                f"planning artifact available at {waiver_home_display}"
                if waiver_home_display != "same-branch task notes"
                else "no authoritative planning artifact is available for this task"
            ),
            "commands": [],
            "note": (
                f"Record N/A or waiver decisions under `Gate Outcomes / Waivers` in "
                f"{waiver_home_display}."
                if waiver_home_display != "same-branch task notes"
                else "Record N/A or waiver decisions in the task's same-branch notes and PR summary."
            ),
        },
    ]


def build_completion_contract(
    task_id: str,
    *,
    normalized_paths: list[str],
    planning: Mapping[str, object],
    validation_pack_commands: list[str],
) -> CompletionContract:
    waiver_home_path = planning.get("waiver_home_path")
    waiver_home_display = str(waiver_home_path) if waiver_home_path else "same-branch task notes"
    filtered_validation_pack_commands = [
        command
        for command in validation_pack_commands
        if command not in default_validation_commands()
    ]

    return {
        "enforced_requirements": [
            {
                "requirement_id": "canonical-local-gate",
                "status": "required",
                "summary": (
                    "`uv run --no-sync horadus tasks local-gate --full` is the canonical "
                    "strict post-task local gate."
                ),
                "reason": "repo workflow policy defines the strict local completion gate",
                "commands": ["uv run --no-sync horadus tasks local-gate --full"],
                "note": "Do not replace it with a narrower gate command.",
            },
            {
                "requirement_id": "finish-lifecycle",
                "status": "required",
                "summary": (
                    "Complete the branch/PR lifecycle with `horadus tasks finish` and the "
                    "strict lifecycle verifier."
                ),
                "reason": "repo workflow policy treats local commits/tests as checkpoints, not completion",
                "commands": [
                    f"uv run --no-sync horadus tasks finish {task_id}",
                    f"uv run --no-sync horadus tasks lifecycle {task_id} --strict",
                ],
                "note": "Do not stop at a local commit boundary or green local tests.",
            },
        ],
        "documented_requirements": _documented_requirements(
            normalized_paths=normalized_paths,
            validation_pack_commands=filtered_validation_pack_commands,
            waiver_home_display=waiver_home_display,
        ),
    }


__all__ = [
    "CompletionContract",
    "CompletionContractRequirement",
    "build_completion_contract",
]
