from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ._docs_freshness_models import DocsFreshnessIssue
from ._docs_freshness_parsing import _extract_task_ids

_PLANNING_GATES_LINE_PATTERN = re.compile(
    r"^(?:-\s+)?(?:\*\*)?Planning Gates(?:\*\*)?:\s*(?P<value>.+)$",
    re.MULTILINE,
)
_EXEC_PLAN_LINE_PATTERN = re.compile(r"^\*\*Exec Plan\*\*:\s*(?P<value>.+)$", re.MULTILINE)
_TASK_ID_FROM_SPEC_PATH = re.compile(r"^(?P<task_num>\d{3})-[^.]+\.md$")
_TASK_ID_FROM_EXEC_PLAN_PATH = re.compile(r"^(?P<task_id>TASK-\d{3})\.md$")
_PLANNING_CHANGED_DEFAULT_BASE_REF = "main"


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


def _planning_state_for_task(
    repo_root: Path,
    *,
    task_id: str,
    backlog_text: str,
) -> dict[str, str | bool | None]:
    backlog_block = _extract_task_block(backlog_text, task_id) or ""
    spec_paths = _task_spec_paths(repo_root, task_id)
    exec_plan_paths = _task_exec_plan_paths(repo_root, task_id)

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


def _validate_planning_artifact(
    *,
    repo_root: Path,
    relative_path: str,
    backlog_text: str,
    planning_spec_section_heading: str,
    planning_exec_plan_section_heading: str,
    planning_core_gate_labels: tuple[str, ...],
    planning_conditional_gate_labels: tuple[str, ...],
    planning_state_for_task: Callable[..., dict[str, str | bool | None]] = _planning_state_for_task,
) -> tuple[DocsFreshnessIssue, ...]:
    issues: list[DocsFreshnessIssue] = []
    path = repo_root / relative_path
    if not path.exists():
        return ()

    content = path.read_text(encoding="utf-8")
    if relative_path == "tasks/specs/TEMPLATE.md":
        if "**Planning Gates**:" not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_marker_missing",
                    message="Spec template should define the canonical Planning Gates marker.",
                    path=relative_path,
                )
            )
        if planning_spec_section_heading not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_spec_section_missing",
                    message="Spec template should include the Phase -1 / Pre-Implementation Gates section.",
                    path=relative_path,
                )
            )
        return tuple(issues)

    if relative_path == "tasks/exec_plans/TEMPLATE.md":
        if "Planning Gates:" not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_marker_missing",
                    message="Exec-plan template should mirror the Planning Gates marker scheme.",
                    path=relative_path,
                )
            )
        if planning_exec_plan_section_heading not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_gate_outcomes_missing",
                    message="Exec-plan template should include Gate Outcomes / Waivers.",
                    path=relative_path,
                )
            )
        return tuple(issues)

    if relative_path == "tasks/BACKLOG.md":
        for backlog_task_id in sorted(_extract_task_ids(backlog_text)):
            state = planning_state_for_task(
                repo_root,
                task_id=backlog_task_id,
                backlog_text=backlog_text,
            )
            if state["state"] != "applicable_backlog_only_missing_artifact":
                continue
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_artifact_missing",
                    message=(
                        f"{backlog_task_id} requires planning gates, but the backlog entry is still the only "
                        "planning artifact. Add a task spec or exec plan before implementation."
                    ),
                    path=relative_path,
                )
            )
        return tuple(issues)

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
        if _planning_marker_value(content) is None:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_marker_missing",
                    message=f"{relative_path} should include an explicit Planning Gates marker.",
                    path=relative_path,
                )
            )
        if planning_spec_section_heading not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_spec_section_missing",
                    message=f"{relative_path} should include {planning_spec_section_heading}.",
                    path=relative_path,
                )
            )
            return tuple(issues)
        for gate_label in planning_core_gate_labels:
            if gate_label not in content:
                issues.append(
                    DocsFreshnessIssue(
                        level="warning",
                        rule_id="planning_core_gate_missing",
                        message=f"{relative_path} is missing required core gate {gate_label}.",
                        path=relative_path,
                    )
                )
        for gate_label in planning_conditional_gate_labels:
            if gate_label not in content:
                issues.append(
                    DocsFreshnessIssue(
                        level="warning",
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
                DocsFreshnessIssue(
                    level="warning",
                    rule_id="planning_integration_proof_incomplete",
                    message=(
                        f"{relative_path} should name an Integration-First validation target and the "
                        "contract/dependency/invariant it exercises."
                    ),
                    path=relative_path,
                )
            )
        return tuple(issues)

    if (
        relative_path.startswith("tasks/exec_plans/")
        and relative_path != "tasks/exec_plans/TEMPLATE.md"
    ):
        if planning_exec_plan_section_heading not in content:
            issues.append(
                DocsFreshnessIssue(
                    level="warning",
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
                    DocsFreshnessIssue(
                        level="warning",
                        rule_id="planning_gate_outcome_field_missing",
                        message=f"{relative_path} should include '{required_phrase}'.",
                        path=relative_path,
                    )
                )
        return tuple(issues)

    return tuple(issues)  # pragma: no cover
