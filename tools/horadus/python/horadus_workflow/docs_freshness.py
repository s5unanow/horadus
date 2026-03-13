"""
Docs freshness and runtime-consistency checks.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from pathlib import Path

from tools.horadus.python.horadus_workflow._docs_freshness_checks import (
    DocsFreshnessCheckConfig,
    run_docs_freshness_check_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_checks import (
    _record_issue as _record_issue_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_models import (
    DocsFreshnessIssue,
    DocsFreshnessResult,
    _ConflictRule,
    _MarkerRequirement,
)
from tools.horadus.python.horadus_workflow._docs_freshness_models import (
    _Override as _Override_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_completed_task_ids as _extract_completed_task_ids_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_current_sprint_active_tasks as _extract_current_sprint_active_tasks_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_h2_section as _extract_h2_section_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_human_blocker_metadata as _extract_human_blocker_metadata_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_section_task_ids as _extract_section_task_ids_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_task_ids as _extract_task_ids_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _extract_telegram_launch_scope as _extract_telegram_launch_scope_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _load_overrides as _load_overrides_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _normalize_whitespace as _normalize_whitespace_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_parsing import (
    _parse_marker_date as _parse_marker_date_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _PLANNING_CHANGED_DEFAULT_BASE_REF,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _changed_planning_artifact_paths as _changed_planning_artifact_paths_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _exec_plan_required_from_backlog as _exec_plan_required_from_backlog_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _extract_task_block as _extract_task_block_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _planning_marker_value as _planning_marker_value_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _planning_required_from_value as _planning_required_from_value_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _planning_state_for_task as _planning_state_for_task_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _task_exec_plan_paths as _task_exec_plan_paths_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _task_id_from_planning_artifact_path as _task_id_from_planning_artifact_path_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _task_spec_paths as _task_spec_paths_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _validate_planning_artifact as _validate_planning_artifact_impl,
)
from tools.horadus.python.horadus_workflow._docs_freshness_rendering import (
    render_docs_freshness_issues as render_docs_freshness_issues_impl,
)
from tools.horadus.python.horadus_workflow.repo_workflow import (
    CANONICAL_SAFE_START_COMMAND,
    CANONICAL_SAFE_START_REFERENCE_PATHS,
    COMPLETION_GUIDANCE_REFERENCE_PATHS,
    DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS,
    FALLBACK_GUIDANCE_REFERENCE_PATHS,
    STALE_LOWER_LEVEL_TASK_START_COMMAND,
    STALE_TASK_START_FORBIDDEN_REFERENCE_PATHS,
    WORKFLOW_ESCAPE_HATCH_TEXT,
    WORKFLOW_POLICY_GUARDRAIL_REFERENCE_PATHS,
    WORKFLOW_REFERENCE_PATHS,
    canonical_task_workflow_command_templates,
    completion_guidance_statements,
    dependency_aware_guidance_statements,
    fallback_guidance_statements,
    workflow_policy_guardrail_statements,
)

_REQUIRED_MARKERS: tuple[_MarkerRequirement, ...] = (
    _MarkerRequirement(path="docs/ARCHITECTURE.md", label="Last Verified"),
    _MarkerRequirement(path="docs/DEPLOYMENT.md", label="Last Verified"),
    _MarkerRequirement(path="docs/ENVIRONMENT.md", label="Last Verified"),
    _MarkerRequirement(path="docs/RELEASING.md", label="Last Verified"),
)

_CONFLICT_RULES: tuple[_ConflictRule, ...] = (
    _ConflictRule(
        rule_id="stale_auth_unenforced_claim",
        pattern="All API endpoints have no authentication checks.",
        description="Stale auth-risk statement conflicts with implemented middleware/auth endpoints.",
    ),
    _ConflictRule(
        rule_id="stale_api_key_not_enforced_claim",
        pattern="API_KEY setting in config (`src/core/config.py`) is defined but never enforced.",
        description="Stale API key enforcement statement conflicts with implemented auth middleware.",
    ),
)

_HIERARCHY_POLICY_PATH = "AGENTS.md"
_HIERARCHY_POLICY_HEADING = "## Canonical Source-of-Truth Hierarchy"
_HIERARCHY_POLICY_REFERENCE_FILES: tuple[str, ...] = (
    "PROJECT_STATUS.md",
    "tasks/CURRENT_SPRINT.md",
)
_HIERARCHY_POLICY_REFERENCE_TEXT = "Canonical Source-of-Truth Hierarchy"
_ADR_REFERENCE_PATTERN = re.compile(r"\bADR-(\d{3})\b")
_DATA_MODEL_REQUIRED_TABLES: tuple[str, ...] = (
    "reports",
    "api_usage",
    "trend_outcomes",
    "human_feedback",
)
_ARCHIVED_DOC_PATH = "docs/POTENTIAL_ISSUES.md"
_ARCHIVED_DOC_STATUS_LINE = "**Status**: Archived historical snapshot (superseded)"
_ARCHIVED_DOC_REQUIRED_POINTERS: tuple[str, ...] = (
    "tasks/CURRENT_SPRINT.md",
    "tasks/BACKLOG.md",
    "tasks/COMPLETED.md",
    "PROJECT_STATUS.md",
    "archive/",
)
_HUMAN_BLOCKER_METADATA_HEADING = "Human Blocker Metadata"
_TELEGRAM_SCOPE_HEADING = "Telegram Launch Scope"
_REQUIRED_HUMAN_BLOCKER_METADATA_FIELDS: tuple[str, ...] = (
    "owner",
    "last_touched",
    "next_action",
    "escalate_after_days",
)
_PROJECT_STATUS_STUB_STATUS_LINE = "**Status**: Archived pointer stub (non-authoritative)"
_PROJECT_STATUS_STUB_REQUIRED_POINTERS: tuple[str, ...] = (
    "tasks/CURRENT_SPRINT.md",
    "tasks/BACKLOG.md",
    "tasks/COMPLETED.md",
)
_PROJECT_STATUS_ARCHIVE_POINTER_PATTERN = re.compile(
    r"archive/\d{4}-\d{2}-\d{2}-[a-z0-9-]+/PROJECT_STATUS\.md"
)
_PROJECT_STATUS_ARCHIVE_GUIDANCE = (
    "Do not read `archive/` during normal implementation flow unless a user "
    "explicitly asks for historical context or an archive-aware CLI flag is used."
)
_THIN_WORKFLOW_SURFACES: tuple[str, ...] = (
    "README.md",
    "docs/AGENT_RUNBOOK.md",
    "ops/skills/horadus-cli/SKILL.md",
    "ops/skills/horadus-cli/references/commands.md",
)
_THIN_SURFACE_FORBIDDEN_POLICY_MARKERS: tuple[str, ...] = (
    "Do not claim a task is complete, done, or finished until",
    "The default review-gate timeout for `horadus tasks finish` is 600",
    "Do not proactively suggest changing the `horadus tasks finish` review timeout",
    "Apply these guardrails only when changing shared workflow helpers,",
)
_PLANNING_SPEC_SECTION_HEADING = "## Phase -1 / Pre-Implementation Gates"
_PLANNING_EXEC_PLAN_SECTION_HEADING = "## Gate Outcomes / Waivers"
_PLANNING_CORE_GATE_LABELS: tuple[str, ...] = (
    "`Simplicity Gate`",
    "`Anti-Abstraction Gate`",
    "`Integration-First Gate`",
)
_PLANNING_CONDITIONAL_GATE_LABELS: tuple[str, ...] = (
    "`Determinism Gate`",
    "`LLM Budget/Safety Gate`",
    "`Observability Gate`",
)


def _thin_surface_forbidden_policy_statements() -> tuple[str, ...]:
    canonical_statements = (
        *completion_guidance_statements(),
        *workflow_policy_guardrail_statements(),
    )
    selected: list[str] = []
    for marker in _THIN_SURFACE_FORBIDDEN_POLICY_MARKERS:
        statement = next((value for value in canonical_statements if marker in value), None)
        if statement is None:
            raise RuntimeError(
                "thin-surface forbidden policy marker no longer matches a canonical statement: "
                f"{marker}"
            )
        selected.append(statement)
    return tuple(selected)


_THIN_SURFACE_FORBIDDEN_POLICY_STATEMENTS: tuple[str, ...] = (
    _thin_surface_forbidden_policy_statements()
)

_load_overrides = _load_overrides_impl
_parse_marker_date = _parse_marker_date_impl
_extract_h2_section = _extract_h2_section_impl
_normalize_whitespace = _normalize_whitespace_impl
_extract_task_ids = _extract_task_ids_impl
_extract_section_task_ids = _extract_section_task_ids_impl
_extract_current_sprint_active_tasks = _extract_current_sprint_active_tasks_impl
_extract_human_blocker_metadata = _extract_human_blocker_metadata_impl
_extract_telegram_launch_scope = _extract_telegram_launch_scope_impl
_extract_completed_task_ids = _extract_completed_task_ids_impl
_planning_marker_value = _planning_marker_value_impl
_planning_required_from_value = _planning_required_from_value_impl
_exec_plan_required_from_backlog = _exec_plan_required_from_backlog_impl
_task_id_from_planning_artifact_path = _task_id_from_planning_artifact_path_impl
_extract_task_block = _extract_task_block_impl
_task_spec_paths = _task_spec_paths_impl
_task_exec_plan_paths = _task_exec_plan_paths_impl
_planning_state_for_task = _planning_state_for_task_impl
_record_issue = _record_issue_impl
_Override = _Override_impl
render_docs_freshness_issues = render_docs_freshness_issues_impl


def _changed_planning_artifact_paths(repo_root: Path) -> tuple[str, ...]:
    return _changed_planning_artifact_paths_impl(
        repo_root,
        base_ref=_PLANNING_CHANGED_DEFAULT_BASE_REF,
        git_which=shutil.which,
        run=subprocess.run,
    )


def _validate_planning_artifact(
    *,
    repo_root: Path,
    relative_path: str,
    backlog_text: str,
) -> tuple[DocsFreshnessIssue, ...]:
    return _validate_planning_artifact_impl(
        repo_root=repo_root,
        relative_path=relative_path,
        backlog_text=backlog_text,
        planning_spec_section_heading=_PLANNING_SPEC_SECTION_HEADING,
        planning_exec_plan_section_heading=_PLANNING_EXEC_PLAN_SECTION_HEADING,
        planning_core_gate_labels=_PLANNING_CORE_GATE_LABELS,
        planning_conditional_gate_labels=_PLANNING_CONDITIONAL_GATE_LABELS,
    )


def run_docs_freshness_check(
    *,
    repo_root: Path,
    override_path: Path | None = None,
    max_age_days: int = 45,
    project_status_max_age_days: int = 7,
    planning_artifact_paths: tuple[str, ...] | None = None,
) -> DocsFreshnessResult:
    _ = project_status_max_age_days
    checked_override_path = (
        override_path
        if override_path is not None
        else repo_root / "docs" / "DOCS_FRESHNESS_OVERRIDES.json"
    )
    return run_docs_freshness_check_impl(
        repo_root=repo_root,
        override_path=checked_override_path,
        max_age_days=max_age_days,
        planning_artifact_paths=planning_artifact_paths,
        config=DocsFreshnessCheckConfig(
            required_markers=_REQUIRED_MARKERS,
            conflict_rules=_CONFLICT_RULES,
            hierarchy_policy_path=_HIERARCHY_POLICY_PATH,
            hierarchy_policy_heading=_HIERARCHY_POLICY_HEADING,
            hierarchy_policy_reference_files=_HIERARCHY_POLICY_REFERENCE_FILES,
            hierarchy_policy_reference_text=_HIERARCHY_POLICY_REFERENCE_TEXT,
            workflow_reference_paths=WORKFLOW_REFERENCE_PATHS,
            workflow_command_templates=tuple(canonical_task_workflow_command_templates()),
            workflow_escape_hatch_text=WORKFLOW_ESCAPE_HATCH_TEXT,
            canonical_safe_start_reference_paths=CANONICAL_SAFE_START_REFERENCE_PATHS,
            canonical_safe_start_command=CANONICAL_SAFE_START_COMMAND,
            stale_task_start_forbidden_reference_paths=STALE_TASK_START_FORBIDDEN_REFERENCE_PATHS,
            stale_lower_level_task_start_command=STALE_LOWER_LEVEL_TASK_START_COMMAND,
            completion_guidance_reference_paths=COMPLETION_GUIDANCE_REFERENCE_PATHS,
            completion_guidance_statements=tuple(completion_guidance_statements()),
            dependency_aware_guidance_reference_paths=DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS,
            dependency_aware_guidance_statements=tuple(dependency_aware_guidance_statements()),
            fallback_guidance_reference_paths=FALLBACK_GUIDANCE_REFERENCE_PATHS,
            fallback_guidance_statements=tuple(fallback_guidance_statements()),
            workflow_policy_guardrail_reference_paths=WORKFLOW_POLICY_GUARDRAIL_REFERENCE_PATHS,
            workflow_policy_guardrail_statements=tuple(workflow_policy_guardrail_statements()),
            adr_reference_pattern=_ADR_REFERENCE_PATTERN,
            data_model_required_tables=_DATA_MODEL_REQUIRED_TABLES,
            archived_doc_path=_ARCHIVED_DOC_PATH,
            archived_doc_status_line=_ARCHIVED_DOC_STATUS_LINE,
            archived_doc_required_pointers=_ARCHIVED_DOC_REQUIRED_POINTERS,
            required_human_blocker_metadata_fields=_REQUIRED_HUMAN_BLOCKER_METADATA_FIELDS,
            current_sprint_human_blocker_metadata_heading=_HUMAN_BLOCKER_METADATA_HEADING,
            current_sprint_telegram_scope_heading=_TELEGRAM_SCOPE_HEADING,
            project_status_stub_status_line=_PROJECT_STATUS_STUB_STATUS_LINE,
            project_status_stub_required_pointers=_PROJECT_STATUS_STUB_REQUIRED_POINTERS,
            project_status_archive_pointer_pattern=_PROJECT_STATUS_ARCHIVE_POINTER_PATTERN,
            project_status_archive_guidance=_PROJECT_STATUS_ARCHIVE_GUIDANCE,
            thin_workflow_surfaces=_THIN_WORKFLOW_SURFACES,
            thin_surface_forbidden_policy_statements=_THIN_SURFACE_FORBIDDEN_POLICY_STATEMENTS,
        ),
        changed_planning_artifact_paths=_changed_planning_artifact_paths,
        validate_planning_artifact=lambda root, relative_path, backlog_text: (
            _validate_planning_artifact(
                repo_root=root,
                relative_path=relative_path,
                backlog_text=backlog_text,
            )
        ),
    )
