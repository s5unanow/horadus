from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ._docs_freshness_content_rules import (
    check_adr_references,
    check_archived_doc,
    check_conflict_rules,
    check_data_model_coverage,
    check_required_markers,
    check_runtime_docs_sync,
)
from ._docs_freshness_current_sprint import check_current_sprint
from ._docs_freshness_models import DocsFreshnessIssue, DocsFreshnessResult
from ._docs_freshness_parsing import _load_overrides
from ._docs_freshness_project_status import check_project_status
from ._docs_freshness_workflow_rules import (
    check_guidance_references,
    check_hierarchy_policy,
    check_safe_start_references,
    check_thin_workflow_surfaces,
    check_workflow_references,
)

if TYPE_CHECKING:
    from ._docs_freshness_config import DocsFreshnessCheckConfig


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

    check_required_markers(
        repo_root=repo_root,
        now=now,
        max_age_days=max_age_days,
        config=config,
        errors=errors,
    )

    docs_files = tuple((repo_root / "docs").rglob("*.md"))
    project_status_path = repo_root / "PROJECT_STATUS.md"
    if project_status_path.exists():
        docs_files = (*docs_files, project_status_path)

    backlog_text = ""
    backlog_file = repo_root / "tasks" / "BACKLOG.md"
    if backlog_file.exists():
        backlog_text = backlog_file.read_text(encoding="utf-8")

    check_conflict_rules(
        repo_root=repo_root,
        docs_files=docs_files,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_hierarchy_policy(repo_root=repo_root, config=config, errors=errors)
    check_workflow_references(repo_root=repo_root, config=config, errors=errors)
    check_safe_start_references(repo_root=repo_root, config=config, errors=errors)
    check_guidance_references(repo_root=repo_root, config=config, errors=errors)
    check_project_status(
        repo_root=repo_root,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_current_sprint(
        repo_root=repo_root,
        now=now,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_adr_references(
        repo_root=repo_root,
        docs_files=docs_files,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_data_model_coverage(
        repo_root=repo_root,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_archived_doc(
        repo_root=repo_root,
        config=config,
        active_override_map=active_override_map,
        errors=errors,
        warnings=warnings,
    )
    check_runtime_docs_sync(repo_root=repo_root, errors=errors)

    effective_planning_paths = (
        tuple(dict.fromkeys(planning_artifact_paths))
        if planning_artifact_paths is not None
        else changed_planning_artifact_paths(repo_root)
    )
    for relative_path in effective_planning_paths:
        warnings.extend(validate_planning_artifact(repo_root, relative_path, backlog_text))

    check_thin_workflow_surfaces(repo_root=repo_root, config=config, errors=errors)

    return DocsFreshnessResult(errors=tuple(errors), warnings=tuple(warnings))
