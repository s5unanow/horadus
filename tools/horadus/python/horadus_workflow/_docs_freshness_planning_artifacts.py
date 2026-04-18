from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._docs_freshness_models import DocsFreshnessIssue

from ._docs_freshness_planning_hotspots import (
    backlog_planning_issues as _backlog_planning_issues,
)
from ._docs_freshness_planning_hotspots import (
    hotspot_outcome_issues as _hotspot_outcome_issues,
)
from ._docs_freshness_planning_hotspots import (
    matching_allowlisted_hotspot_paths as _matching_allowlisted_hotspot_paths,
)
from ._docs_freshness_planning_hotspots import (
    planning_exec_plan_issues as _planning_exec_plan_issues,
)
from ._docs_freshness_planning_hotspots import (
    planning_spec_issues as _planning_spec_issues,
)
from ._docs_freshness_planning_hotspots import (
    task_file_paths_from_block as _task_file_paths_from_block,
)
from ._docs_freshness_planning_hotspots import (
    task_hotspot_paths as _task_hotspot_paths_impl,
)
from ._docs_freshness_planning_hotspots import (
    template_planning_issues as _template_planning_issues,
)

_PLANNING_GATES_LINE_PATTERN = re.compile(
    r"^(?:-\s+)?(?:\*\*)?Planning Gates(?:\*\*)?:\s*(?P<value>.+)$",
    re.MULTILINE,
)
_EXEC_PLAN_LINE_PATTERN = re.compile(r"^\*\*Exec Plan\*\*:\s*(?P<value>.+)$", re.MULTILINE)
_TASK_ID_FROM_SPEC_PATH = re.compile(r"^(?P<task_num>\d{3})-[^.]+\.md$")
_TASK_ID_FROM_EXEC_PLAN_PATH = re.compile(r"^(?P<task_id>TASK-\d{3})\.md$")
_BACKLOG_TASK_HEADER_PATTERN = re.compile(r"^### (?P<task_id>TASK-\d{3}): .+$", re.MULTILINE)
_COMPLETED_TASK_LINE_PATTERN = re.compile(r"^-\s+(?P<task_id>TASK-\d{3}):", re.MULTILINE)
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


def _archived_task_block(repo_root: Path, task_id: str) -> str | None:
    archive_root = repo_root / "archive" / "closed_tasks"
    if not archive_root.exists():
        return None
    for archive_path in sorted(archive_root.glob("*.md")):
        task_block = _extract_task_block(archive_path.read_text(encoding="utf-8"), task_id)
        if task_block is not None:
            return task_block
    return None


def _backlog_task_ids(content: str) -> set[str]:
    return {match.group("task_id") for match in _BACKLOG_TASK_HEADER_PATTERN.finditer(content)}


def _completed_task_ids(repo_root: Path) -> set[str]:
    completed_path = repo_root / "tasks" / "COMPLETED.md"
    if not completed_path.exists():
        return set()
    return {
        match.group("task_id")
        for match in _COMPLETED_TASK_LINE_PATTERN.finditer(
            completed_path.read_text(encoding="utf-8")
        )
    }


def _closed_archive_task_ids(repo_root: Path) -> set[str]:
    archive_root = repo_root / "archive" / "closed_tasks"
    if not archive_root.exists():
        return set()

    archived_task_ids: set[str] = set()
    for archive_path in archive_root.glob("*.md"):
        archived_task_ids.update(
            match.group("task_id")
            for match in _BACKLOG_TASK_HEADER_PATTERN.finditer(
                archive_path.read_text(encoding="utf-8")
            )
        )
    return archived_task_ids


def _known_followup_task_ids(repo_root: Path, backlog_text: str) -> set[str]:
    return {
        *_backlog_task_ids(backlog_text),
        *_completed_task_ids(repo_root),
        *_closed_archive_task_ids(repo_root),
    }


def _task_hotspot_paths(
    repo_root: Path,
    *,
    task_id: str,
    backlog_text: str,
) -> tuple[str, ...]:
    return _task_hotspot_paths_impl(
        repo_root,
        task_id=task_id,
        backlog_text=backlog_text,
        extract_task_block=_extract_task_block,
    )


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
) -> dict[str, object]:
    backlog_block = (
        _extract_task_block(backlog_text, task_id) or _archived_task_block(repo_root, task_id) or ""
    )
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
                planning_marker_value=_planning_marker_value,
            ),
            *_hotspot_outcome_issues(
                relative_path=relative_path,
                content=content,
                planning_state=planning_state,
                known_task_ids=_known_followup_task_ids(repo_root, backlog_text),
                current_task_id=artifact_task_id,
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
                known_task_ids=_known_followup_task_ids(repo_root, backlog_text),
                current_task_id=artifact_task_id,
            ),
        )

    return ()  # pragma: no cover


__all__ = [
    "_PLANNING_CHANGED_DEFAULT_BASE_REF",
    "_changed_planning_artifact_paths",
    "_exec_plan_required_from_backlog",
    "_extract_task_block",
    "_planning_marker_value",
    "_planning_required_from_value",
    "_planning_state_for_task",
    "_task_exec_plan_paths",
    "_task_hotspot_paths",
    "_task_id_from_planning_artifact_path",
    "_task_spec_paths",
    "_validate_planning_artifact",
]
