from __future__ import annotations

from pathlib import Path

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import _task_preflight_guard as guard_module


def eligibility_data(task_input: str) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)
    current_sprint_path = shared._compat_attr("current_sprint_path", task_repo)
    sprint_file = Path(shared.getenv("TASK_ELIGIBILITY_SPRINT_FILE") or current_sprint_path())
    if not sprint_file.exists():
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"sprint_file": str(sprint_file)},
            [f"Missing sprint file: {sprint_file}"],
        )

    active_section_text = shared._compat_attr("active_section_text", task_repo)
    try:
        _ = active_section_text(sprint_file)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {"sprint_file": str(sprint_file)}, [str(exc)])

    parse_active_tasks = shared._compat_attr("parse_active_tasks", task_repo)
    matched_task = next(
        (task for task in parse_active_tasks(sprint_file) if task.task_id == task_id), None
    )
    if matched_task is None:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "sprint_file": str(sprint_file)},
            [f"{task_id} is not listed in Active Tasks ({sprint_file})"],
        )
    if matched_task.requires_human:
        return (
            ExitCode.VALIDATION_ERROR,
            {"task_id": task_id, "requires_human": True},
            [f"{task_id} is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"],
        )

    preflight_override = shared.getenv("TASK_ELIGIBILITY_PREFLIGHT_CMD")
    if preflight_override and preflight_override != "./scripts/check_task_start_preflight.sh":
        preflight_result = shared._run_shell(preflight_override)
        if preflight_result.returncode != 0:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "preflight_cmd": preflight_override},
                [f"Task sequencing preflight failed for {task_id}."],
            )
    else:
        preflight_exit, preflight_data, preflight_lines = guard_module.task_preflight_data(
            task_id=task_id,
            allow_task_ledger_intake=True,
        )
        if preflight_exit != ExitCode.OK:
            return (
                preflight_exit,
                {"task_id": task_id, "preflight": preflight_data},
                [*preflight_lines, f"Task sequencing preflight failed for {task_id}."],
            )

    return (
        ExitCode.OK,
        {"task_id": task_id, "sprint_file": str(sprint_file), "requires_human": False},
        [f"Agent task eligibility passed: {task_id}"],
    )


__all__ = [
    "eligibility_data",
]
