from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ._docs_freshness_models import DocsFreshnessIssue
from ._docs_freshness_parsing import _extract_task_ids
from .code_shape import load_code_shape_policy

_PLANNING_GATES_LINE_PATTERN = re.compile(
    r"^(?:-\s+)?(?:\*\*)?Planning Gates(?:\*\*)?:\s*(?P<value>.+)$",
    re.MULTILINE,
)
_EXEC_PLAN_LINE_PATTERN = re.compile(r"^\*\*Exec Plan\*\*:\s*(?P<value>.+)$", re.MULTILINE)
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
_TASK_ID_FROM_SPEC_PATH = re.compile(r"^(?P<task_num>\d{3})-[^.]+\.md$")
_TASK_ID_FROM_EXEC_PLAN_PATH = re.compile(r"^(?P<task_id>TASK-\d{3})\.md$")
_PLANNING_CHANGED_DEFAULT_BASE_REF = "main"
_CODE_SHAPE_POLICY_RELATIVE_PATH = Path("config/quality/code_shape.toml")


def _planning_marker_value(content: str) -> str | None:
    match = _PLANNING_GATES_LINE_PATTERN.search(content)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _planning_required_from_value(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lstrip("`*_ ").lower()
    if normalized.startswith("required"):
        return True
    if normalized.startswith("not required"):
        return False
    return None


def _exec_plan_required_from_backlog(content: str) -> bool:
    match = _EXEC_PLAN_LINE_PATTERN.search(content)
    if match is None:
        return False
    return match.group("value").strip().lower().startswith("required")


def _task_id_from_planning_artifact_path(path: str) -> str | None:
    normalized = Path(path)
    if normalized.parts[:2] == ("tasks", "specs"):
        match = _TASK_ID_FROM_SPEC_PATH.match(normalized.name)
        if match is None:
            return None
        return f"TASK-{match.group('task_num')}"
    if normalized.parts[:2] == ("tasks", "exec_plans"):
        match = _TASK_ID_FROM_EXEC_PLAN_PATH.match(normalized.name)
        if match is None:
            return None
        return match.group("task_id")
    return None


def _extract_task_block(content: str, task_id: str) -> str | None:
    task_header_pattern = re.compile(
        rf"^### {re.escape(task_id)}: .+?\n(?P<body>.*?)(?=^---\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = task_header_pattern.search(content)
    if match is None:
        return None
    return match.group(0)


def _task_spec_paths(repo_root: Path, task_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(path.relative_to(repo_root))
            for path in (repo_root / "tasks" / "specs").glob(f"{task_id[5:]}-*.md")
        )
    )


def _task_exec_plan_paths(repo_root: Path, task_id: str) -> tuple[str, ...]:
    candidate = repo_root / "tasks" / "exec_plans" / f"{task_id}.md"
    if not candidate.exists():
        return ()
    return (str(candidate.relative_to(repo_root)),)


def _task_file_paths_from_block(task_block: str) -> tuple[str, ...]:
    paths: list[str] = []
    for match in _FILES_LINE_PATTERN.finditer(task_block):
        raw_value = match.group("value").strip()
        if not raw_value:
            continue
        backticked_paths = [item.strip() for item in _BACKTICKED_PATH_PATTERN.findall(raw_value)]
        if backticked_paths:
            paths.extend(backticked_paths)
            continue
        paths.extend(item.strip() for item in raw_value.split(",") if item.strip())
    return tuple(dict.fromkeys(paths))


def _matches_declared_task_path(declared_path: str, candidate_path: str) -> bool:
    normalized = declared_path.strip().strip("`").rstrip("/")
    if not normalized:
        return False
    return candidate_path == normalized or candidate_path.startswith(f"{normalized}/")


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


def _matching_allowlisted_hotspot_paths(
    repo_root: Path, declared_paths: Sequence[str]
) -> tuple[str, ...]:
    normalized_paths = [path.strip() for path in declared_paths if path.strip()]
    if not normalized_paths:
        return ()
    return tuple(
        hotspot_path
        for hotspot_path in _allowlisted_production_hotspot_paths(repo_root)
        if any(
            _matches_declared_task_path(declared_path, hotspot_path)
            for declared_path in normalized_paths
        )
    )


def _task_hotspot_paths(repo_root: Path, *, task_id: str, backlog_text: str) -> tuple[str, ...]:
    backlog_block = _extract_task_block(backlog_text, task_id) or ""
    return _matching_allowlisted_hotspot_paths(
        repo_root,
        _task_file_paths_from_block(backlog_block),
    )


def _hotspot_outcome_marker_value(content: str) -> str | None:
    match = _HOTSPOT_OUTCOME_LINE_PATTERN.search(content)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _parse_hotspot_outcome_marker(value: str | None) -> tuple[str, str | None] | None:
    if value is None:
        return None
    match = _HOTSPOT_OUTCOME_VALUE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    detail = match.group("detail")
    return match.group("outcome").lower(), detail.strip() if detail is not None else None


def _planning_state_for_task(
    repo_root: Path,
    *,
    task_id: str,
    backlog_text: str,
) -> dict[str, object]:
    backlog_block = _extract_task_block(backlog_text, task_id) or ""
    spec_paths = _task_spec_paths(repo_root, task_id)
    exec_plan_paths = _task_exec_plan_paths(repo_root, task_id)
    hotspot_paths = _matching_allowlisted_hotspot_paths(
        repo_root,
        _task_file_paths_from_block(backlog_block),
    )

    explicit_value = None
    marker_source = None
    for relative_path in [*exec_plan_paths, *spec_paths]:
        content = (repo_root / relative_path).read_text(encoding="utf-8")
        explicit_value = _planning_marker_value(content)
        if explicit_value is not None:
            marker_source = relative_path
            break
    if explicit_value is None:
        explicit_value = _planning_marker_value(backlog_block)
        if explicit_value is not None:
            marker_source = "tasks/BACKLOG.md"

    required = _planning_required_from_value(explicit_value)
    if required is None:
        required = _exec_plan_required_from_backlog(backlog_block) or bool(exec_plan_paths)
    if hotspot_paths:
        required = True

    state = "non_applicable"
    authoritative_artifact = None
    if required:
        if exec_plan_paths:
            state = "applicable_with_authoritative_artifact_present"
            authoritative_artifact = exec_plan_paths[0]
        elif spec_paths:
            state = "applicable_spec_backed_without_exec_plan"
            authoritative_artifact = spec_paths[0]
        else:
            state = "applicable_backlog_only_missing_artifact"

    return {
        "required": required,
        "marker_value": explicit_value,
        "marker_source": marker_source,
        "state": state,
        "authoritative_artifact": authoritative_artifact,
        "spec_path": spec_paths[0] if spec_paths else None,
        "exec_plan_path": exec_plan_paths[0] if exec_plan_paths else None,
        "hotspot_paths": hotspot_paths,
        "hotspot_outcome_required": bool(hotspot_paths),
    }


def _changed_planning_artifact_paths(
    repo_root: Path,
    *,
    base_ref: str = _PLANNING_CHANGED_DEFAULT_BASE_REF,
    git_which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., Any] = subprocess.run,
) -> tuple[str, ...]:
    git_bin = git_which("git")
    if git_bin is None:
        return ()
    try:
        merge_base_result = run(  # nosec B603
            [git_bin, "merge-base", "HEAD", base_ref],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if merge_base_result.returncode != 0:
            return ()
        merge_base = merge_base_result.stdout.strip()
        if not merge_base:
            return ()
        diff_result = run(  # nosec B603
            [git_bin, "diff", "--name-only", f"{merge_base}...HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if diff_result.returncode != 0:
            return ()
    except FileNotFoundError:
        return ()

    paths: list[str] = []
    for raw_line in diff_result.stdout.splitlines():
        path = raw_line.strip()
        if not path:
            continue
        if path == "tasks/BACKLOG.md":
            paths.append(path)
            continue
        if path in {"tasks/specs/TEMPLATE.md", "tasks/exec_plans/TEMPLATE.md"}:
            paths.append(path)
            continue
        if path.startswith("tasks/specs/") and path.endswith(".md"):
            paths.append(path)
            continue
        if path.startswith("tasks/exec_plans/") and path.endswith(".md"):
            paths.append(path)
            continue
    return tuple(dict.fromkeys(paths))


def _warning_issue(*, rule_id: str, message: str, path: str) -> DocsFreshnessIssue:
    return DocsFreshnessIssue(level="warning", rule_id=rule_id, message=message, path=path)


def _template_planning_issues(
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


def _backlog_planning_issues(
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
            repo_root,
            task_id=backlog_task_id,
            backlog_text=backlog_text,
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


def _planning_spec_issues(
    *,
    relative_path: str,
    content: str,
    planning_spec_section_heading: str,
    planning_core_gate_labels: tuple[str, ...],
    planning_conditional_gate_labels: tuple[str, ...],
) -> tuple[DocsFreshnessIssue, ...]:
    issues: list[DocsFreshnessIssue] = []
    if _planning_marker_value(content) is None:
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


def _planning_exec_plan_issues(
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


def _hotspot_outcome_issues(
    *,
    relative_path: str,
    content: str,
    planning_state: dict[str, object],
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

    marker_value = _hotspot_outcome_marker_value(content)
    canonical_marker = (
        "`- Hotspot Outcome: reduce — ...` or "
        "`- Hotspot Outcome: keep-flat-with-rationale — ...` or "
        "`- Hotspot Outcome: follow-up-task-created — TASK-XXX ...`"
    )
    if marker_value is None:
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

    parsed_marker = _parse_hotspot_outcome_marker(marker_value)
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
    return ()


def _validate_planning_artifact(
    *,
    repo_root: Path,
    relative_path: str,
    backlog_text: str,
    planning_spec_section_heading: str,
    planning_exec_plan_section_heading: str,
    planning_core_gate_labels: tuple[str, ...],
    planning_conditional_gate_labels: tuple[str, ...],
    planning_state_for_task: Callable[..., dict[str, object]] = _planning_state_for_task,
) -> tuple[DocsFreshnessIssue, ...]:
    path = repo_root / relative_path
    if not path.exists():
        return ()

    content = path.read_text(encoding="utf-8")
    template_issues = _template_planning_issues(
        relative_path=relative_path,
        content=content,
        planning_spec_section_heading=planning_spec_section_heading,
        planning_exec_plan_section_heading=planning_exec_plan_section_heading,
    )
    if template_issues:
        return template_issues

    backlog_issues = _backlog_planning_issues(
        repo_root=repo_root,
        backlog_text=backlog_text,
        planning_state_for_task=planning_state_for_task,
        relative_path=relative_path,
    )
    if backlog_issues:
        return backlog_issues

    artifact_task_id = _task_id_from_planning_artifact_path(relative_path)
    if artifact_task_id is None:
        return ()
    planning_state = planning_state_for_task(
        repo_root,
        task_id=artifact_task_id,
        backlog_text=backlog_text,
    )
    if not bool(planning_state["required"]):
        return ()

    if relative_path.startswith("tasks/specs/"):
        return (
            *_planning_spec_issues(
                relative_path=relative_path,
                content=content,
                planning_spec_section_heading=planning_spec_section_heading,
                planning_core_gate_labels=planning_core_gate_labels,
                planning_conditional_gate_labels=planning_conditional_gate_labels,
            ),
            *_hotspot_outcome_issues(
                relative_path=relative_path,
                content=content,
                planning_state=planning_state,
            ),
        )

    if (
        relative_path.startswith("tasks/exec_plans/")
        and relative_path != "tasks/exec_plans/TEMPLATE.md"
    ):
        return (
            *_planning_exec_plan_issues(
                relative_path=relative_path,
                content=content,
                planning_exec_plan_section_heading=planning_exec_plan_section_heading,
            ),
            *_hotspot_outcome_issues(
                relative_path=relative_path,
                content=content,
                planning_state=planning_state,
            ),
        )

    return ()  # pragma: no cover
