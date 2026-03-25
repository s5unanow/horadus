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
_RUNTIME_TARGETED_TEST_PREFIXES = ("src/", "alembic/")
_WORKFLOW_TARGETED_TEST_PREFIXES = ("tools/", "scripts/", ".github/workflows/", "config/")
_WORKFLOW_TARGETED_TEST_EXACT_PATHS = (
    "Makefile",
    ".pre-commit-config.yaml",
    "pyproject.toml",
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


def _docs_update_required(normalized_paths: list[str]) -> bool:
    return _matches_path_rule(
        normalized_paths,
        prefixes=_DOC_UPDATE_REQUIRED_PREFIXES,
        exact_paths=_DOC_UPDATE_REQUIRED_EXACT_PATHS,
    ) or any(
        path.startswith(prefix) for prefix in _SHARED_WORKFLOW_PREFIXES for path in normalized_paths
    )


def _requirement_status(*, required: bool, scope_declared: bool) -> str:
    if required:
        return "required"
    if scope_declared:
        return "not_applicable"
    return "conditional"


def _fallback_targeted_validation_commands(normalized_paths: list[str]) -> list[str]:
    commands: list[str] = []
    if any(
        path.startswith(prefix)
        for prefix in _RUNTIME_TARGETED_TEST_PREFIXES
        for path in normalized_paths
    ):
        commands.append("uv run --no-sync pytest tests/unit/ -v -m unit")
    if _matches_path_rule(
        normalized_paths,
        prefixes=_WORKFLOW_TARGETED_TEST_PREFIXES,
        exact_paths=_WORKFLOW_TARGETED_TEST_EXACT_PATHS,
    ):
        commands.append("uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit")
    return commands


def _targeted_tests_requirement(
    *,
    required: bool,
    scope_declared: bool,
    waiver_home_display: str,
    commands: list[str],
) -> CompletionContractRequirement:
    return {
        "requirement_id": "targeted-tests",
        "status": _requirement_status(required=required, scope_declared=scope_declared),
        "summary": "Run relevant targeted tests for code, config, or workflow changes before claiming completion.",
        "reason": (
            "task files declare code/config/runtime surfaces"
            if required
            else (
                "task files only declare docs/ledger-style surfaces"
                if scope_declared
                else "task does not declare file scope"
            )
        ),
        "commands": commands if required else [],
        "note": (
            "`make agent-check` and `uv run --no-sync horadus tasks local-gate --full` remain the baseline gates."
            if required
            else (
                f"Record the targeted-test N/A in {waiver_home_display}."
                if scope_declared
                else "Inspect the task scope and run the relevant targeted tests before treating this as N/A."
            )
        ),
    }


def _integration_requirement(
    *,
    required: bool,
    scope_declared: bool,
    waiver_home_display: str,
) -> CompletionContractRequirement:
    return {
        "requirement_id": "integration-proof",
        "status": _requirement_status(required=required, scope_declared=scope_declared),
        "summary": "Run local integration proof when the task touches integration-covered or push/PR workflow surfaces.",
        "reason": (
            "task files declare integration-covered or push/PR workflow paths"
            if required
            else (
                "task files do not declare integration-covered or push/PR workflow paths"
                if scope_declared
                else "task does not declare file scope"
            )
        ),
        "commands": [targeted_integration_validation_command()] if required else [],
        "note": (
            "`uv run --no-sync horadus tasks local-gate --full` stays the canonical strict gate; this is the focused integration proof."
            if required
            else (
                f"Record the integration-proof N/A in {waiver_home_display}."
                if scope_declared
                else "Confirm whether the task touches integration-covered or push/PR workflow paths before recording N/A."
            )
        ),
    }


def _docs_updates_requirement(
    *, required: bool, waiver_home_display: str
) -> CompletionContractRequirement:
    return {
        "requirement_id": "docs-updates",
        "status": "required" if required else "conditional",
        "summary": "Update docs in the same branch when behavior, workflow, or operator-facing contracts change.",
        "reason": (
            "task files declare workflow/policy/operator-facing surfaces"
            if required
            else "docs applicability depends on whether the implementation changes user-facing behavior"
        ),
        "commands": [],
        "note": (
            "Update AGENTS/runbook/README or other operator-facing docs alongside the code."
            if required
            else f"If docs are unchanged, record that N/A decision in {waiver_home_display}."
        ),
    }


def _na_recording_requirement(waiver_home_display: str) -> CompletionContractRequirement:
    return {
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
            f"Record N/A or waiver decisions under `Gate Outcomes / Waivers` in {waiver_home_display}."
            if waiver_home_display != "same-branch task notes"
            else "Record N/A or waiver decisions in the task's same-branch notes and PR summary."
        ),
    }


def _documented_requirements(
    *,
    normalized_paths: list[str],
    validation_pack_commands: list[str],
    waiver_home_display: str,
) -> list[CompletionContractRequirement]:
    scope_declared = bool(normalized_paths)
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
    docs_update_required = _docs_update_required(normalized_paths)
    targeted_test_commands = validation_pack_commands or _fallback_targeted_validation_commands(
        normalized_paths
    )

    return [
        _targeted_tests_requirement(
            required=targeted_test_required,
            scope_declared=scope_declared,
            waiver_home_display=waiver_home_display,
            commands=targeted_test_commands,
        ),
        _integration_requirement(
            required=integration_required,
            scope_declared=scope_declared,
            waiver_home_display=waiver_home_display,
        ),
        _docs_updates_requirement(
            required=docs_update_required, waiver_home_display=waiver_home_display
        ),
        _na_recording_requirement(waiver_home_display),
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
