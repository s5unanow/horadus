from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from re import Pattern

from ._docs_freshness_models import (
    DocsFreshnessIssue,
    DocsFreshnessResult,
    _ConflictRule,
    _MarkerRequirement,
    _Override,
)
from ._docs_freshness_parsing import (
    _extract_current_sprint_active_tasks,
    _extract_human_blocker_metadata,
    _extract_telegram_launch_scope,
    _load_overrides,
    _normalize_whitespace,
    _parse_marker_date,
)


@dataclass(frozen=True, slots=True)
class DocsFreshnessCheckConfig:
    required_markers: tuple[_MarkerRequirement, ...]
    conflict_rules: tuple[_ConflictRule, ...]
    hierarchy_policy_path: str
    hierarchy_policy_heading: str
    hierarchy_policy_reference_files: tuple[str, ...]
    hierarchy_policy_reference_text: str
    workflow_reference_paths: tuple[str, ...]
    workflow_command_templates: tuple[str, ...]
    workflow_escape_hatch_text: str
    canonical_safe_start_reference_paths: tuple[str, ...]
    canonical_safe_start_command: str
    stale_task_start_forbidden_reference_paths: tuple[str, ...]
    stale_lower_level_task_start_command: str
    completion_guidance_reference_paths: tuple[str, ...]
    completion_guidance_statements: tuple[str, ...]
    dependency_aware_guidance_reference_paths: tuple[str, ...]
    dependency_aware_guidance_statements: tuple[str, ...]
    fallback_guidance_reference_paths: tuple[str, ...]
    fallback_guidance_statements: tuple[str, ...]
    workflow_policy_guardrail_reference_paths: tuple[str, ...]
    workflow_policy_guardrail_statements: tuple[str, ...]
    adr_reference_pattern: Pattern[str]
    data_model_required_tables: tuple[str, ...]
    archived_doc_path: str
    archived_doc_status_line: str
    archived_doc_required_pointers: tuple[str, ...]
    required_human_blocker_metadata_fields: tuple[str, ...]
    current_sprint_human_blocker_metadata_heading: str
    current_sprint_telegram_scope_heading: str
    project_status_stub_status_line: str
    project_status_stub_required_pointers: tuple[str, ...]
    project_status_archive_pointer_pattern: Pattern[str]
    project_status_archive_guidance: str
    thin_workflow_surfaces: tuple[str, ...]
    thin_surface_forbidden_policy_statements: tuple[str, ...]


def _record_issue(
    *,
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
    active_override_map: dict[tuple[str, str], _Override],
    rule_id: str,
    message: str,
    path: str,
) -> None:
    override = active_override_map.get((rule_id, path))
    if override is not None:
        warnings.append(
            DocsFreshnessIssue(
                level="warning",
                rule_id="docs_freshness_override_applied",
                message=(
                    f"Override active for {rule_id} in {path}: "
                    f"{override.reason} (expires {override.expires_on.isoformat()})"
                ),
                path=path,
            )
        )
        return

    errors.append(
        DocsFreshnessIssue(
            level="error",
            rule_id=rule_id,
            message=message,
            path=path,
        )
    )


def run_docs_freshness_check_impl(
    *,
    repo_root: Path,
    override_path: Path,
    max_age_days: int,
    planning_artifact_paths: tuple[str, ...] | None,
    config: DocsFreshnessCheckConfig,
    changed_planning_artifact_paths: Callable[[Path], tuple[str, ...]],
    validate_planning_artifact: Callable[[Path, str, str], tuple[DocsFreshnessIssue, ...]],
) -> DocsFreshnessResult:
    now = datetime.now(tz=UTC).date()
    overrides = _load_overrides(override_path)
    active_override_map = {
        (item.rule_id, item.path): item for item in overrides if item.expires_on >= now
    }

    errors: list[DocsFreshnessIssue] = []
    warnings: list[DocsFreshnessIssue] = []

    for requirement in config.required_markers:
        file_path = repo_root / requirement.path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="required_marker_file_missing",
                    message=f"Required docs freshness file missing: {requirement.path}",
                    path=requirement.path,
                )
            )
            continue
        content = file_path.read_text(encoding="utf-8")
        marker_date = _parse_marker_date(content, requirement.label)
        if marker_date is None:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="required_marker_missing",
                    message=f"Missing '{requirement.label}' marker in {requirement.path}",
                    path=requirement.path,
                )
            )
            continue
        if marker_date > now:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="required_marker_future_date",
                    message=(
                        f"Future '{requirement.label}' date ({marker_date.isoformat()}) "
                        f"in {requirement.path}"
                    ),
                    path=requirement.path,
                )
            )
            continue
        age_days = (now - marker_date).days
        if age_days > max_age_days:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="required_marker_stale",
                    message=(
                        f"{requirement.path} '{requirement.label}' is stale "
                        f"({age_days} days old; max {max_age_days})"
                    ),
                    path=requirement.path,
                )
            )

    docs_files = list((repo_root / "docs").rglob("*.md"))
    project_status_path = repo_root / "PROJECT_STATUS.md"
    if project_status_path.exists():
        docs_files.append(project_status_path)

    backlog_text = ""
    backlog_file = repo_root / "tasks" / "BACKLOG.md"
    if backlog_file.exists():
        backlog_text = backlog_file.read_text(encoding="utf-8")

    for rule in config.conflict_rules:
        for doc_path in docs_files:
            content = doc_path.read_text(encoding="utf-8")
            if rule.pattern not in content:
                continue
            relative_path = str(doc_path.relative_to(repo_root))
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id=rule.rule_id,
                message=f"{rule.description} Found in {relative_path}",
                path=relative_path,
            )

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

    for reference_paths, statements, missing_rule_id, message_prefix in (
        (
            config.completion_guidance_reference_paths,
            config.completion_guidance_statements,
            "completion_guidance_reference_file_missing",
            "completion guidance",
        ),
        (
            config.dependency_aware_guidance_reference_paths,
            config.dependency_aware_guidance_statements,
            "dependency_guidance_reference_file_missing",
            "dependency-aware workflow guidance",
        ),
        (
            config.fallback_guidance_reference_paths,
            config.fallback_guidance_statements,
            "fallback_guidance_reference_file_missing",
            "fallback workflow guidance",
        ),
        (
            config.workflow_policy_guardrail_reference_paths,
            config.workflow_policy_guardrail_statements,
            "workflow_policy_guardrail_reference_file_missing",
            "workflow/policy guardrail guidance",
        ),
    ):
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
            statement_rule_id = {
                "completion guidance": "completion_guidance_statement_missing",
                "dependency-aware workflow guidance": "dependency_guidance_statement_missing",
                "fallback workflow guidance": "fallback_guidance_statement_missing",
                "workflow/policy guardrail guidance": "workflow_policy_guardrail_statement_missing",
            }[message_prefix]
            for statement in statements:
                if _normalize_whitespace(statement) in normalized_content:
                    continue
                errors.append(
                    DocsFreshnessIssue(
                        level="error",
                        rule_id=statement_rule_id,
                        message=(
                            f"{path_text} must include canonical {message_prefix}: {statement}"
                        ),
                        path=path_text,
                    )
                )

    if project_status_path.exists():
        project_status_text = project_status_path.read_text(encoding="utf-8")
        if config.project_status_stub_status_line not in project_status_text:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_stub_status_missing",
                message=(
                    "PROJECT_STATUS.md must be the non-authoritative archive-pointer stub "
                    f"('{config.project_status_stub_status_line}')."
                ),
                path="PROJECT_STATUS.md",
            )
        missing_project_status_pointers = [
            pointer
            for pointer in config.project_status_stub_required_pointers
            if pointer not in project_status_text
        ]
        if missing_project_status_pointers:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_stub_pointer_missing",
                message=(
                    "PROJECT_STATUS.md missing required live/archive pointers: "
                    + ", ".join(missing_project_status_pointers)
                ),
                path="PROJECT_STATUS.md",
            )
        if config.project_status_archive_pointer_pattern.search(project_status_text) is None:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_stub_archive_pointer_missing",
                message=(
                    "PROJECT_STATUS.md must point to a dated archived status snapshot "
                    "(archive/YYYY-MM-DD-.../PROJECT_STATUS.md)."
                ),
                path="PROJECT_STATUS.md",
            )
        if _normalize_whitespace(
            config.project_status_archive_guidance
        ) not in _normalize_whitespace(project_status_text):
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_archive_guidance_missing",
                message="PROJECT_STATUS.md must say that archive access is opt-in only.",
                path="PROJECT_STATUS.md",
            )

    current_sprint_path = repo_root / "tasks" / "CURRENT_SPRINT.md"
    if current_sprint_path.exists():
        current_sprint = current_sprint_path.read_text(encoding="utf-8")
        active_sprint_tasks, active_requires_human_tasks = _extract_current_sprint_active_tasks(
            current_sprint
        )

        if active_requires_human_tasks:
            blocker_metadata = _extract_human_blocker_metadata(current_sprint)
            for task_id in sorted(active_requires_human_tasks):
                task_metadata = blocker_metadata.get(task_id)
                if task_metadata is None:
                    _record_issue(
                        errors=errors,
                        warnings=warnings,
                        active_override_map=active_override_map,
                        rule_id="human_blocker_metadata_missing",
                        message=(
                            f"{task_id} missing metadata in CURRENT_SPRINT "
                            f"'{config.current_sprint_human_blocker_metadata_heading}' section"
                        ),
                        path="tasks/CURRENT_SPRINT.md",
                    )
                    continue

                missing_fields = [
                    field
                    for field in config.required_human_blocker_metadata_fields
                    if not task_metadata.get(field, "").strip()
                ]
                if missing_fields:
                    _record_issue(
                        errors=errors,
                        warnings=warnings,
                        active_override_map=active_override_map,
                        rule_id="human_blocker_metadata_missing_fields",
                        message=(
                            f"{task_id} metadata missing required fields: "
                            + ", ".join(missing_fields)
                        ),
                        path="tasks/CURRENT_SPRINT.md",
                    )

                parsed_metadata_dates: dict[str, date] = {}
                for date_field in ("last_touched", "next_action"):
                    raw_value = task_metadata.get(date_field, "").strip()
                    if not raw_value:
                        continue
                    try:
                        parsed_date = date.fromisoformat(raw_value)
                    except ValueError:
                        _record_issue(
                            errors=errors,
                            warnings=warnings,
                            active_override_map=active_override_map,
                            rule_id="human_blocker_metadata_invalid_date",
                            message=(
                                f"{task_id} metadata field '{date_field}' must use YYYY-MM-DD "
                                f"(found '{raw_value}')"
                            ),
                            path="tasks/CURRENT_SPRINT.md",
                        )
                        continue
                    parsed_metadata_dates[date_field] = parsed_date
                    if date_field == "last_touched" and parsed_date > now:
                        _record_issue(
                            errors=errors,
                            warnings=warnings,
                            active_override_map=active_override_map,
                            rule_id="human_blocker_metadata_future_date",
                            message=(
                                f"{task_id} metadata field '{date_field}' is in the future "
                                f"({parsed_date.isoformat()})"
                            ),
                            path="tasks/CURRENT_SPRINT.md",
                        )
                if (
                    "last_touched" in parsed_metadata_dates
                    and "next_action" in parsed_metadata_dates
                    and parsed_metadata_dates["next_action"] < parsed_metadata_dates["last_touched"]
                ):
                    _record_issue(
                        errors=errors,
                        warnings=warnings,
                        active_override_map=active_override_map,
                        rule_id="human_blocker_metadata_invalid_date_order",
                        message=(
                            f"{task_id} metadata field 'next_action' must be on/after "
                            "'last_touched'"
                        ),
                        path="tasks/CURRENT_SPRINT.md",
                    )

                escalate_raw = task_metadata.get("escalate_after_days", "").strip()
                if escalate_raw:
                    try:
                        escalate_days = int(escalate_raw)
                    except ValueError:
                        _record_issue(
                            errors=errors,
                            warnings=warnings,
                            active_override_map=active_override_map,
                            rule_id="human_blocker_metadata_invalid_escalation_threshold",
                            message=(
                                f"{task_id} metadata field 'escalate_after_days' must be an "
                                f"integer (found '{escalate_raw}')"
                            ),
                            path="tasks/CURRENT_SPRINT.md",
                        )
                    else:
                        if escalate_days <= 0:
                            _record_issue(
                                errors=errors,
                                warnings=warnings,
                                active_override_map=active_override_map,
                                rule_id="human_blocker_metadata_invalid_escalation_threshold",
                                message=(
                                    f"{task_id} metadata field 'escalate_after_days' must be > 0 "
                                    f"(found '{escalate_days}')"
                                ),
                                path="tasks/CURRENT_SPRINT.md",
                            )

            if (
                "TASK-080" in active_sprint_tasks
                and _extract_telegram_launch_scope(current_sprint) is None
            ):
                _record_issue(
                    errors=errors,
                    warnings=warnings,
                    active_override_map=active_override_map,
                    rule_id="telegram_launch_scope_missing",
                    message=(
                        "TASK-080 is active: CURRENT_SPRINT must define "
                        f"'{config.current_sprint_telegram_scope_heading}' with a launch_scope field"
                    ),
                    path="tasks/CURRENT_SPRINT.md",
                )

    adr_dir = repo_root / "docs" / "adr"
    available_adr_ids: set[str] = set()
    if adr_dir.exists():
        for adr_file in adr_dir.glob("[0-9][0-9][0-9]-*.md"):
            available_adr_ids.add(adr_file.name[:3])

    seen_missing_adr_refs: set[tuple[str, str]] = set()
    for doc_path in docs_files:
        relative_path = str(doc_path.relative_to(repo_root))
        content = doc_path.read_text(encoding="utf-8")
        for match in config.adr_reference_pattern.finditer(content):
            adr_id = match.group(1)
            if adr_id in available_adr_ids:
                continue
            key = (relative_path, adr_id)
            if key in seen_missing_adr_refs:
                continue
            seen_missing_adr_refs.add(key)
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="adr_reference_target_missing",
                message=(
                    f"{relative_path} references ADR-{adr_id} but docs/adr/{adr_id}-*.md "
                    "does not exist."
                ),
                path=relative_path,
            )

    data_model_path = repo_root / "docs" / "DATA_MODEL.md"
    if not data_model_path.exists():
        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="data_model_doc_missing",
                message="Missing docs/DATA_MODEL.md required for schema coverage checks.",
                path="docs/DATA_MODEL.md",
            )
        )
    else:
        data_model = data_model_path.read_text(encoding="utf-8")
        for table_name in config.data_model_required_tables:
            heading_pattern = re.compile(rf"^###\s+{re.escape(table_name)}\s*$", re.MULTILINE)
            if heading_pattern.search(data_model):
                continue
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="data_model_table_coverage_missing",
                message=(
                    f"docs/DATA_MODEL.md missing required runtime table section: '{table_name}'."
                ),
                path="docs/DATA_MODEL.md",
            )

    archived_doc_path = repo_root / config.archived_doc_path
    if not archived_doc_path.exists():
        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="archived_doc_missing",
                message=f"Missing archived document: {config.archived_doc_path}",
                path=config.archived_doc_path,
            )
        )
    else:
        archived_doc = archived_doc_path.read_text(encoding="utf-8")
        if config.archived_doc_status_line not in archived_doc:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="archived_doc_status_banner_missing",
                message=(
                    f"{config.archived_doc_path} missing archived/superseded status banner "
                    f"('{config.archived_doc_status_line}')."
                ),
                path=config.archived_doc_path,
            )

        missing_pointers = [
            pointer
            for pointer in config.archived_doc_required_pointers
            if pointer not in archived_doc
        ]
        if missing_pointers:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="archived_doc_authoritative_pointer_missing",
                message=(
                    f"{config.archived_doc_path} missing authoritative pointers: "
                    + ", ".join(missing_pointers)
                ),
                path=config.archived_doc_path,
            )

    api_main_path = repo_root / "src" / "api" / "main.py"
    api_docs_path = repo_root / "docs" / "API.md"
    env_docs_path = repo_root / "docs" / "ENVIRONMENT.md"
    api_key_manager_path = repo_root / "src" / "core" / "api_key_manager.py"

    if api_main_path.exists() and api_docs_path.exists():
        api_main = api_main_path.read_text(encoding="utf-8")
        api_docs = api_docs_path.read_text(encoding="utf-8")
        if "APIKeyAuthMiddleware" in api_main and "X-API-Key" not in api_docs:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="runtime_marker_auth_header_doc_missing",
                    message="docs/API.md missing X-API-Key mention while auth middleware is enabled.",
                    path="docs/API.md",
                )
            )
        if "APIKeyAuthMiddleware" in api_main and "API_AUTH_ENABLED" not in api_docs:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="runtime_marker_auth_toggle_doc_missing",
                    message="docs/API.md missing API_AUTH_ENABLED mention while auth middleware exists.",
                    path="docs/API.md",
                )
            )

    if api_key_manager_path.exists() and env_docs_path.exists():
        api_key_manager = api_key_manager_path.read_text(encoding="utf-8")
        env_docs = env_docs_path.read_text(encoding="utf-8")
        if (
            "API_RATE_LIMIT_PER_MINUTE" in api_key_manager
            and "API_RATE_LIMIT_PER_MINUTE" not in env_docs
        ):
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="runtime_marker_rate_limit_doc_missing",
                    message=(
                        "docs/ENVIRONMENT.md missing API_RATE_LIMIT_PER_MINUTE while "
                        "runtime rate limiting is implemented."
                    ),
                    path="docs/ENVIRONMENT.md",
                )
            )

    effective_planning_paths = (
        tuple(dict.fromkeys(planning_artifact_paths))
        if planning_artifact_paths is not None
        else changed_planning_artifact_paths(repo_root)
    )
    for relative_path in effective_planning_paths:
        warnings.extend(validate_planning_artifact(repo_root, relative_path, backlog_text))

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

    return DocsFreshnessResult(errors=tuple(errors), warnings=tuple(warnings))
