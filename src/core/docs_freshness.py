"""
Docs freshness and runtime-consistency checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from src.core.repo_workflow import (
    COMPLETION_GUIDANCE_REFERENCE_PATHS,
    DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS,
    FALLBACK_GUIDANCE_REFERENCE_PATHS,
    WORKFLOW_ESCAPE_HATCH_TEXT,
    WORKFLOW_POLICY_GUARDRAIL_REFERENCE_PATHS,
    WORKFLOW_REFERENCE_PATHS,
    canonical_task_workflow_command_templates,
    completion_guidance_statements,
    dependency_aware_guidance_statements,
    fallback_guidance_statements,
    workflow_policy_guardrail_statements,
)


@dataclass(frozen=True, slots=True)
class DocsFreshnessIssue:
    level: str
    rule_id: str
    message: str
    path: str | None = None


@dataclass(frozen=True, slots=True)
class DocsFreshnessResult:
    errors: tuple[DocsFreshnessIssue, ...]
    warnings: tuple[DocsFreshnessIssue, ...]

    @property
    def is_ok(self) -> bool:
        return len(self.errors) == 0


@dataclass(frozen=True, slots=True)
class _MarkerRequirement:
    path: str
    label: str


@dataclass(frozen=True, slots=True)
class _ConflictRule:
    rule_id: str
    pattern: str
    description: str


@dataclass(frozen=True, slots=True)
class _Override:
    rule_id: str
    path: str
    reason: str
    expires_on: date


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
_TASK_ID_PATTERN = re.compile(r"\bTASK-(\d{3})\b")
_CURRENT_SPRINT_ACTIVE_HEADING = "Active Tasks"
_CURRENT_SPRINT_COMPLETED_HEADING = "Completed This Sprint"
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
    "archive/2026-03-10-sprint-3-close/PROJECT_STATUS.md",
)
_PROJECT_STATUS_ARCHIVE_GUIDANCE = (
    "Do not read `archive/` during normal implementation flow unless a user "
    "explicitly asks for historical context or an archive-aware CLI flag is used."
)


def _load_overrides(override_path: Path) -> tuple[_Override, ...]:
    if not override_path.exists():
        return ()
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    raw_overrides = payload.get("overrides", [])
    if not isinstance(raw_overrides, list):
        msg = f"Override file '{override_path}' must contain an 'overrides' list"
        raise ValueError(msg)

    loaded: list[_Override] = []
    for row in raw_overrides:
        if not isinstance(row, dict):
            msg = f"Override row in '{override_path}' is not an object"
            raise ValueError(msg)
        rule_id = str(row.get("rule_id", "")).strip()
        path = str(row.get("path", "")).strip()
        reason = str(row.get("reason", "")).strip()
        expires_on_raw = str(row.get("expires_on", "")).strip()
        if not rule_id or not path or not reason or not expires_on_raw:
            msg = f"Override row in '{override_path}' is missing required fields"
            raise ValueError(msg)
        loaded.append(
            _Override(
                rule_id=rule_id,
                path=path,
                reason=reason,
                expires_on=date.fromisoformat(expires_on_raw),
            )
        )
    return tuple(loaded)


def _parse_marker_date(content: str, label: str) -> date | None:
    pattern = re.compile(rf"\*\*{re.escape(label)}\*\*:\s*(\d{{4}}-\d{{2}}-\d{{2}})")
    match = pattern.search(content)
    if match is None:
        return None
    return date.fromisoformat(match.group(1))


def _extract_h2_section(content: str, heading: str) -> str | None:
    heading_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = heading_pattern.search(content)
    if match is None:
        return None

    section_start = match.end()
    remainder = content[section_start:]
    next_heading_match = re.search(r"^##\s+.+$", remainder, re.MULTILINE)
    if next_heading_match is None:
        return remainder

    section_end = section_start + next_heading_match.start()
    return content[section_start:section_end]


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _extract_task_ids(content: str) -> set[str]:
    return {f"TASK-{match.group(1)}" for match in _TASK_ID_PATTERN.finditer(content)}


def _extract_section_task_ids(content: str, heading: str) -> set[str]:
    section = _extract_h2_section(content, heading)
    if section is None:
        return set()
    return _extract_task_ids(section)


def _extract_current_sprint_active_tasks(content: str) -> tuple[set[str], set[str]]:
    section = _extract_h2_section(content, _CURRENT_SPRINT_ACTIVE_HEADING)
    if section is None:
        return set(), set()

    active_tasks: set[str] = set()
    active_requires_human_tasks: set[str] = set()
    for line in section.splitlines():
        line_task_ids = _extract_task_ids(line)
        if not line_task_ids:
            continue
        active_tasks.update(line_task_ids)
        if "[REQUIRES_HUMAN]" in line:
            active_requires_human_tasks.update(line_task_ids)

    return active_tasks, active_requires_human_tasks


def _extract_human_blocker_metadata(content: str) -> dict[str, dict[str, str]]:
    section = _extract_h2_section(content, _HUMAN_BLOCKER_METADATA_HEADING)
    if section is None:
        return {}

    metadata: dict[str, dict[str, str]] = {}
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        task_ids = _extract_task_ids(line)
        if not task_ids:
            continue
        fields: dict[str, str] = {}
        for segment in line.split("|"):
            key, separator, value = segment.partition("=")
            if separator != "=":
                continue
            normalized_key = key.strip().lstrip("-").strip().lower()
            if not normalized_key:
                continue
            fields[normalized_key] = value.strip()
        for task_id in task_ids:
            metadata[task_id] = fields
    return metadata


def _extract_telegram_launch_scope(content: str) -> str | None:
    section = _extract_h2_section(content, _TELEGRAM_SCOPE_HEADING)
    if section is None:
        return None

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if "launch_scope" not in line:
            continue
        _, _, value = line.partition(":")
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _extract_completed_task_ids(content: str) -> set[str]:
    completed: set[str] = set()
    for line in content.splitlines():
        if not line.lstrip().startswith("-"):
            continue
        completed.update(_extract_task_ids(line))
    return completed


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


def run_docs_freshness_check(
    *,
    repo_root: Path,
    override_path: Path | None = None,
    max_age_days: int = 45,
    project_status_max_age_days: int = 7,
) -> DocsFreshnessResult:
    _ = project_status_max_age_days
    now = datetime.now(tz=UTC).date()
    checked_override_path = (
        override_path
        if override_path is not None
        else repo_root / "docs" / "DOCS_FRESHNESS_OVERRIDES.json"
    )
    overrides = _load_overrides(checked_override_path)
    active_override_map = {
        (item.rule_id, item.path): item for item in overrides if item.expires_on >= now
    }

    errors: list[DocsFreshnessIssue] = []
    warnings: list[DocsFreshnessIssue] = []

    for requirement in _REQUIRED_MARKERS:
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
    project_status = repo_root / "PROJECT_STATUS.md"
    if project_status.exists():
        docs_files.append(project_status)

    for rule in _CONFLICT_RULES:
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

    hierarchy_policy_path = repo_root / _HIERARCHY_POLICY_PATH
    if not hierarchy_policy_path.exists():
        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="hierarchy_policy_file_missing",
                message=f"Missing hierarchy policy file: {_HIERARCHY_POLICY_PATH}",
                path=_HIERARCHY_POLICY_PATH,
            )
        )
    else:
        hierarchy_policy = hierarchy_policy_path.read_text(encoding="utf-8")
        if _HIERARCHY_POLICY_HEADING not in hierarchy_policy:
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="hierarchy_policy_heading_missing",
                    message=(
                        f"AGENTS.md missing hierarchy heading: '{_HIERARCHY_POLICY_HEADING}'."
                    ),
                    path=_HIERARCHY_POLICY_PATH,
                )
            )

    for reference_path in _HIERARCHY_POLICY_REFERENCE_FILES:
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
        if "AGENTS.md" in content and _HIERARCHY_POLICY_REFERENCE_TEXT in content:
            continue

        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="hierarchy_policy_reference_missing",
                message=(
                    f"{reference_path} must reference AGENTS hierarchy policy "
                    f"('{_HIERARCHY_POLICY_REFERENCE_TEXT}')."
                ),
                path=reference_path,
            )
        )

    workflow_command_templates = canonical_task_workflow_command_templates()
    for reference_path in WORKFLOW_REFERENCE_PATHS:
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
        for command_template in workflow_command_templates:
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
        if _normalize_whitespace(WORKFLOW_ESCAPE_HATCH_TEXT) not in _normalize_whitespace(content):
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

    guidance_statements = completion_guidance_statements()
    for reference_path in COMPLETION_GUIDANCE_REFERENCE_PATHS:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="completion_guidance_reference_file_missing",
                    message=f"Missing completion guidance file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
        for statement in guidance_statements:
            if _normalize_whitespace(statement) in normalized_content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="completion_guidance_statement_missing",
                    message=(
                        f"{reference_path} must include canonical completion guidance: {statement}"
                    ),
                    path=reference_path,
                )
            )

    dependency_statements = dependency_aware_guidance_statements()
    for reference_path in DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="dependency_guidance_reference_file_missing",
                    message=f"Missing dependency-aware workflow guidance file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
        for statement in dependency_statements:
            if _normalize_whitespace(statement) in normalized_content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="dependency_guidance_statement_missing",
                    message=(
                        f"{reference_path} must include canonical dependency-aware "
                        f"workflow guidance: {statement}"
                    ),
                    path=reference_path,
                )
            )

    fallback_statements = fallback_guidance_statements()
    for reference_path in FALLBACK_GUIDANCE_REFERENCE_PATHS:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="fallback_guidance_reference_file_missing",
                    message=f"Missing fallback workflow guidance file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
        for statement in fallback_statements:
            if _normalize_whitespace(statement) in normalized_content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="fallback_guidance_statement_missing",
                    message=(
                        f"{reference_path} must include canonical fallback workflow "
                        f"guidance: {statement}"
                    ),
                    path=reference_path,
                )
            )

    workflow_guardrail_statements = workflow_policy_guardrail_statements()
    for reference_path in WORKFLOW_POLICY_GUARDRAIL_REFERENCE_PATHS:
        file_path = repo_root / reference_path
        if not file_path.exists():
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_policy_guardrail_reference_file_missing",
                    message=f"Missing workflow policy guardrail file: {reference_path}",
                    path=reference_path,
                )
            )
            continue

        normalized_content = _normalize_whitespace(file_path.read_text(encoding="utf-8"))
        for statement in workflow_guardrail_statements:
            if _normalize_whitespace(statement) in normalized_content:
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id="workflow_policy_guardrail_statement_missing",
                    message=(
                        f"{reference_path} must include canonical workflow/policy "
                        f"guardrail guidance: {statement}"
                    ),
                    path=reference_path,
                )
            )

    current_sprint_path = repo_root / "tasks" / "CURRENT_SPRINT.md"
    project_status_path = repo_root / "PROJECT_STATUS.md"
    if project_status_path.exists():
        project_status_text = project_status_path.read_text(encoding="utf-8")
        if _PROJECT_STATUS_STUB_STATUS_LINE not in project_status_text:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_stub_status_missing",
                message=(
                    "PROJECT_STATUS.md must be the non-authoritative archive-pointer stub "
                    f"('{_PROJECT_STATUS_STUB_STATUS_LINE}')."
                ),
                path="PROJECT_STATUS.md",
            )
        missing_project_status_pointers = [
            pointer
            for pointer in _PROJECT_STATUS_STUB_REQUIRED_POINTERS
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
        if _normalize_whitespace(_PROJECT_STATUS_ARCHIVE_GUIDANCE) not in _normalize_whitespace(
            project_status_text
        ):
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="project_status_archive_guidance_missing",
                message="PROJECT_STATUS.md must say that archive access is opt-in only.",
                path="PROJECT_STATUS.md",
            )

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
                            f"'{_HUMAN_BLOCKER_METADATA_HEADING}' section"
                        ),
                        path="tasks/CURRENT_SPRINT.md",
                    )
                    continue

                missing_fields = [
                    field
                    for field in _REQUIRED_HUMAN_BLOCKER_METADATA_FIELDS
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

            if "TASK-080" in active_sprint_tasks:
                telegram_scope = _extract_telegram_launch_scope(current_sprint)
                if telegram_scope is None:
                    _record_issue(
                        errors=errors,
                        warnings=warnings,
                        active_override_map=active_override_map,
                        rule_id="telegram_launch_scope_missing",
                        message=(
                            "TASK-080 is active: CURRENT_SPRINT must define "
                            f"'{_TELEGRAM_SCOPE_HEADING}' with a launch_scope field"
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
        for match in _ADR_REFERENCE_PATTERN.finditer(content):
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
        for table_name in _DATA_MODEL_REQUIRED_TABLES:
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

    archived_doc_path = repo_root / _ARCHIVED_DOC_PATH
    if not archived_doc_path.exists():
        errors.append(
            DocsFreshnessIssue(
                level="error",
                rule_id="archived_doc_missing",
                message=f"Missing archived document: {_ARCHIVED_DOC_PATH}",
                path=_ARCHIVED_DOC_PATH,
            )
        )
    else:
        archived_doc = archived_doc_path.read_text(encoding="utf-8")
        if _ARCHIVED_DOC_STATUS_LINE not in archived_doc:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="archived_doc_status_banner_missing",
                message=(
                    f"{_ARCHIVED_DOC_PATH} missing archived/superseded status banner "
                    f"('{_ARCHIVED_DOC_STATUS_LINE}')."
                ),
                path=_ARCHIVED_DOC_PATH,
            )

        missing_pointers = [
            pointer for pointer in _ARCHIVED_DOC_REQUIRED_POINTERS if pointer not in archived_doc
        ]
        if missing_pointers:
            _record_issue(
                errors=errors,
                warnings=warnings,
                active_override_map=active_override_map,
                rule_id="archived_doc_authoritative_pointer_missing",
                message=(
                    f"{_ARCHIVED_DOC_PATH} missing authoritative pointers: "
                    + ", ".join(missing_pointers)
                ),
                path=_ARCHIVED_DOC_PATH,
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

    return DocsFreshnessResult(errors=tuple(errors), warnings=tuple(warnings))
