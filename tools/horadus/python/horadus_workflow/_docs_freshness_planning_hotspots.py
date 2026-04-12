from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from pathlib import Path

from ._docs_freshness_models import DocsFreshnessIssue
from ._docs_freshness_parsing import _extract_task_ids
from .code_shape import load_code_shape_policy

_FILES_LINE_PATTERN = re.compile(r"^\*\*Files\*\*:\s*(?P<value>.+)$", re.MULTILINE)
_BACKTICKED_PATH_PATTERN = re.compile(r"`([^`]+)`")
_HOTSPOT_OUTCOME_LINE_PATTERN = re.compile(
    r"^(?:-\s+)?(?:\*\*)?Hotspot Outcome(?:\*\*)?:\s*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_HOTSPOT_OUTCOME_VALUE_PATTERN = re.compile(
    r"^(?:`)?(?P<outcome>reduce|keep-flat-with-rationale|follow-up-task-created)(?:`)?"
    r"(?:\s*[—-]\s*(?P<detail>.+))?$",
    re.IGNORECASE,
)
_TASK_ID_PATTERN = re.compile(r"\bTASK-\d{3}\b")
_CODE_SHAPE_POLICY_RELATIVE_PATH = Path("config/quality/code_shape.toml")


def task_file_paths_from_block(task_block: str) -> tuple[str, ...]:
    paths: list[str] = []
    for match in _FILES_LINE_PATTERN.finditer(task_block):
        raw_value = match.group("value").strip()
        if not raw_value:
            continue
        backticked_paths = [item.strip() for item in _BACKTICKED_PATH_PATTERN.findall(raw_value)]
        if backticked_paths:
            paths.extend(backticked_paths)
            raw_value = _BACKTICKED_PATH_PATTERN.sub("", raw_value)
        paths.extend(item.strip() for item in raw_value.split(",") if item.strip())
    return tuple(dict.fromkeys(paths))


def matches_declared_task_path(declared_path: str, candidate_path: str) -> bool:
    normalized = declared_path.strip().strip("`").rstrip("/")
    if not normalized:
        return False
    return candidate_path == normalized or candidate_path.startswith(f"{normalized}/")


def matching_allowlisted_hotspot_paths(
    repo_root: Path, declared_paths: Sequence[str]
) -> tuple[str, ...]:
    normalized_paths = [path.strip() for path in declared_paths if path.strip()]
    if not normalized_paths:
        return ()
    return tuple(
        hotspot_path
        for hotspot_path in _allowlisted_production_hotspot_paths(repo_root)
        if any(
            matches_declared_task_path(declared_path, hotspot_path)
            for declared_path in normalized_paths
        )
    )


def task_hotspot_paths(
    repo_root: Path,
    *,
    task_id: str,
    backlog_text: str,
    extract_task_block: Callable[[str, str], str | None],
) -> tuple[str, ...]:
    backlog_block = extract_task_block(backlog_text, task_id) or ""
    return matching_allowlisted_hotspot_paths(repo_root, task_file_paths_from_block(backlog_block))


def hotspot_outcome_marker_value(content: str) -> str | None:
    values = hotspot_outcome_marker_values(content)
    if not values:
        return None
    return values[0]


def hotspot_outcome_marker_values(content: str) -> tuple[str, ...]:
    return tuple(
        value
        for match in _HOTSPOT_OUTCOME_LINE_PATTERN.finditer(content)
        if (value := match.group("value").strip())
    )


def parse_hotspot_outcome_marker(value: str | None) -> tuple[str, str | None] | None:
    if value is None:
        return None
    match = _HOTSPOT_OUTCOME_VALUE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    detail = match.group("detail")
    return match.group("outcome").lower(), detail.strip() if detail is not None else None


def template_planning_issues(
    *,
    relative_path: str,
    content: str,
    planning_spec_section_heading: str,
    planning_exec_plan_section_heading: str,
) -> tuple[DocsFreshnessIssue, ...]:
    issues: list[DocsFreshnessIssue] = []
    if relative_path == "tasks/specs/TEMPLATE.md":
        if "**Planning Gates**:" not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_marker_missing",
                    message="Spec template should define the canonical Planning Gates marker.",
                    path=relative_path,
                )
            )
        if planning_spec_section_heading not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_spec_section_missing",
                    message="Spec template should include the Phase -1 / Pre-Implementation Gates section.",
                    path=relative_path,
                )
            )
        if "Hotspot Outcome:" not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_hotspot_template_missing",
                    message="Spec template should include the canonical Hotspot Outcome marker.",
                    path=relative_path,
                )
            )
        return tuple(issues)
    if relative_path == "tasks/exec_plans/TEMPLATE.md":
        if "Planning Gates:" not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_marker_missing",
                    message="Exec-plan template should mirror the Planning Gates marker scheme.",
                    path=relative_path,
                )
            )
        if planning_exec_plan_section_heading not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_gate_outcomes_missing",
                    message="Exec-plan template should include Gate Outcomes / Waivers.",
                    path=relative_path,
                )
            )
        if "Hotspot Outcome:" not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_hotspot_template_missing",
                    message="Exec-plan template should include the canonical Hotspot Outcome marker.",
                    path=relative_path,
                )
            )
        return tuple(issues)
    return ()


def backlog_planning_issues(
    *,
    repo_root: Path,
    backlog_text: str,
    planning_state_for_task: Callable[..., dict[str, object]],
    relative_path: str,
) -> tuple[DocsFreshnessIssue, ...]:
    if relative_path != "tasks/BACKLOG.md":
        return ()
    issues: list[DocsFreshnessIssue] = []
    for backlog_task_id in sorted(_extract_task_ids(backlog_text)):
        state = planning_state_for_task(
            repo_root, task_id=backlog_task_id, backlog_text=backlog_text
        )
        if state["state"] != "applicable_backlog_only_missing_artifact":
            continue
        raw_hotspot_paths = state.get("hotspot_paths")
        hotspot_paths: tuple[str, ...] = (
            tuple(str(item) for item in raw_hotspot_paths)
            if isinstance(raw_hotspot_paths, tuple | list)
            else ()
        )
        hotspot_note = ""
        if hotspot_paths:
            hotspot_note = (
                " The declared task files include allowlisted production hotspots: "
                f"{', '.join(hotspot_paths)}."
            )
        issues.append(
            _warning_issue(
                rule_id="planning_artifact_missing",
                message=(
                    f"{backlog_task_id} requires planning gates, but the backlog entry is still the only "
                    f"planning artifact. Add a task spec or exec plan before implementation.{hotspot_note}"
                ),
                path=relative_path,
            )
        )
    return tuple(issues)


def planning_spec_issues(
    *,
    relative_path: str,
    content: str,
    planning_spec_section_heading: str,
    planning_core_gate_labels: tuple[str, ...],
    planning_conditional_gate_labels: tuple[str, ...],
    planning_marker_value: Callable[[str], str | None],
) -> tuple[DocsFreshnessIssue, ...]:
    issues: list[DocsFreshnessIssue] = []
    if planning_marker_value(content) is None:
        issues.append(
            _warning_issue(
                rule_id="planning_marker_missing",
                message=f"{relative_path} should include an explicit Planning Gates marker.",
                path=relative_path,
            )
        )
    if planning_spec_section_heading not in content:
        issues.append(
            _warning_issue(
                rule_id="planning_spec_section_missing",
                message=f"{relative_path} should include {planning_spec_section_heading}.",
                path=relative_path,
            )
        )
        return tuple(issues)
    for gate_label in planning_core_gate_labels:
        if gate_label not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_core_gate_missing",
                    message=f"{relative_path} is missing required core gate {gate_label}.",
                    path=relative_path,
                )
            )
    for gate_label in planning_conditional_gate_labels:
        if gate_label not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_conditional_gate_missing",
                    message=(
                        f"{relative_path} should include {gate_label} with a triggered answer or "
                        "a short 'Not applicable' reason."
                    ),
                    path=relative_path,
                )
            )
    if "Validation target:" not in content or "Exercises:" not in content:
        issues.append(
            _warning_issue(
                rule_id="planning_integration_proof_incomplete",
                message=(
                    f"{relative_path} should name an Integration-First validation target and the "
                    "contract/dependency/invariant it exercises."
                ),
                path=relative_path,
            )
        )
    return tuple(issues)


def planning_exec_plan_issues(
    *,
    relative_path: str,
    content: str,
    planning_exec_plan_section_heading: str,
) -> tuple[DocsFreshnessIssue, ...]:
    issues: list[DocsFreshnessIssue] = []
    if planning_exec_plan_section_heading not in content:
        issues.append(
            _warning_issue(
                rule_id="planning_gate_outcomes_missing",
                message=f"{relative_path} should include {planning_exec_plan_section_heading}.",
                path=relative_path,
            )
        )
    for required_phrase in (
        "Accepted design / smallest safe shape:",
        "Rejected simpler alternative:",
        "First integration proof:",
        "Waivers:",
    ):
        if required_phrase not in content:
            issues.append(
                _warning_issue(
                    rule_id="planning_gate_outcome_field_missing",
                    message=f"{relative_path} should include '{required_phrase}'.",
                    path=relative_path,
                )
            )
    return tuple(issues)


def hotspot_outcome_issues(
    *,
    relative_path: str,
    content: str,
    planning_state: dict[str, object],
    known_task_ids: Collection[str] | None = None,
) -> tuple[DocsFreshnessIssue, ...]:
    raw_hotspot_paths = planning_state.get("hotspot_paths")
    hotspot_paths: tuple[str, ...] = (
        tuple(str(item) for item in raw_hotspot_paths)
        if isinstance(raw_hotspot_paths, tuple | list)
        else ()
    )
    if not hotspot_paths:
        return ()
    authoritative_artifact = planning_state.get("authoritative_artifact")
    if authoritative_artifact is not None and relative_path != authoritative_artifact:
        return ()
    marker_values = hotspot_outcome_marker_values(content)
    canonical_marker = (
        "`- Hotspot Outcome: reduce — ...` or "
        "`- Hotspot Outcome: keep-flat-with-rationale — ...` or "
        "`- Hotspot Outcome: follow-up-task-created — TASK-XXX ...`"
    )
    if not marker_values:
        return (
            _warning_issue(
                rule_id="planning_hotspot_outcome_missing",
                message=(
                    f"{relative_path} must record a Hotspot Outcome for allowlisted production "
                    f"hotspots: {', '.join(hotspot_paths)}. Use {canonical_marker}."
                ),
                path=relative_path,
            ),
        )
    if len(marker_values) > 1:
        return (
            _warning_issue(
                rule_id="planning_hotspot_outcome_duplicate",
                message=(
                    f"{relative_path} must record exactly one Hotspot Outcome for "
                    f"{', '.join(hotspot_paths)}. Use {canonical_marker} once."
                ),
                path=relative_path,
            ),
        )
    parsed_marker = parse_hotspot_outcome_marker(marker_values[0])
    if parsed_marker is None:
        return (
            _warning_issue(
                rule_id="planning_hotspot_outcome_invalid",
                message=(
                    f"{relative_path} has an invalid Hotspot Outcome marker for "
                    f"{', '.join(hotspot_paths)}. Use {canonical_marker}."
                ),
                path=relative_path,
            ),
        )
    outcome, detail = parsed_marker
    if not detail:
        return (
            _warning_issue(
                rule_id="planning_hotspot_outcome_invalid",
                message=(
                    f"{relative_path} should explain the Hotspot Outcome for "
                    f"{', '.join(hotspot_paths)}."
                ),
                path=relative_path,
            ),
        )
    if outcome == "follow-up-task-created" and _TASK_ID_PATTERN.search(detail) is None:
        return (
            _warning_issue(
                rule_id="planning_hotspot_followup_missing_task",
                message=(
                    f"{relative_path} should name the follow-up TASK-XXX when the Hotspot Outcome "
                    "is follow-up-task-created."
                ),
                path=relative_path,
            ),
        )
    if outcome == "follow-up-task-created" and known_task_ids is not None:
        referenced_task_ids = set(_TASK_ID_PATTERN.findall(detail))
        if referenced_task_ids and not referenced_task_ids.intersection(known_task_ids):
            return (
                _warning_issue(
                    rule_id="planning_hotspot_followup_unknown_task",
                    message=(
                        f"{relative_path} should reference an existing backlog task when the "
                        "Hotspot Outcome is follow-up-task-created."
                    ),
                    path=relative_path,
                ),
            )
    return ()


def _allowlisted_production_hotspot_paths(repo_root: Path) -> tuple[str, ...]:
    policy_path = repo_root / _CODE_SHAPE_POLICY_RELATIVE_PATH
    if not policy_path.exists():
        return ()
    policy = load_code_shape_policy(policy_path)
    return tuple(
        sorted(
            path
            for path, legacy_policy in policy.legacy_files.items()
            if not path.startswith("tests/")
            and (
                legacy_policy.max_lines is not None
                or bool(legacy_policy.member_max_lines)
                or bool(legacy_policy.member_max_complexity)
            )
        )
    )


def _warning_issue(*, rule_id: str, message: str, path: str) -> DocsFreshnessIssue:
    return DocsFreshnessIssue(level="warning", rule_id=rule_id, message=message, path=path)


__all__ = [
    "backlog_planning_issues",
    "hotspot_outcome_issues",
    "hotspot_outcome_marker_value",
    "hotspot_outcome_marker_values",
    "matches_declared_task_path",
    "matching_allowlisted_hotspot_paths",
    "parse_hotspot_outcome_marker",
    "planning_exec_plan_issues",
    "planning_spec_issues",
    "task_file_paths_from_block",
    "task_hotspot_paths",
    "template_planning_issues",
]
