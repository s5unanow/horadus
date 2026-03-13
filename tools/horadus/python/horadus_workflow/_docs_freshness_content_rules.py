from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from ._docs_freshness_issue_helpers import _record_issue
from ._docs_freshness_models import DocsFreshnessIssue, _Override
from ._docs_freshness_parsing import _parse_marker_date

if TYPE_CHECKING:
    from ._docs_freshness_config import DocsFreshnessCheckConfig


def check_required_markers(
    *,
    repo_root: Path,
    now: date,
    max_age_days: int,
    config: DocsFreshnessCheckConfig,
    errors: list[DocsFreshnessIssue],
) -> None:
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


def check_conflict_rules(
    *,
    repo_root: Path,
    docs_files: tuple[Path, ...],
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
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


def check_adr_references(
    *,
    repo_root: Path,
    docs_files: tuple[Path, ...],
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
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


def check_data_model_coverage(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
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
        return

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
            message=f"docs/DATA_MODEL.md missing required runtime table section: '{table_name}'.",
            path="docs/DATA_MODEL.md",
        )


def check_archived_doc(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
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
        return

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
        pointer for pointer in config.archived_doc_required_pointers if pointer not in archived_doc
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


def check_runtime_docs_sync(
    *,
    repo_root: Path,
    errors: list[DocsFreshnessIssue],
) -> None:
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
