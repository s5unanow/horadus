from __future__ import annotations

import shutil

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

from . import _task_preflight_checks as checks_module
from . import _task_preflight_intake as intake_module


def assert_safe_worktree_data() -> tuple[int, dict[str, object], list[str]]:
    branch_result = shared._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        message = (
            branch_result.stderr.strip()
            or branch_result.stdout.strip()
            or "Unable to determine the current git branch."
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"branch_error": message},
            ["Dirty-main watchdog failed.", message],
        )

    current_branch = branch_result.stdout.strip()
    status_result = shared._run_command(["git", "status", "--porcelain", "--untracked-files=no"])
    if status_result.returncode != 0:
        message = (
            status_result.stderr.strip()
            or status_result.stdout.strip()
            or "Unable to inspect tracked git status."
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"current_branch": current_branch, "status_error": message},
            ["Dirty-main watchdog failed.", message],
        )

    tracked_dirty_paths = intake_module._git_status_dirty_paths(status_result.stdout)
    result_data: dict[str, object] = {
        "current_branch": current_branch,
        "tracked_dirty_paths": tracked_dirty_paths,
        "watchdog_applicable": current_branch == "main",
        "working_tree_clean": not tracked_dirty_paths,
    }
    if current_branch != "main":
        return (
            ExitCode.OK,
            result_data,
            [f"Dirty-main watchdog skipped: current branch is {current_branch}."],
        )
    if not tracked_dirty_paths:
        return (
            ExitCode.OK,
            result_data,
            ["Dirty-main watchdog passed: no tracked diffs on 'main'."],
        )
    return (
        ExitCode.VALIDATION_ERROR,
        result_data,
        [
            "Dirty-main watchdog failed.",
            "Tracked diffs on 'main' are not allowed for chat/agent sessions.",
            f"Tracked dirty paths: {', '.join(tracked_dirty_paths)}",
            "Create or switch to a task branch with "
            "`uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name` "
            "before continuing tracked edits.",
        ],
    )


def task_preflight_data(
    *,
    task_id: str | None = None,
    allow_task_ledger_intake: bool = False,
) -> tuple[int, dict[str, object], list[str]]:
    if shared.getenv("SKIP_TASK_SEQUENCE_GUARD") == "1":
        data: dict[str, object] = {"skipped": True}
        return (ExitCode.OK, data, ["Task sequencing guard skipped (SKIP_TASK_SEQUENCE_GUARD=1)."])

    gh_path = shutil.which("gh")
    if gh_path is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": "gh"},
            ["Task sequencing guard failed.", "GitHub CLI (gh) is required for open-PR checks."],
        )

    hooks_ok, missing_hooks = checks_module._ensure_required_hooks()
    if not hooks_ok:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_hooks": missing_hooks},
            [
                "Task sequencing guard failed.",
                f"Required local git hooks are missing: {', '.join(missing_hooks)}.",
            ],
        )

    branch_result = shared._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = branch_result.stdout.strip()
    if current_branch != "main":
        return (
            ExitCode.VALIDATION_ERROR,
            {"current_branch": current_branch},
            [
                "Task sequencing guard failed.",
                f"You must start tasks from 'main'. Current branch: {current_branch}",
            ],
        )

    status_result = shared._run_command(["git", "status", "--porcelain"])
    dirty_paths = intake_module._git_status_dirty_paths(status_result.stdout)
    intake_state = intake_module._task_ledger_intake_state(
        task_id=task_id if allow_task_ledger_intake else None,
        dirty_paths=dirty_paths,
    )
    if dirty_paths and not (allow_task_ledger_intake and intake_state.ready):
        dirty_data: dict[str, object] = {
            "working_tree_clean": False,
            "dirty_paths": dirty_paths,
            "eligible_dirty_paths": intake_state.eligible_paths,
            "blocking_dirty_paths": intake_state.blocking_paths,
            "intake_consistency_errors": intake_state.consistency_errors,
        }
        lines = [
            "Task sequencing guard failed.",
            "Working tree must be clean before starting a new task branch.",
        ]
        if allow_task_ledger_intake and intake_state.eligible_paths:
            lines.append(
                f"Eligible planning intake files for {task_id}: "
                f"{', '.join(intake_state.eligible_paths)}"
            )
        elif intake_state.eligible_paths and not intake_state.blocking_paths:
            lines.append(
                "Detected planning-intake-only dirty files: "
                f"{', '.join(intake_state.eligible_paths)}"
            )
            lines.append(
                "Run `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name` "
                "to check whether they can be carried onto a new task branch."
            )
        if intake_state.blocking_paths:
            lines.append(f"Blocking dirty files: {', '.join(intake_state.blocking_paths)}")
        lines.extend(intake_state.consistency_errors)
        return (ExitCode.VALIDATION_ERROR, dirty_data, lines)

    fetch_result = shared._run_command(["git", "fetch", "origin", "main", "--quiet"])
    if fetch_result.returncode != 0:
        message = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch failed"
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"fetch_error": message},
            ["Task sequencing guard failed.", message],
        )

    local_sha = shared._run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = shared._run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        return (
            ExitCode.VALIDATION_ERROR,
            {"local_main_sha": local_sha, "remote_main_sha": remote_sha},
            ["Task sequencing guard failed.", "Local main is not synced to origin/main."],
        )

    if shared.getenv("ALLOW_OPEN_TASK_PRS") != "1":
        ok, pr_result = checks_module._open_task_prs()
        if not ok:
            return (
                ExitCode.ENVIRONMENT_ERROR,
                {"open_pr_query_error": pr_result},
                ["Task sequencing guard failed.", "Unable to query open PRs via GitHub CLI."],
            )
        if pr_result:
            return (
                ExitCode.VALIDATION_ERROR,
                {"open_task_prs": pr_result},
                [
                    "Task sequencing guard failed.",
                    "Open non-merged task PR(s) already exist for current user:",
                    *list(pr_result),
                ],
            )

    result_data: dict[str, object] = {
        "gh_path": gh_path,
        "working_tree_clean": not dirty_paths,
        "local_main_sha": local_sha,
        "remote_main_sha": remote_sha,
        "dirty_paths": dirty_paths,
        "eligible_dirty_paths": intake_state.eligible_paths,
        "blocking_dirty_paths": intake_state.blocking_paths,
    }
    return (
        ExitCode.OK,
        result_data,
        [
            "Task sequencing guard passed: main is synced and no open task PRs.",
            *(
                [
                    f"Eligible planning intake files will carry onto the new branch for {task_id}: "
                    f"{', '.join(intake_state.eligible_paths)}"
                ]
                if intake_state.eligible_paths
                else []
            ),
        ],
    )


def _preflight_result() -> CommandResult:
    exit_code, data, lines = task_preflight_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def _assert_safe_worktree_result() -> CommandResult:
    exit_code, data, lines = assert_safe_worktree_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "_assert_safe_worktree_result",
    "_preflight_result",
    "assert_safe_worktree_data",
    "task_preflight_data",
]
