from __future__ import annotations

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode


def _resolve_finish_context(
    task_input: str | None, config: shared.FinishConfig
) -> tuple[int, dict[str, object], list[str]] | shared.FinishContext:
    branch_result = shared._run_command([config.git_bin, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(branch_result, "Unable to determine current branch."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    current_branch = branch_result.stdout.strip()
    if current_branch == "HEAD":
        return shared._task_blocked(
            "detached HEAD is not allowed.",
            next_action="Check out the task branch you want to finish, then re-run `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )
    requested_task_id: str | None = None
    if task_input is not None:
        requested_task_id = shared._compat_attr("normalize_task_id", task_repo)(task_input)
    if current_branch == "main":
        if requested_task_id is not None:
            lifecycle_result = lifecycle.resolve_task_lifecycle(requested_task_id, config=config)
            if isinstance(lifecycle_result, tuple):
                exit_code, data, lines = lifecycle_result
                return shared._task_blocked(
                    "unable to recover task context from 'main'.",
                    next_action=(
                        f"Restore the branch or PR state for {requested_task_id}, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id, **data},
                    exit_code=exit_code,
                    extra_lines=lines,
                )
            if not lifecycle_result.working_tree_clean:
                return shared._task_blocked(
                    "working tree must be clean.",
                    next_action=(
                        "Commit or stash local changes, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id},
                )
            if lifecycle_result.branch_name is None:
                return shared._task_blocked(
                    f"unable to resolve a task branch for {requested_task_id} from 'main'.",
                    next_action=(
                        f"Restore the task branch or open PR for {requested_task_id}, then re-run "
                        f"`horadus tasks finish {requested_task_id}`."
                    ),
                    data={"current_branch": current_branch, "task_id": requested_task_id},
                )
            return shared.FinishContext(
                branch_name=lifecycle_result.branch_name,
                branch_task_id=requested_task_id,
                task_id=requested_task_id,
                current_branch=current_branch,
            )
        return shared._task_blocked(
            "refusing to run on 'main'.",
            next_action=(
                "Re-run `horadus tasks finish TASK-XXX` with an explicit task id, or switch to "
                "the task branch that owns the PR lifecycle you want to finish."
            ),
            data={"current_branch": current_branch},
        )

    match = shared.TASK_BRANCH_PATTERN.match(current_branch)
    if match is None:
        return shared._task_blocked(
            (
                "branch does not match the required task pattern "
                f"`codex/task-XXX-short-name`: {current_branch}"
            ),
            next_action="Switch to a canonical task branch before running `horadus tasks finish`.",
            data={"current_branch": current_branch},
        )

    branch_task_id = f"TASK-{match.group('number')}"
    requested_task_id = branch_task_id
    if task_input is not None:
        requested_task_id = shared._compat_attr("normalize_task_id", task_repo)(task_input)
        if requested_task_id != branch_task_id:
            return shared._task_blocked(
                (f"branch {current_branch} maps to {branch_task_id}, not {requested_task_id}."),
                next_action=(
                    f"Run `horadus tasks finish {branch_task_id}` on this branch, or switch to the "
                    f"branch for {requested_task_id}."
                ),
                data={
                    "current_branch": current_branch,
                    "branch_task_id": branch_task_id,
                    "task_id": requested_task_id,
                },
            )

    status_result = shared._run_command([config.git_bin, "status", "--porcelain"])
    if status_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(status_result, "Unable to determine working tree state."),
            next_action="Resolve local git issues, then re-run `horadus tasks finish`.",
            data={"branch_name": current_branch, "task_id": requested_task_id},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if status_result.stdout.strip():
        return shared._task_blocked(
            "working tree must be clean.",
            next_action=(
                "Commit or stash local changes, then re-run "
                f"`horadus tasks finish {requested_task_id}`."
            ),
            data={"branch_name": current_branch, "task_id": requested_task_id},
        )

    return shared.FinishContext(
        branch_name=current_branch,
        branch_task_id=branch_task_id,
        task_id=requested_task_id,
        current_branch=current_branch,
    )


__all__ = ["_resolve_finish_context"]
