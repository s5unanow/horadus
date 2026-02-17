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
            override = active_override_map.get((rule.rule_id, relative_path))
            if override is not None:
                warnings.append(
                    DocsFreshnessIssue(
                        level="warning",
                        rule_id="docs_freshness_override_applied",
                        message=(
                            f"Override active for {rule.rule_id} in {relative_path}: "
                            f"{override.reason} (expires {override.expires_on.isoformat()})"
                        ),
                        path=relative_path,
                    )
                )
                continue
            errors.append(
                DocsFreshnessIssue(
                    level="error",
                    rule_id=rule.rule_id,
                    message=f"{rule.description} Found in {relative_path}",
                    path=relative_path,
                )
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
