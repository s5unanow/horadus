from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared

_TASK_LEDGER_INTAKE_PATHS = (
    "tasks/BACKLOG.md",
    "tasks/CURRENT_SPRINT.md",
)


@dataclass(slots=True)
class TaskLedgerIntakeState:
    task_id: str | None
    dirty_paths: list[str]
    eligible_paths: list[str]
    blocking_paths: list[str]
    consistency_errors: list[str]

    @property
    def ready(self) -> bool:
        return bool(self.eligible_paths) and not self.blocking_paths and not self.consistency_errors


def _git_status_dirty_paths(status_output: str) -> list[str]:
    paths: list[str] = []
    for raw_line in status_output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        candidate = line[3:].strip() if len(line) >= 4 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1].strip()
        if candidate.startswith('"') and candidate.endswith('"'):
            candidate = candidate[1:-1]
        if candidate:
            paths.append(candidate)
    return paths


def _head_text_for_path(path: str) -> str:
    result = shared._run_command(["git", "show", f"HEAD:{path}"])
    if result.returncode != 0:
        return ""
    return result.stdout


def _working_tree_text_for_path(path: str) -> str:
    try:
        repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
        return (repo_root() / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _index_text_for_path(path: str) -> str:
    result = shared._run_command(["git", "show", f":{path}"])
    if result.returncode != 0:
        return ""
    return result.stdout


def _diff_texts_for_path(path: str) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for diff_kind, args in (
        ("unstaged", ["git", "diff", "--unified=20", "--", path]),
        ("staged", ["git", "diff", "--cached", "--unified=20", "--", path]),
    ):
        result = shared._run_command(args)
        if result.returncode == 0 and result.stdout.strip():
            texts.append((diff_kind, result.stdout))
    return texts


def _changed_line_numbers(diff_text: str) -> tuple[list[int], list[int]]:
    old_lines: list[int] = []
    new_lines: list[int] = []
    old_line = 0
    new_line = 0
    in_hunk = False
    hunk_pattern = re.compile(
        r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
    )
    for raw_line in diff_text.splitlines():
        match = hunk_pattern.match(raw_line)
        if match is not None:
            old_line = int(match.group("old_start"))
            new_line = int(match.group("new_start"))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            old_lines.append(old_line)
            old_line += 1
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            new_lines.append(new_line)
            new_line += 1
            continue
        if raw_line.startswith(" "):
            old_line += 1
            new_line += 1
    return (old_lines, new_lines)


def _backlog_task_id_for_line(text: str, line_number: int) -> str | None:
    lines = text.splitlines()
    if not lines:
        return None
    bounded_line = min(line_number, len(lines))
    if bounded_line <= 0:
        return None
    current_match = re.match(r"^###\s+(TASK-\d{3}):", lines[bounded_line - 1])
    if current_match is not None:
        return current_match.group(1)
    for index in range(bounded_line - 1, -1, -1):
        if re.match(r"^\s*---\s*$", lines[index]):
            break
        match = re.match(r"^###\s+(TASK-\d{3}):", lines[index])
        if match is not None:
            return match.group(1)
    return None


def _dirty_task_refs_for_path(path: str) -> set[str]:
    diff_texts = _diff_texts_for_path(path)
    if not diff_texts:
        return set()
    if path == "tasks/BACKLOG.md":
        head_text = _head_text_for_path(path)
        index_text = _index_text_for_path(path)
        working_text = _working_tree_text_for_path(path)
        refs: set[str] = set()
        for diff_kind, diff_text in diff_texts:
            old_text = index_text if diff_kind == "unstaged" else head_text
            new_text = working_text if diff_kind == "unstaged" else index_text
            old_lines, new_lines = _changed_line_numbers(diff_text)
            refs.update(
                task_id
                for line_number in old_lines
                if (task_id := _backlog_task_id_for_line(old_text, line_number)) is not None
            )
            refs.update(
                task_id
                for line_number in new_lines
                if (task_id := _backlog_task_id_for_line(new_text, line_number)) is not None
            )
        return refs
    diff_refs: set[str] = set()
    for _diff_kind, diff_text in diff_texts:
        for raw_line in diff_text.splitlines():
            if (raw_line.startswith("+") and not raw_line.startswith("+++")) or (
                raw_line.startswith("-") and not raw_line.startswith("---")
            ):
                diff_refs.update(re.findall(r"TASK-\d{3}", raw_line))
    return diff_refs


def _path_owned_task_start_intake_ref(path: str) -> str | None:
    if path in _TASK_LEDGER_INTAKE_PATHS:
        return None
    if path.startswith("tasks/exec_plans/"):
        return task_repo.task_id_from_exec_plan_path(path)
    if path.startswith("tasks/specs/"):
        return task_repo.task_id_from_spec_path(path)
    return None


def _is_task_start_intake_path(path: str) -> bool:
    return path in _TASK_LEDGER_INTAKE_PATHS or _path_owned_task_start_intake_ref(path) is not None


def _path_owned_task_start_intake_refs_from_diff(path: str) -> set[str]:
    refs: set[str] = set()
    if (owned_task_id := _path_owned_task_start_intake_ref(path)) is not None:
        refs.add(owned_task_id)
    for _diff_kind, diff_text in _diff_texts_for_path(path):
        for raw_line in diff_text.splitlines():
            candidate_path: str | None = None
            if raw_line.startswith("rename from "):
                candidate_path = raw_line.removeprefix("rename from ").strip()
            elif raw_line.startswith("rename to "):
                candidate_path = raw_line.removeprefix("rename to ").strip()
            elif raw_line.startswith("--- "):
                candidate_path = raw_line.removeprefix("--- ").strip()
            elif raw_line.startswith("+++ "):
                candidate_path = raw_line.removeprefix("+++ ").strip()
            if candidate_path is None or candidate_path == "/dev/null":
                continue
            if candidate_path.startswith(("a/", "b/")):
                candidate_path = candidate_path[2:]
            if (task_id := _path_owned_task_start_intake_ref(candidate_path)) is not None:
                refs.add(task_id)
    return refs


def _task_start_intake_refs_for_path(path: str) -> set[str]:
    if _path_owned_task_start_intake_ref(path) is not None:
        return _path_owned_task_start_intake_refs_from_diff(path)
    return _dirty_task_refs_for_path(path)


def _task_ledger_intake_state(
    *,
    task_id: str | None,
    dirty_paths: list[str],
) -> TaskLedgerIntakeState:
    eligible_paths = [path for path in dirty_paths if _is_task_start_intake_path(path)]
    blocking_paths = [path for path in dirty_paths if not _is_task_start_intake_path(path)]
    consistency_errors: list[str] = []
    if task_id is not None:
        task_block_match = shared._compat_attr("task_block_match", task_repo)
        try:
            backlog_match = task_block_match(task_id)
        except FileNotFoundError:
            backlog_match = None
            consistency_errors.append("tasks/BACKLOG.md is missing in the working tree.")
        if backlog_match is None:
            consistency_errors.append(
                f"{task_id} is not present in tasks/BACKLOG.md in the working tree."
            )
        for path in eligible_paths:
            task_refs = _task_start_intake_refs_for_path(path)
            if task_id not in task_refs:
                if _path_owned_task_start_intake_ref(path) is not None:
                    consistency_errors.append(f"{path} does not belong to {task_id}.")
                else:
                    consistency_errors.append(
                        f"{path} does not include {task_id} in its dirty diff."
                    )
            other_refs = sorted(ref for ref in task_refs if ref != task_id)
            if other_refs:
                consistency_errors.append(
                    f"{path} contains edits for other tasks: {', '.join(other_refs)}"
                )
        if "tasks/CURRENT_SPRINT.md" in eligible_paths:
            parse_active_tasks = shared._compat_attr("parse_active_tasks", task_repo)
            try:
                active_tasks = parse_active_tasks()
            except (FileNotFoundError, ValueError) as exc:
                consistency_errors.append(str(exc))
            else:
                if not any(task.task_id == task_id for task in active_tasks):
                    current_sprint_path = shared._compat_attr("current_sprint_path", task_repo)
                    consistency_errors.append(
                        f"{task_id} is not listed in Active Tasks ({current_sprint_path()})"
                    )
    return TaskLedgerIntakeState(
        task_id=task_id,
        dirty_paths=list(dirty_paths),
        eligible_paths=eligible_paths,
        blocking_paths=blocking_paths,
        consistency_errors=consistency_errors,
    )


__all__ = [
    "TaskLedgerIntakeState",
    "_backlog_task_id_for_line",
    "_changed_line_numbers",
    "_diff_texts_for_path",
    "_dirty_task_refs_for_path",
    "_git_status_dirty_paths",
    "_head_text_for_path",
    "_index_text_for_path",
    "_path_owned_task_start_intake_ref",
    "_path_owned_task_start_intake_refs_from_diff",
    "_task_ledger_intake_state",
    "_working_tree_text_for_path",
]
