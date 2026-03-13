from __future__ import annotations

import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import checks


def _pr_state(*, pr_url: str, config: shared.FinishConfig) -> str:
    state_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
    )
    return state_result.stdout.strip() if state_result.returncode == 0 else ""


def complete_merge_data(
    *,
    context: shared.FinishContext,
    pr_url: str,
    pr_state: str,
    config: shared.FinishConfig,
) -> tuple[int, dict[str, object], list[str]]:
    lines: list[str] = []
    if pr_state == "MERGED":
        lines.append("PR already merged; skipping merge step.")
    else:
        lines.append("Merging PR (squash, delete branch)...")
        try:
            merge_result = shared._run_command_with_timeout(
                [config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"],
                timeout_seconds=shared.DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS,
            )
        except shared.CommandTimeoutError as exc:
            state_after = _pr_state(pr_url=pr_url, config=config)
            if state_after != "MERGED":
                return shared._task_blocked(
                    "merge command did not exit cleanly after the review gate passed.",
                    next_action="Inspect the PR merge state in GitHub, then re-run `horadus tasks finish`.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[str(exc), *exc.output_lines()],
                )
            lines.append("Merge command timed out, but PR is already MERGED; continuing.")
            merge_result = subprocess.CompletedProcess(
                args=[config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"],
                returncode=0,
                stdout="",
                stderr="",
            )
        if merge_result.returncode != 0:
            state_after = _pr_state(pr_url=pr_url, config=config)
            if state_after != "MERGED":
                merge_lines = shared._output_lines(merge_result)
                merge_message = "\n".join(merge_lines)
                if "--auto" in merge_message or "prohibits the merge" in merge_message:
                    lines.append(
                        "Base branch policy requires auto-merge; enabling auto-merge and waiting for merge completion."
                    )
                    try:
                        auto_merge_result = shared._run_command_with_timeout(
                            [
                                config.gh_bin,
                                "pr",
                                "merge",
                                pr_url,
                                "--auto",
                                "--squash",
                                "--delete-branch",
                            ],
                            timeout_seconds=shared.DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS,
                        )
                    except shared.CommandTimeoutError as exc:
                        auto_state_after = _pr_state(pr_url=pr_url, config=config)
                        if auto_state_after != "MERGED":
                            return shared._task_blocked(
                                "auto-merge command did not exit cleanly after the review gate passed.",
                                next_action=(
                                    "Inspect the PR auto-merge state in GitHub, then re-run "
                                    "`horadus tasks finish`."
                                ),
                                data={
                                    "task_id": context.task_id,
                                    "branch_name": context.branch_name,
                                    "pr_url": pr_url,
                                },
                                exit_code=ExitCode.ENVIRONMENT_ERROR,
                                extra_lines=[str(exc), *exc.output_lines()],
                            )
                        lines.append(
                            "Auto-merge command timed out, but PR is already MERGED; continuing."
                        )
                        auto_merge_result = subprocess.CompletedProcess(
                            args=[
                                config.gh_bin,
                                "pr",
                                "merge",
                                pr_url,
                                "--auto",
                                "--squash",
                                "--delete-branch",
                            ],
                            returncode=0,
                            stdout="",
                            stderr="",
                        )
                    if auto_merge_result.returncode != 0:
                        auto_state_after = _pr_state(pr_url=pr_url, config=config)
                        if auto_state_after != "MERGED":
                            return shared._task_blocked(
                                "merge failed.",
                                next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                                data={
                                    "task_id": context.task_id,
                                    "branch_name": context.branch_name,
                                    "pr_url": pr_url,
                                },
                                exit_code=ExitCode.ENVIRONMENT_ERROR,
                                extra_lines=shared._output_lines(auto_merge_result),
                            )
                    merged_ok, merged_lines = checks._wait_for_pr_state(
                        pr_url=pr_url, expected_state="MERGED", config=config
                    )
                    if not merged_ok:
                        return shared._task_blocked(
                            "auto-merge did not complete before timeout.",
                            next_action="Wait for the PR to merge in GitHub, then re-run `horadus tasks finish`.",
                            data={
                                "task_id": context.task_id,
                                "branch_name": context.branch_name,
                                "pr_url": pr_url,
                            },
                            exit_code=ExitCode.ENVIRONMENT_ERROR,
                            extra_lines=merged_lines,
                        )
                else:
                    return shared._task_blocked(
                        "merge failed.",
                        next_action="Resolve the merge blocker in GitHub, then re-run `horadus tasks finish`.",
                        data={
                            "task_id": context.task_id,
                            "branch_name": context.branch_name,
                            "pr_url": pr_url,
                        },
                        exit_code=ExitCode.ENVIRONMENT_ERROR,
                        extra_lines=merge_lines,
                    )
            lines.append("Merge step reported failure, but PR is already MERGED; continuing.")

    merge_commit_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "mergeCommit", "--jq", ".mergeCommit.oid"]
    )
    merge_commit = merge_commit_result.stdout.strip()
    if merge_commit_result.returncode != 0 or not merge_commit or merge_commit == "null":
        return shared._task_blocked(
            "could not determine merge commit.",
            next_action="Inspect the merged PR state in GitHub, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    lines.append("Syncing main...")
    switch_main_result = shared._run_command([config.git_bin, "switch", "main"])
    if switch_main_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(switch_main_result, "Failed to switch to main."),
            next_action="Resolve the local git state and switch to `main`, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    pull_result = shared._run_command([config.git_bin, "pull", "--ff-only"])
    if pull_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(pull_result, "Failed to fast-forward local main."),
            next_action="Resolve the local `main` sync issue and re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    cat_file_result = shared._run_command([config.git_bin, "cat-file", "-e", merge_commit])
    if cat_file_result.returncode != 0:
        return shared._task_blocked(
            f"merge commit {merge_commit} is not available locally after syncing main.",
            next_action="Fetch/pull `main` successfully, then re-run `horadus tasks finish`.",
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    branch_exists_result = shared._run_command(
        [config.git_bin, "show-ref", "--verify", f"refs/heads/{context.branch_name}"]
    )
    if branch_exists_result.returncode == 0:
        delete_branch_result = shared._run_command(
            [config.git_bin, "branch", "-d", context.branch_name]
        )
        if delete_branch_result.returncode != 0:
            return shared._task_blocked(
                f"merged branch `{context.branch_name}` still exists locally and could not be deleted.",
                next_action=f"Delete `{context.branch_name}` locally after syncing main, then re-run `horadus tasks finish`.",
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                    "merge_commit": merge_commit,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=shared._output_lines(delete_branch_result),
            )

    lifecycle_exit, lifecycle_data_result, lifecycle_lines = lifecycle.task_lifecycle_data(
        context.task_id,
        strict=True,
        dry_run=False,
    )
    if lifecycle_exit != ExitCode.OK:
        return shared._task_blocked(
            "completion verifier did not pass after merge.",
            next_action=(
                f"Run `horadus tasks lifecycle {context.task_id} --strict`, fix the remaining "
                "repo-state gap, then re-run `horadus tasks finish`."
            ),
            data={
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "merge_commit": merge_commit,
                "lifecycle": lifecycle_data_result,
            },
            exit_code=lifecycle_exit,
            extra_lines=lifecycle_lines,
        )

    lines.append("Completion verifier passed: state local-main-synced.")
    lines.append(f"Task finish passed: merged {merge_commit} and synced main.")
    return (
        ExitCode.OK,
        {
            "merge_commit": merge_commit,
            "lifecycle": lifecycle_data_result,
        },
        lines,
    )


__all__ = ["complete_merge_data"]
