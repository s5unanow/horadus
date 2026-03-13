from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._docs_freshness_issue_helpers import _record_issue
from ._docs_freshness_parsing import _normalize_whitespace

if TYPE_CHECKING:
    from ._docs_freshness_config import DocsFreshnessCheckConfig
    from ._docs_freshness_models import DocsFreshnessIssue, _Override


def check_project_status(
    *,
    repo_root: Path,
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
    project_status_path = repo_root / "PROJECT_STATUS.md"
    if not project_status_path.exists():
        return

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

    if _normalize_whitespace(config.project_status_archive_guidance) not in _normalize_whitespace(
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
