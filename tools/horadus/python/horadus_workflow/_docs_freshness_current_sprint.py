from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from ._docs_freshness_issue_helpers import _record_issue
from ._docs_freshness_parsing import (
    _extract_current_sprint_active_tasks,
    _extract_human_blocker_metadata,
    _extract_telegram_launch_scope,
)

if TYPE_CHECKING:
    from ._docs_freshness_config import DocsFreshnessCheckConfig
    from ._docs_freshness_models import DocsFreshnessIssue, _Override


def check_current_sprint(
    *,
    repo_root: Path,
    now: date,
    config: DocsFreshnessCheckConfig,
    active_override_map: dict[tuple[str, str], _Override],
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
) -> None:
    current_sprint_path = repo_root / "tasks" / "CURRENT_SPRINT.md"
    if not current_sprint_path.exists():
        return

    current_sprint = current_sprint_path.read_text(encoding="utf-8")
    active_sprint_tasks, active_requires_human_tasks = _extract_current_sprint_active_tasks(
        current_sprint
    )

    if not active_requires_human_tasks:
        return

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
                message=f"{task_id} metadata missing required fields: " + ", ".join(missing_fields),
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
                message=f"{task_id} metadata field 'next_action' must be on/after 'last_touched'",
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

    if "TASK-080" in active_sprint_tasks and _extract_telegram_launch_scope(current_sprint) is None:
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
