from __future__ import annotations

import json
from typing import Any

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

from . import bootstrap, checks, context, merge, preconditions, review


def _finish_debug_lines(message: str) -> list[str]:
    if not shared._finish_debug_enabled():
        return []
    return [shared._finish_debug_line(message)]


def _resume_lines(finish_context: shared.FinishContext) -> list[str]:
    if (
        finish_context.current_branch is None
        or finish_context.current_branch == finish_context.branch_name
    ):
        return []
    return [
        f"Resuming {finish_context.task_id} from {finish_context.current_branch} using task branch {finish_context.branch_name}."
    ]


def finish_task_data(
    task_input: str | None, *, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    try:
        config = shared._finish_config()
    except ValueError as exc:
        return shared._task_blocked(
            str(exc),
            next_action="Fix the invalid environment override and re-run `horadus tasks finish`.",
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    for command_name in (config.gh_bin, config.git_bin, config.python_bin):
        if shared._ensure_command_available(command_name) is None:
            return shared._task_blocked(
                f"missing required command '{command_name}'.",
                next_action=f"Install or expose `{command_name}` on PATH, then re-run `horadus tasks finish`.",
                data={"missing_command": command_name},
                exit_code=ExitCode.ENVIRONMENT_ERROR,
            )

    finish_context = context._resolve_finish_context(task_input, config)
    if not isinstance(finish_context, shared.FinishContext):
        return finish_context

    bootstrap_result = bootstrap._ensure_finish_pull_request(
        context=finish_context,
        config=config,
        dry_run=dry_run,
    )
    if not isinstance(bootstrap_result, bootstrap.FinishPullRequestBootstrap):
        return bootstrap_result
    pr_url = bootstrap_result.pr_url
    remote_branch_exists = bootstrap_result.remote_branch_exists
    lines: list[str] = _resume_lines(finish_context)
    lines.append(f"Finishing {finish_context.task_id} from {finish_context.branch_name}")
    lines.extend(bootstrap_result.lines)

    if dry_run and pr_url is None:
        lines.append(
            "Dry run: would wait for checks, merge, and sync main after bootstrapping the branch/PR."
        )
        return (
            ExitCode.OK,
            {
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": None,
                "generated_pr_title": bootstrap_result.generated_title,
                "generated_pr_body": bootstrap_result.generated_body,
                "pushed_branch": bootstrap_result.pushed_branch,
                "created_pr": bootstrap_result.created_pr,
                "dry_run": True,
            },
            lines,
        )
    assert pr_url is not None

    pr_metadata_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "title,body"]
    )
    if pr_metadata_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(pr_metadata_result, "Unable to read the PR title/body."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    try:
        pr_metadata = json.loads(pr_metadata_result.stdout or "{}")
    except json.JSONDecodeError:
        return shared._task_blocked(
            "Unable to parse the PR title/body.",
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            extra_lines=shared._output_lines(pr_metadata_result),
        )
    pr_title = str(pr_metadata.get("title", "")) if isinstance(pr_metadata, dict) else ""
    pr_body = str(pr_metadata.get("body", "")) if isinstance(pr_metadata, dict) else ""

    scope_result = preconditions._run_pr_scope_guard(
        branch_name=finish_context.branch_name,
        pr_title=pr_title,
        pr_body=pr_body,
    )
    if scope_result.returncode != 0:
        return shared._task_blocked(
            "PR scope validation failed.",
            next_action=(
                f"Fix the PR title to `{finish_context.task_id}: short summary` and the PR body so it "
                f"contains exactly `Primary-Task: {finish_context.task_id}`, then re-run `horadus tasks finish`."
            ),
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
            extra_lines=shared._output_lines(scope_result),
        )

    lines.append(f"PR: {pr_url}")

    pr_state_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
    )
    if pr_state_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(pr_state_result, "Unable to determine PR state."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    pr_state = pr_state_result.stdout.strip()

    if pr_state != "MERGED" and not remote_branch_exists:
        return shared._task_blocked(
            f"branch `{finish_context.branch_name}` is not pushed to origin.",
            next_action=f"Run `git push -u origin {finish_context.branch_name}` and re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
        )

    draft_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "isDraft", "--jq", ".isDraft"]
    )
    if draft_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(draft_result, "Unable to determine PR draft status."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if draft_result.stdout.strip() == "true":
        return shared._task_blocked(
            "PR is draft; refusing to merge.",
            next_action="Mark the PR ready for review, then re-run `horadus tasks finish`.",
            data={
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
            },
        )

    if pr_state != "MERGED":
        head_alignment_blocker = preconditions._branch_head_alignment_blocker(
            branch_name=finish_context.branch_name,
            pr_url=pr_url,
            config=config,
        )
        if head_alignment_blocker is not None:
            blocker_message, blocker_data, blocker_lines = head_alignment_blocker
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    f"Checkout `{finish_context.branch_name}`, ensure the intended task-close commits are pushed so "
                    "the local branch, origin branch, and PR head all match, then re-run "
                    "`horadus tasks finish`."
                ),
                data={"task_id": finish_context.task_id, "pr_url": pr_url, **blocker_data},
                extra_lines=blocker_lines,
            )

        closure_blocker = lifecycle._pre_merge_task_closure_blocker(
            finish_context.task_id,
            branch_name=finish_context.branch_name,
            config=config,
        )
        if closure_blocker is not None:
            blocker_message, blocker_data, blocker_lines = closure_blocker
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    f"Run `uv run --no-sync horadus tasks close-ledgers {finish_context.task_id}`, commit and "
                    f"push the ledger/archive updates on `{finish_context.branch_name}`, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": finish_context.task_id,
                    "branch_name": finish_context.branch_name,
                    "pr_url": pr_url,
                    **blocker_data,
                },
                extra_lines=blocker_lines,
            )

    if dry_run:
        lines.append(
            "Dry run: scope and PR preconditions passed; would wait for checks, merge, and sync main."
        )
        return (
            ExitCode.OK,
            {
                "task_id": finish_context.task_id,
                "branch_name": finish_context.branch_name,
                "pr_url": pr_url,
                "pushed_branch": bootstrap_result.pushed_branch,
                "created_pr": bootstrap_result.created_pr,
                "dry_run": True,
            },
            lines,
        )

    if pr_state != "MERGED":
        lines.append(f"Waiting for PR checks to pass (timeout={config.checks_timeout_seconds}s)...")
        checks_ok, check_lines, check_reason = checks._coerce_wait_for_required_checks_result(
            checks._wait_for_required_checks(pr_url=pr_url, config=config)
        )
        if not checks_ok:
            return shared._task_blocked(
                (
                    "required PR checks could not be determined on the current head."
                    if check_reason == "error"
                    else "required PR checks are failing on the current head."
                    if check_reason == "fail"
                    else "required PR checks did not pass before timeout."
                ),
                next_action="Inspect the failing required checks, fix them, and re-run `horadus tasks finish`.",
                data={
                    "task_id": finish_context.task_id,
                    "branch_name": finish_context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=check_lines,
            )
        lines.extend(
            _finish_debug_lines(f"Required checks passed for {pr_url}; reason={check_reason}.")
        )

        review_exit, _review_data, review_lines = review.review_gate_data(
            context=finish_context,
            pr_url=pr_url,
            config=config,
        )
        if review_exit != ExitCode.OK:
            return review_exit, _review_data, review_lines
        lines.extend(review_lines)
        lines.extend(_finish_debug_lines(f"Review gate passed for {pr_url}."))

    merge_exit, merge_data, merge_lines = merge.complete_merge_data(
        context=finish_context,
        pr_url=pr_url,
        pr_state=pr_state,
        config=config,
    )
    if merge_exit != ExitCode.OK:
        return merge_exit, merge_data, merge_lines
    lines.extend(merge_lines)
    return (
        ExitCode.OK,
        {
            "task_id": finish_context.task_id,
            "branch_name": finish_context.branch_name,
            "pr_url": pr_url,
            "merge_commit": merge_data["merge_commit"],
            "lifecycle": merge_data["lifecycle"],
            "dry_run": False,
        },
        lines,
    )


def handle_finish(args: Any) -> CommandResult:
    try:
        normalize_task_id = shared._compat_attr("normalize_task_id", task_repo)
        task_input = normalize_task_id(args.task_id) if args.task_id is not None else None
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = finish_task_data(task_input, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "finish_task_data",
    "handle_finish",
]
