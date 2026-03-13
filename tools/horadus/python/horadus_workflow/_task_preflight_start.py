from __future__ import annotations

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import _task_preflight_eligibility as eligibility_module
from . import _task_preflight_guard as guard_module


def start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)
    slug = task_repo.slugify_name(raw_name)
    branch_name = f"codex/task-{task_id[5:]}-{slug}"

    preflight_exit, preflight_data, preflight_lines = guard_module.task_preflight_data(
        task_id=task_id,
        allow_task_ledger_intake=True,
    )
    if preflight_exit != ExitCode.OK:
        return (
            preflight_exit,
            {"branch_name": branch_name, "preflight": preflight_data},
            preflight_lines,
        )

    local_exists = (
        shared._run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"]
        ).returncode
        == 0
    )
    if local_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists locally: {branch_name}"],
        )

    remote_exists = (
        shared._run_command(
            ["git", "ls-remote", "--exit-code", "--heads", "origin", branch_name]
        ).returncode
        == 0
    )
    if remote_exists:
        return (
            ExitCode.VALIDATION_ERROR,
            {"branch_name": branch_name},
            [f"Branch already exists on origin: {branch_name}"],
        )

    lines = list(preflight_lines)
    if dry_run:
        lines.append(f"Dry run: would create task branch {branch_name}")
        return (
            ExitCode.OK,
            {"task_id": task_id, "branch_name": branch_name, "dry_run": True},
            lines,
        )

    switch_result = shared._run_command(["git", "switch", "-c", branch_name])
    if switch_result.returncode != 0:
        message = (
            switch_result.stderr.strip() or switch_result.stdout.strip() or "git switch failed"
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"task_id": task_id, "branch_name": branch_name, "error": message},
            [message],
        )

    lines.extend(
        [
            f"Switched to a new branch '{branch_name}'",
            f"Created task branch: {branch_name}",
        ]
    )
    return (
        ExitCode.OK,
        {"task_id": task_id, "branch_name": branch_name, "dry_run": False},
        lines,
    )


def safe_start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)

    eligibility_exit, eligibility_data_payload, eligibility_lines = (
        eligibility_module.eligibility_data(task_id)
    )
    if eligibility_exit != ExitCode.OK:
        return (eligibility_exit, eligibility_data_payload, eligibility_lines)

    start_exit, start_data_payload, start_lines = start_task_data(
        task_id, raw_name, dry_run=dry_run
    )
    return (start_exit, start_data_payload, [*eligibility_lines, *start_lines])


__all__ = [
    "safe_start_task_data",
    "start_task_data",
]
