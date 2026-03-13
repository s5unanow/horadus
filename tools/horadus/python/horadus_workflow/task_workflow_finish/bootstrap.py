from __future__ import annotations

import json
import re
from dataclasses import dataclass

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import preconditions


@dataclass(slots=True)
class BranchPullRequest:
    number: int
    url: str
    head_ref_name: str


@dataclass(slots=True)
class FinishPullRequestBootstrap:
    pr_url: str | None
    remote_branch_exists: bool
    pushed_branch: bool
    created_pr: bool
    lines: list[str]
    generated_title: str | None = None
    generated_body: str | None = None


def _humanize_branch_summary(branch_name: str) -> str:
    match = shared.TASK_BRANCH_PATTERN.match(branch_name)
    if match is None:
        return "short summary"
    suffix = branch_name.split("-", maxsplit=3)[-1].strip()
    summary = re.sub(r"[-_.]+", " ", suffix).strip()
    return summary or "short summary"


def _resolve_finish_pr_title(*, task_id: str, branch_name: str) -> str:
    summary: str | None = None
    live_record = task_repo.task_record(task_id)
    if live_record is not None:
        summary = live_record.title.strip()
    if not summary:
        archived_record = task_repo.task_record(task_id, include_archive=True)
        if archived_record is not None:
            summary = archived_record.title.strip()
    if not summary:
        closed_record = task_repo.closed_task_archive_record(task_id)
        if closed_record is not None:
            summary = closed_record.title.strip()
    if not summary:
        summary = _humanize_branch_summary(branch_name)
    return f"{task_id}: {summary}"


def _resolve_finish_pr_body(*, task_id: str) -> str:
    return f"Primary-Task: {task_id}\n"


def _find_open_branch_pull_request(
    *,
    branch_name: str,
    config: shared.FinishConfig,
) -> tuple[int, dict[str, object], list[str]] | BranchPullRequest | None:
    result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "list",
            "--state",
            "open",
            "--head",
            branch_name,
            "--json",
            "number,url,headRefName",
        ]
    )
    if result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(result, "Unable to query GitHub pull requests."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"branch_name": branch_name},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return shared._task_blocked(
            "Unable to parse GitHub pull request search results.",
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"branch_name": branch_name},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            extra_lines=shared._output_lines(result),
        )
    if not isinstance(payload, list):
        return shared._task_blocked(
            "Unable to parse GitHub pull request search results.",
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"branch_name": branch_name},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )

    matches = [
        BranchPullRequest(
            number=int(entry.get("number", 0)),
            url=str(entry.get("url") or ""),
            head_ref_name=str(entry.get("headRefName") or ""),
        )
        for entry in payload
        if isinstance(entry, dict)
        and str(entry.get("headRefName") or "") == branch_name
        and str(entry.get("url") or "").strip()
    ]
    if not matches:
        return None
    if len(matches) > 1:
        return shared._task_blocked(
            f"multiple open pull requests match branch `{branch_name}`.",
            next_action=(
                f"Close or consolidate the duplicate PRs for `{branch_name}`, then re-run "
                "`horadus tasks finish`."
            ),
            data={
                "branch_name": branch_name,
                "matching_pull_requests": [
                    {"number": match.number, "url": match.url} for match in matches
                ],
            },
            extra_lines=[
                f"- PR #{match.number}: {match.url}"
                for match in sorted(matches, key=lambda value: value.number)
            ],
        )
    return matches[0]


def _generated_pr_scope_blocker(
    *,
    task_id: str,
    branch_name: str,
    pr_title: str,
    pr_body: str,
) -> tuple[int, dict[str, object], list[str]] | None:
    scope_result = preconditions._run_pr_scope_guard(
        branch_name=branch_name,
        pr_title=pr_title,
        pr_body=pr_body,
    )
    if scope_result.returncode == 0:
        return None
    return shared._task_blocked(
        "generated PR metadata failed scope validation.",
        next_action="Resolve the finish PR metadata generation issue, then re-run `horadus tasks finish`.",
        data={
            "task_id": task_id,
            "branch_name": branch_name,
            "generated_pr_title": pr_title,
            "generated_pr_body": pr_body,
        },
        exit_code=ExitCode.ENVIRONMENT_ERROR,
        extra_lines=shared._output_lines(scope_result),
    )


def _ensure_finish_pull_request(
    *,
    context: shared.FinishContext,
    config: shared.FinishConfig,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]] | FinishPullRequestBootstrap:
    remote_branch_result = shared._run_command(
        [
            config.git_bin,
            "ls-remote",
            "--exit-code",
            "--heads",
            "origin",
            context.branch_name,
        ]
    )
    remote_branch_exists = remote_branch_result.returncode == 0

    branch_pr = _find_open_branch_pull_request(branch_name=context.branch_name, config=config)
    if isinstance(branch_pr, tuple):
        return branch_pr
    if isinstance(branch_pr, BranchPullRequest):
        return FinishPullRequestBootstrap(
            pr_url=branch_pr.url,
            remote_branch_exists=remote_branch_exists,
            pushed_branch=False,
            created_pr=False,
            lines=[],
        )

    pr_title = _resolve_finish_pr_title(task_id=context.task_id, branch_name=context.branch_name)
    pr_body = _resolve_finish_pr_body(task_id=context.task_id)
    scope_blocker = _generated_pr_scope_blocker(
        task_id=context.task_id,
        branch_name=context.branch_name,
        pr_title=pr_title,
        pr_body=pr_body,
    )
    if scope_blocker is not None:
        return scope_blocker

    dry_run_lines: list[str] = []
    if dry_run:
        if not remote_branch_exists:
            dry_run_lines.append(f"Dry run: would push `{context.branch_name}` to `origin`.")
        dry_run_lines.append(f"Dry run: would create PR `{pr_title}` for `{context.branch_name}`.")
        return FinishPullRequestBootstrap(
            pr_url=None,
            remote_branch_exists=remote_branch_exists,
            pushed_branch=False,
            created_pr=False,
            lines=dry_run_lines,
            generated_title=pr_title,
            generated_body=pr_body,
        )

    lines: list[str] = []
    pushed_branch = False
    created_pr = False

    if not remote_branch_exists:
        docker_readiness = shared.ensure_docker_ready(
            reason="the next required `git push` pre-push integration gate"
        )
        if not docker_readiness.ready:
            return shared._task_blocked(
                "Docker is not ready for the next required push gate.",
                next_action=(
                    f"Make Docker ready, then re-run `horadus tasks finish {context.task_id}`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "docker_ready": False,
                },
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=docker_readiness.lines,
            )
        lines.append(f"Pushing branch `{context.branch_name}` to `origin`...")
        push_result = shared._run_command(
            [config.git_bin, "push", "-u", "origin", context.branch_name]
        )
        if push_result.returncode != 0:
            return shared._task_blocked(
                f"unable to push branch `{context.branch_name}` to origin.",
                next_action="Resolve the push failure, then re-run `horadus tasks finish`.",
                data={"task_id": context.task_id, "branch_name": context.branch_name},
                exit_code=ExitCode.ENVIRONMENT_ERROR,
                extra_lines=shared._output_lines(push_result),
            )
        remote_branch_exists = True
        pushed_branch = True

    lines.append(f"Creating canonical PR for `{context.branch_name}`...")
    create_result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            context.branch_name,
            "--title",
            pr_title,
            "--body",
            pr_body,
        ]
    )
    branch_pr = _find_open_branch_pull_request(branch_name=context.branch_name, config=config)
    if isinstance(branch_pr, tuple):
        return branch_pr
    if isinstance(branch_pr, BranchPullRequest):
        if create_result.returncode != 0:
            lines.append(
                "PR already exists after create attempt; continuing with the discovered branch PR."
            )
        else:
            created_pr = True
        return FinishPullRequestBootstrap(
            pr_url=branch_pr.url,
            remote_branch_exists=remote_branch_exists,
            pushed_branch=pushed_branch,
            created_pr=created_pr,
            lines=lines,
            generated_title=pr_title,
            generated_body=pr_body,
        )

    blocker_message = (
        f"unable to create a PR for branch `{context.branch_name}`."
        if create_result.returncode != 0
        else f"created PR for `{context.branch_name}` could not be re-queried."
    )
    return shared._task_blocked(
        blocker_message,
        next_action="Resolve the branch/PR state in GitHub, then re-run `horadus tasks finish`.",
        data={
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "generated_pr_title": pr_title,
            "generated_pr_body": pr_body,
        },
        exit_code=ExitCode.ENVIRONMENT_ERROR,
        extra_lines=shared._output_lines(create_result),
    )


__all__ = [
    "BranchPullRequest",
    "FinishPullRequestBootstrap",
    "_ensure_finish_pull_request",
    "_find_open_branch_pull_request",
    "_resolve_finish_pr_body",
    "_resolve_finish_pr_title",
]
