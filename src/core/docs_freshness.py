"""
Docs freshness and runtime-consistency checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path


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
    _MarkerRequirement(path="PROJECT_STATUS.md", label="Last Updated"),
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
    "PROJECT_STATUS.md",
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
) -> DocsFreshnessResult:
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
