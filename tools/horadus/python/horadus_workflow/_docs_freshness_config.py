from __future__ import annotations

from dataclasses import dataclass
from re import Pattern
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._docs_freshness_models import _ConflictRule, _MarkerRequirement


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
    high_risk_pre_push_review_reference_paths: tuple[str, ...]
    high_risk_pre_push_review_statements: tuple[str, ...]
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
