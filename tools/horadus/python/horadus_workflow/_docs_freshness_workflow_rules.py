from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._docs_freshness_models import DocsFreshnessIssue
from ._docs_freshness_parsing import _normalize_whitespace

if TYPE_CHECKING:
    from ._docs_freshness_config import DocsFreshnessCheckConfig


_GUIDANCE_RULES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "completion_guidance_reference_paths",
        "completion_guidance_statements",
        "completion_guidance_reference_file_missing",
        "completion guidance",
        "completion_guidance_statement_missing",
    ),
    (
        "dependency_aware_guidance_reference_paths",
        "dependency_aware_guidance_statements",
        "dependency_guidance_reference_file_missing",
        "dependency-aware workflow guidance",
        "dependency_guidance_statement_missing",
    ),
    (
        "fallback_guidance_reference_paths",
        "fallback_guidance_statements",
        "fallback_guidance_reference_file_missing",
        "fallback workflow guidance",
        "fallback_guidance_statement_missing",
    ),
    (
        "workflow_policy_guardrail_reference_paths",
        "workflow_policy_guardrail_statements",
        "workflow_policy_guardrail_reference_file_missing",
        "workflow/policy guardrail guidance",
        "workflow_policy_guardrail_statement_missing",
    ),
)


def check_hierarchy_policy(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
    hierarchy_policy_path = repo_root / config.hierarchy_policy_path
    if not hierarchy_policy_path.exists():
        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="hierarchy_policy_file_missing",
                message=f"Missing hierarchy policy file: {config.hierarchy_policy_path}",
                path=config.hierarchy_policy_path,
            )
        )
    else:
        hierarchy_policy = hierarchy_policy_path.read_text(encoding="utf-8")
        if config.hierarchy_policy_heading not in hierarchy_policy:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="hierarchy_policy_heading_missing",
                    message=(
                        f"AGENTS.md missing hierarchy heading: '{config.hierarchy_policy_heading}'."
                    ),
                    path=config.hierarchy_policy_path,
                )
            )

    for reference_path in config.hierarchy_policy_reference_files:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="hierarchy_policy_reference_file_missing",
                    message=f"Missing hierarchy reference file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        content = file_path.read_text(encoding="utf-8")
        if "AGENTS.md" in content and config.hierarchy_policy_reference_text in content:
            continue

        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="hierarchy_policy_reference_missing",
                message=(
                    f"{reference_path} must reference AGENTS hierarchy policy "
                    f"('{config.hierarchy_policy_reference_text}')."
                ),
                path=reference_path,
            )
        )


def check_workflow_references(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
    for reference_path in config.workflow_reference_paths:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_reference_file_missing",
                    message=f"Missing workflow reference file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        content = file_path.read_text(encoding="utf-8")
        for command_template in config.workflow_command_templates:
            if command_template in content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_command_reference_missing",
                    message=(
                        f"{reference_path} must document canonical workflow command: "
                        f"{command_template}"
                    ),
                    path=reference_path,
                )
            )
        if _normalize_whitespace(config.workflow_escape_hatch_text) not in _normalize_whitespace(
            content
        ):
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_escape_hatch_missing",
                    message=(
                        f"{reference_path} must include the canonical raw git/gh escape-hatch "
                        "guidance."
                    ),
                    path=reference_path,
                )
            )


def check_safe_start_references(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
    for reference_path in config.canonical_safe_start_reference_paths:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="safe_start_reference_file_missing",
                    message=f"Missing safe-start reference file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        content = file_path.read_text(encoding="utf-8")
        if config.canonical_safe_start_command not in content:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="safe_start_reference_missing",
                    message=(
                        f"{reference_path} must include the canonical guarded task-start "
                        f"command: {config.canonical_safe_start_command}"
                    ),
                    path=reference_path,
                )
            )
        if (
            reference_path in config.stale_task_start_forbidden_reference_paths
            and config.stale_lower_level_task_start_command in content
        ):
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="stale_task_start_reference_present",
                    message=(
                        f"{reference_path} must not teach the stale lower-level task-start "
                        f"command: {config.stale_lower_level_task_start_command}"
                    ),
                    path=reference_path,
                )
            )


def check_guidance_references(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
    for (
        reference_paths_attr,
        statements_attr,
        missing_rule_id,
        message_prefix,
        statement_rule_id,
    ) in _GUIDANCE_RULES:
        reference_paths = getattr(config, reference_paths_attr)
        statements = getattr(config, statements_attr)
        for path_text in reference_paths:
            file_path = repo_root / path_text
            if not file_path.exists():
                errors.append(
                    DocsFreshnessIssue(
                        level="error",
                        rule_id=missing_rule_id,
                        message=f"Missing {message_prefix} file: {path_text}",
                        path=path_text,
                    )
                )
                continue

            normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
            for statement in statements:
                if _normalize_whitespace(statement) in normalized_content:
                    continue
                errors.append(
                    DocsFreshnessIssue(
                        level="error",
                        rule_id=statement_rule_id,
                        message=f"{path_text} must include canonical {message_prefix}: {statement}",
                        path=path_text,
                    )
                )


def check_thin_workflow_surfaces(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
    for reference_path in config.thin_workflow_surfaces:
        file_path = repo_root / reference_path
        if not file_path.exists():
            continue
        normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
        for statement in config.thin_surface_forbidden_policy_statements:
            if _normalize_whitespace(statement) not in normalized_content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_policy_statement_duplicated_outside_agents",
                    message=(
                        f"{reference_path} must stay thin and must not duplicate "
                        "canonical workflow-policy statements owned by AGENTS.md."
                    ),
                    path=reference_path,
                )
            )
