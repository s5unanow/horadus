from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import time
from typing import Any

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode


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


def _run_pr_scope_guard(
    *, branch_name: str, pr_title: str, pr_body: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PR_BRANCH"] = branch_name
    env["PR_TITLE"] = pr_title
    env["PR_BODY"] = pr_body
    return subprocess.run(  # nosec B603
        ["./scripts/check_pr_task_scope.sh"],
        cwd=shared._compat_attr("repo_root", task_repo)(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_review_gate(
    *, pr_url: str, config: shared.FinishConfig
) -> subprocess.CompletedProcess[str]:
    return shared._run_command_with_timeout(
        [
            config.python_bin,
            "./scripts/check_pr_review_gate.py",
            "--pr-url",
            pr_url,
            "--reviewer-login",
            config.review_bot_login,
            "--timeout-seconds",
            str(config.review_timeout_seconds),
            "--poll-seconds",
            str(config.review_poll_seconds),
            "--timeout-policy",
            config.review_timeout_policy,
            "--format",
            "json",
        ],
        timeout_seconds=(
            config.review_timeout_seconds
            + max(config.review_poll_seconds, 1)
            + shared.DEFAULT_FINISH_REVIEW_GATE_GRACE_SECONDS
        ),
    )


def _parse_review_gate_result(result: subprocess.CompletedProcess[str]) -> shared.ReviewGateResult:
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unable to parse review gate payload: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Unable to parse review gate payload: expected a JSON object.")

    actionable_lines = payload.get("actionable_lines", [])
    if not isinstance(actionable_lines, list) or not all(
        isinstance(line, str) for line in actionable_lines
    ):
        raise ValueError(
            "Unable to parse review gate payload: actionable_lines must be a string list."
        )

    required_str_fields = (
        "status",
        "reason",
        "reviewer_login",
        "reviewed_head_oid",
        "current_head_oid",
        "summary",
    )
    for field_name in required_str_fields:
        if not isinstance(payload.get(field_name), str) or not str(payload[field_name]).strip():
            raise ValueError(f"Unable to parse review gate payload: missing {field_name}.")

    try:
        return shared.ReviewGateResult(
            status=str(payload["status"]).strip(),
            reason=str(payload["reason"]).strip(),
            reviewer_login=str(payload["reviewer_login"]).strip(),
            reviewed_head_oid=str(payload["reviewed_head_oid"]).strip(),
            current_head_oid=str(payload["current_head_oid"]).strip(),
            clean_current_head_review=bool(payload.get("clean_current_head_review")),
            summary_thumbs_up=bool(payload.get("summary_thumbs_up")),
            actionable_comment_count=int(payload.get("actionable_comment_count", 0)),
            actionable_review_count=int(payload.get("actionable_review_count", 0)),
            timeout_seconds=int(payload.get("timeout_seconds", 0)),
            timed_out=bool(payload.get("timed_out")),
            summary=str(payload["summary"]).strip(),
            actionable_lines=[str(line) for line in actionable_lines],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Unable to parse review gate payload: invalid field types.") from exc


def _required_checks_state(*, pr_url: str, config: shared.FinishConfig) -> tuple[str, list[str]]:
    result = shared._run_command(
        [
            config.gh_bin,
            "pr",
            "checks",
            pr_url,
            "--required",
            "--json",
            "bucket,name,link,workflow",
        ]
    )
    lines = shared._output_lines(result)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        if result.returncode == 0:
            return ("error", ["Unable to parse required-check payload from `gh pr checks`."])
        return ("pending", lines)

    if not isinstance(payload, list):
        if result.returncode == 0:
            return ("error", ["Unable to parse required-check payload from `gh pr checks`."])
        return ("pending", lines)

    failed_checks: list[str] = []
    pending_checks: list[str] = []
    saw_checks = False
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        saw_checks = True
        bucket = str(entry.get("bucket") or "").strip().lower()
        name = str(entry.get("name") or "").strip() or "unnamed-check"
        workflow = str(entry.get("workflow") or "").strip()
        label = f"{workflow} / {name}" if workflow and workflow != name else name
        link = str(entry.get("link") or "").strip()
        detail = f"{label}: {bucket}"
        if link:
            detail = f"{detail} ({link})"
        if bucket in {"fail", "cancel"}:
            failed_checks.append(detail)
        elif bucket == "pending":
            pending_checks.append(detail)

    if failed_checks:
        return ("fail", failed_checks)
    if pending_checks:
        return ("pending", pending_checks)
    if result.returncode == 0:
        return ("pass", [])
    if saw_checks:
        return ("pending", lines)
    return ("pending", lines)


def _coerce_wait_for_required_checks_result(
    result: tuple[bool, list[str]] | tuple[bool, list[str], str],
) -> tuple[bool, list[str], str]:
    if len(result) == 2:
        checks_ok, check_lines = result
        return (checks_ok, check_lines, "pass" if checks_ok else "timeout")
    checks_ok, check_lines, reason = result
    return (checks_ok, check_lines, reason)


def _current_required_checks_blocker(
    *, pr_url: str, config: shared.FinishConfig, block_pending: bool = True
) -> tuple[str, list[str]] | None:
    check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
    if check_state == "error":
        return (
            "required PR checks could not be determined on the current head.",
            check_lines,
        )
    if check_state == "fail":
        return (
            "required PR checks are failing on the current head.",
            check_lines,
        )
    if check_state == "pending" and block_pending:
        return (
            "required PR checks are still pending on the current head.",
            check_lines,
        )
    return None


def _branch_head_alignment_blocker(
    *, branch_name: str, pr_url: str, config: shared.FinishConfig
) -> tuple[str, dict[str, object], list[str]] | None:
    local_head_result = shared._run_command([config.git_bin, "rev-parse", branch_name])
    remote_head_result = shared._run_command(
        [config.git_bin, "ls-remote", "--heads", "origin", branch_name]
    )
    pr_head_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "headRefOid", "--jq", ".headRefOid"]
    )

    local_head = local_head_result.stdout.strip() if local_head_result.returncode == 0 else ""
    remote_head = ""
    if remote_head_result.returncode == 0:
        remote_head = remote_head_result.stdout.split(maxsplit=1)[0].strip()
    pr_head = pr_head_result.stdout.strip() if pr_head_result.returncode == 0 else ""

    if local_head and remote_head and pr_head and local_head == remote_head == pr_head:
        return None

    return (
        "task branch head, pushed branch head, and PR head are not aligned.",
        {
            "branch_name": branch_name,
            "local_branch_head": local_head or None,
            "remote_branch_head": remote_head or None,
            "pr_head": pr_head or None,
        },
        [
            f"- local branch head: {local_head or '<missing>'}",
            f"- remote branch head: {remote_head or '<missing>'}",
            f"- PR head: {pr_head or '<missing>'}",
        ],
    )


def _unresolved_review_thread_lines(*, pr_url: str, config: shared.FinishConfig) -> list[str]:
    threads = _review_threads(pr_url=pr_url, config=config)
    return _review_thread_lines(threads, include_outdated=False)


def _review_threads(*, pr_url: str, config: shared.FinishConfig) -> list[dict[str, Any]]:
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    repo_name = repo_result.stdout.strip() if repo_result.returncode == 0 else ""
    if "/" not in repo_name:
        return []
    owner, repo = repo_name.split("/", 1)

    pr_number_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number", "--jq", ".number"]
    )
    pr_number_raw = pr_number_result.stdout.strip() if pr_number_result.returncode == 0 else ""
    if not pr_number_raw.isdigit():
        return []

    query = (
        "query($owner:String!, $repo:String!, $number:Int!, $after:String){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100, after:$after){"
        "pageInfo{hasNextPage endCursor}"
        "nodes{"
        "id isResolved isOutdated "
        "comments(first:20){"
        "pageInfo{hasNextPage}"
        "nodes{author{login} body path line originalLine url}"
        "}"
        "}"
        "}"
        "}"
        "}"
        "}"
    )
    all_threads: list[dict[str, Any]] = []
    after_cursor: str | None = None
    while True:
        args = [
            config.gh_bin,
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number_raw}",
        ]
        if after_cursor is not None:
            args.extend(["-F", f"after={after_cursor}"])
        else:
            args.extend(["-F", "after="])
        threads_result = shared._run_command(args)
        if threads_result.returncode != 0:
            raise ValueError(
                shared._result_message(threads_result, "Unable to load PR review threads.")
            )
        try:
            payload = json.loads(threads_result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Unable to parse PR review threads payload.") from exc

        review_threads = (
            payload.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
        )
        if not isinstance(review_threads, dict):
            raise ValueError("Unexpected PR review threads payload.")
        page_info = review_threads.get("pageInfo")
        nodes = review_threads.get("nodes")
        if not isinstance(page_info, dict) or not isinstance(nodes, list):
            raise ValueError("Unexpected PR review threads payload.")
        for thread in nodes:
            if not isinstance(thread, dict):
                raise ValueError("Unexpected PR review thread entry.")
            comments = thread.get("comments")
            if not isinstance(comments, dict):
                raise ValueError("Unexpected PR review thread comments payload.")
            comment_page_info = comments.get("pageInfo")
            comment_nodes = comments.get("nodes")
            if not isinstance(comment_page_info, dict) or not isinstance(comment_nodes, list):
                raise ValueError("Unexpected PR review thread comments payload.")
            if comment_page_info.get("hasNextPage") is True:
                raise ValueError("PR review thread comments pagination is incomplete.")
            all_threads.append(thread)
        if page_info.get("hasNextPage") is not True:
            break
        end_cursor = page_info.get("endCursor")
        if not isinstance(end_cursor, str) or not end_cursor.strip():
            raise ValueError("PR review thread pagination is incomplete.")
        after_cursor = end_cursor
    return all_threads


def _review_thread_lines(threads: list[dict[str, Any]], *, include_outdated: bool) -> list[str]:
    lines: list[str] = []
    for thread in threads:
        if thread.get("isResolved") is True or (
            not include_outdated and thread.get("isOutdated") is True
        ):
            continue
        comments = thread.get("comments", {}).get("nodes", [])
        if not isinstance(comments, list):
            continue
        comment = next((entry for entry in reversed(comments) if isinstance(entry, dict)), None)
        if comment is None:
            continue
        path = str(comment.get("path") or "<unknown>")
        line = comment.get("line") or comment.get("originalLine") or "?"
        url = str(comment.get("url") or "").strip()
        author = ""
        if isinstance(comment.get("author"), dict):
            author = str(comment["author"].get("login") or "").strip()
        header = f"- {path}:{line}"
        if url:
            header = f"{header} {url}"
        if author:
            header = f"{header} ({author})"
        lines.append(header)
        body = " ".join(str(comment.get("body") or "").strip().split())
        if body:
            lines.append(f"  {body}")
    return lines


def _outdated_unresolved_review_thread_ids(
    *, pr_url: str, config: shared.FinishConfig
) -> list[str]:
    thread_ids: list[str] = []
    for thread in _review_threads(pr_url=pr_url, config=config):
        if thread.get("isResolved") is True or thread.get("isOutdated") is not True:
            continue
        thread_id = str(thread.get("id") or "").strip()
        if thread_id:
            thread_ids.append(thread_id)
    return thread_ids


def _resolve_review_threads(
    *, thread_ids: list[str], config: shared.FinishConfig
) -> tuple[bool, list[str]]:
    if not thread_ids:
        return True, []

    lines: list[str] = []
    for thread_id in thread_ids:
        mutation = (
            "mutation($threadId:ID!){"
            "resolveReviewThread(input:{threadId:$threadId}){"
            "thread{id isResolved}"
            "}"
            "}"
        )
        result = shared._run_command(
            [
                config.gh_bin,
                "api",
                "graphql",
                "-f",
                f"query={mutation}",
                "-F",
                f"threadId={thread_id}",
            ]
        )
        if result.returncode != 0:
            return False, [
                "Failed to resolve outdated review threads automatically.",
                *shared._output_lines(result),
            ]
        lines.append(f"Resolved outdated review thread automatically: {thread_id}")
    return True, lines


def _maybe_request_fresh_review(*, pr_url: str, config: shared.FinishConfig) -> list[str]:
    pr_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number,headRefOid", "--jq", "."]
    )
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if pr_result.returncode != 0 or repo_result.returncode != 0:
        return ["Failed to determine PR metadata for automatic fresh-review request."]
    try:
        pr_payload = json.loads(pr_result.stdout or "{}")
    except json.JSONDecodeError:
        return ["Failed to parse PR metadata for automatic fresh-review request."]
    if not isinstance(pr_payload, dict):
        return ["Failed to parse PR metadata for automatic fresh-review request."]
    pr_number = pr_payload.get("number")
    head_oid = str(pr_payload.get("headRefOid") or "").strip()
    repo_name = repo_result.stdout.strip()
    if not isinstance(pr_number, int) or "/" not in repo_name or not head_oid:
        return ["Failed to determine PR metadata for automatic fresh-review request."]

    marker = f"<!-- horadus:fresh-review reviewer={config.review_bot_login} head={head_oid} -->"
    request_comment = (
        f"@codex review\n{marker}"
        if config.review_bot_login == "chatgpt-codex-connector[bot]"
        else f"@{config.review_bot_login} review\n{marker}"
    )

    comments_result = shared._run_command(
        [
            config.gh_bin,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo_name}/issues/{pr_number}/comments",
        ]
    )
    if comments_result.returncode != 0:
        return ["Failed to inspect existing fresh-review requests automatically."]
    try:
        comments_payload = json.loads(comments_result.stdout or "[]")
    except json.JSONDecodeError:
        return ["Failed to inspect existing fresh-review requests automatically."]
    existing_comments: list[dict[str, Any]] = []
    if isinstance(comments_payload, list):
        if all(isinstance(entry, dict) for entry in comments_payload):
            existing_comments = [entry for entry in comments_payload if isinstance(entry, dict)]
        else:
            for page in comments_payload:
                if not isinstance(page, list):
                    return ["Failed to inspect existing fresh-review requests automatically."]
                for entry in page:
                    if not isinstance(entry, dict):
                        return ["Failed to inspect existing fresh-review requests automatically."]
                    existing_comments.append(entry)
    else:
        return ["Failed to inspect existing fresh-review requests automatically."]

    if any(marker in str(comment.get("body") or "") for comment in existing_comments):
        return [
            f"Fresh review already requested for `{config.review_bot_login}` on current head {head_oid}."
        ]

    result = shared._run_command(
        [config.gh_bin, "pr", "comment", pr_url, "--body", request_comment]
    )
    if result.returncode != 0:
        return [
            f"Failed to request a fresh review from `{config.review_bot_login}` automatically.",
            *shared._output_lines(result),
        ]
    requested_with = (
        "@codex review"
        if config.review_bot_login == "chatgpt-codex-connector[bot]"
        else f"@{config.review_bot_login} review"
    )
    return [
        f"Requested a fresh review from `{config.review_bot_login}` with `{requested_with}` for head {head_oid}."
    ]


def _fresh_review_request_blocker(
    *, pr_url: str, config: shared.FinishConfig
) -> tuple[list[str], tuple[str, dict[str, object], list[str]] | None]:
    request_lines = _maybe_request_fresh_review(pr_url=pr_url, config=config)
    if request_lines and request_lines[0].startswith("Failed"):
        return (
            [],
            (
                "unable to request a fresh current-head review automatically.",
                {},
                request_lines,
            ),
        )
    return (request_lines, None)


def _needs_pre_review_fresh_review_request(*, pr_url: str, config: shared.FinishConfig) -> bool:
    pr_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "number,headRefOid", "--jq", "."]
    )
    repo_result = shared._run_command(
        [config.gh_bin, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )
    if pr_result.returncode != 0 or repo_result.returncode != 0:
        raise ValueError("Unable to determine PR metadata for pre-review refresh state.")
    try:
        pr_payload = json.loads(pr_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse PR metadata for pre-review refresh state.") from exc
    if not isinstance(pr_payload, dict):
        raise ValueError("Unable to parse PR metadata for pre-review refresh state.")
    pr_number = pr_payload.get("number")
    head_oid = str(pr_payload.get("headRefOid") or "").strip()
    repo_name = repo_result.stdout.strip()
    if not isinstance(pr_number, int) or "/" not in repo_name or not head_oid:
        raise ValueError("Unable to determine PR metadata for pre-review refresh state.")

    reviews_result = shared._run_command(
        [
            config.gh_bin,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo_name}/pulls/{pr_number}/reviews",
        ]
    )
    if reviews_result.returncode != 0:
        raise ValueError("Unable to inspect prior reviewer activity for pre-review refresh.")
    try:
        reviews_payload = json.loads(reviews_result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse prior reviewer activity for pre-review refresh.") from exc

    review_entries: list[dict[str, Any]] = []
    if isinstance(reviews_payload, list):
        if all(isinstance(entry, dict) for entry in reviews_payload):
            review_entries = [entry for entry in reviews_payload if isinstance(entry, dict)]
        else:
            for page in reviews_payload:
                if not isinstance(page, list):
                    raise ValueError("Unexpected prior reviewer activity payload.")
                for entry in page:
                    if not isinstance(entry, dict):
                        raise ValueError("Unexpected prior reviewer activity payload.")
                    review_entries.append(entry)
    else:
        raise ValueError("Unexpected prior reviewer activity payload.")

    saw_current_head_review = False
    saw_other_head_review = False
    for review in review_entries:
        user = review.get("user")
        if not isinstance(user, dict):
            continue
        login = str(user.get("login") or "").strip()
        if login != config.review_bot_login:
            continue
        commit_id = str(review.get("commit_id") or "").strip()
        if not commit_id:
            continue
        if commit_id == head_oid:
            saw_current_head_review = True
        else:
            saw_other_head_review = True
    return saw_other_head_review and not saw_current_head_review


def _wait_for_required_checks(
    *, pr_url: str, config: shared.FinishConfig
) -> tuple[bool, list[str], str]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        check_state, check_lines = _required_checks_state(pr_url=pr_url, config=config)
        if check_state == "pass":
            return (True, [], "pass")
        if check_state == "fail":
            return (False, check_lines, "fail")
        if check_state == "error":
            return (False, check_lines, "error")
        if time.time() >= deadline:
            return (
                False,
                check_lines or ["`gh pr checks --required` did not report success before timeout."],
                "timeout",
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _wait_for_pr_state(
    *, pr_url: str, expected_state: str, config: shared.FinishConfig
) -> tuple[bool, list[str]]:
    deadline = time.time() + config.checks_timeout_seconds
    while True:
        result = shared._run_command(
            [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
        )
        if result.returncode == 0 and result.stdout.strip() == expected_state:
            return (True, [])
        if time.time() >= deadline:
            return (
                False,
                shared._output_lines(result)
                or [f"PR did not reach state {expected_state!r} before timeout."],
            )
        if config.checks_poll_seconds:
            time.sleep(config.checks_poll_seconds)


def _current_head_finish_blocker(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[str, dict[str, object], list[str]] | None:
    head_alignment_blocker = _branch_head_alignment_blocker(
        branch_name=context.branch_name,
        pr_url=pr_url,
        config=config,
    )
    if head_alignment_blocker is not None:
        return head_alignment_blocker

    closure_blocker = lifecycle._pre_merge_task_closure_blocker(
        context.task_id,
        branch_name=context.branch_name,
        config=config,
    )
    if closure_blocker is not None:
        return closure_blocker

    checks_blocker = _current_required_checks_blocker(
        pr_url=pr_url,
        config=config,
        block_pending=True,
    )
    if checks_blocker is not None:
        blocker_message, blocker_lines = checks_blocker
        return (blocker_message, {}, blocker_lines)
    return None


def _head_changed_review_gate_blocker(
    *,
    context: shared.FinishContext,
    pr_url: str,
    config: shared.FinishConfig,
    review_lines: list[str],
) -> tuple[int, dict[str, object], list[str]] | None:
    blocker = _current_head_finish_blocker(context=context, pr_url=pr_url, config=config)
    if blocker is None:
        return None
    blocker_message, blocker_data, blocker_lines = blocker
    return shared._task_blocked(
        blocker_message,
        next_action=(
            "Ensure the updated PR head is pushed, task-close state is present on that head, "
            "and current-head required checks are green, then re-run `horadus tasks finish`."
        ),
        data={
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            **blocker_data,
        },
        extra_lines=[*review_lines, *blocker_lines],
    )


def _prepare_current_head_review_window(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[list[str], tuple[str, dict[str, object], list[str]] | None]:
    blocker = _current_head_finish_blocker(context=context, pr_url=pr_url, config=config)
    if blocker is not None:
        return ([], blocker)

    try:
        stale_thread_ids = _outdated_unresolved_review_thread_ids(pr_url=pr_url, config=config)
        needs_fresh_review_request = bool(stale_thread_ids)
        if not needs_fresh_review_request:
            needs_fresh_review_request = _needs_pre_review_fresh_review_request(
                pr_url=pr_url,
                config=config,
            )
    except ValueError as exc:
        return (
            [],
            (
                "unable to determine outdated review thread state on the current head.",
                {},
                [str(exc)],
            ),
        )

    if not needs_fresh_review_request:
        return ([], None)

    review_refresh_lines: list[str] = []
    if stale_thread_ids:
        resolved_ok, stale_thread_lines = _resolve_review_threads(
            thread_ids=stale_thread_ids,
            config=config,
        )
        if not resolved_ok:
            return (
                [],
                (
                    "PR still has outdated unresolved review threads that could not be auto-resolved.",
                    {},
                    stale_thread_lines,
                ),
            )
        review_refresh_lines.extend(stale_thread_lines)
    request_lines, request_blocker = _fresh_review_request_blocker(
        pr_url=pr_url,
        config=config,
    )
    if request_blocker is not None:
        return ([], request_blocker)
    review_refresh_lines.extend(request_lines)
    if stale_thread_ids:
        review_refresh_lines.append(
            "Refreshed stale review state for the current head; discarding the previous "
            f"review window and starting a fresh {config.review_timeout_seconds}s review window."
        )
    else:
        review_refresh_lines.append(
            "Detected reviewer activity on an older head; discarding the previous "
            f"review window and starting a fresh {config.review_timeout_seconds}s review window."
        )
    return (review_refresh_lines, None)


def _review_gate_lines(review_result: shared.ReviewGateResult) -> list[str]:
    return [review_result.summary, *review_result.actionable_lines]


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

    context = _resolve_finish_context(task_input, config)
    if not isinstance(context, shared.FinishContext):
        return context

    remote_branch_result = shared._run_command(
        [config.git_bin, "ls-remote", "--exit-code", "--heads", "origin", context.branch_name]
    )
    remote_branch_exists = remote_branch_result.returncode == 0

    pr_url_result = shared._run_command(
        [config.gh_bin, "pr", "view", context.branch_name, "--json", "url", "--jq", ".url"]
    )
    pr_url = pr_url_result.stdout.strip()
    if pr_url_result.returncode != 0 or not pr_url:
        if not remote_branch_exists and not dry_run:
            docker_readiness = shared.ensure_docker_ready(
                reason="the next required `git push` pre-push integration gate"
            )
            if not docker_readiness.ready:
                return shared._task_blocked(
                    "Docker is not ready for the next required push gate.",
                    next_action=(
                        f"Make Docker ready, then run `git push -u origin {context.branch_name}` "
                        f"and re-run `horadus tasks finish {context.task_id}`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "docker_ready": False,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=docker_readiness.lines,
                )
        next_action = (
            f"Run `git push -u origin {context.branch_name}` and open a PR for {context.task_id}."
            if not remote_branch_exists
            else (
                f"Open a PR for `{context.branch_name}` titled `{context.task_id}: short summary` "
                f"with `Primary-Task: {context.task_id}` in the body, then re-run `horadus tasks finish`."
            )
        )
        return shared._task_blocked(
            f"unable to locate a PR for branch `{context.branch_name}`.",
            next_action=next_action,
            data={"task_id": context.task_id, "branch_name": context.branch_name},
        )

    pr_metadata_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "title,body"]
    )
    if pr_metadata_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(pr_metadata_result, "Unable to read the PR title/body."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    try:
        pr_metadata = json.loads(pr_metadata_result.stdout or "{}")
    except json.JSONDecodeError:
        return shared._task_blocked(
            "Unable to parse the PR title/body.",
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            extra_lines=shared._output_lines(pr_metadata_result),
        )
    pr_title = str(pr_metadata.get("title", "")) if isinstance(pr_metadata, dict) else ""
    pr_body = str(pr_metadata.get("body", "")) if isinstance(pr_metadata, dict) else ""

    scope_result = _run_pr_scope_guard(
        branch_name=context.branch_name,
        pr_title=pr_title,
        pr_body=pr_body,
    )
    if scope_result.returncode != 0:
        return shared._task_blocked(
            "PR scope validation failed.",
            next_action=(
                f"Fix the PR title to `{context.task_id}: short summary` and the PR body so it "
                f"contains exactly `Primary-Task: {context.task_id}`, then re-run `horadus tasks finish`."
            ),
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            extra_lines=shared._output_lines(scope_result),
        )

    lines: list[str] = []
    if context.current_branch is not None and context.current_branch != context.branch_name:
        lines.append(
            f"Resuming {context.task_id} from {context.current_branch} using task branch {context.branch_name}."
        )
    lines.extend([f"Finishing {context.task_id} from {context.branch_name}", f"PR: {pr_url}"])

    pr_state_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
    )
    if pr_state_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(pr_state_result, "Unable to determine PR state."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    pr_state = pr_state_result.stdout.strip()

    if pr_state != "MERGED" and not remote_branch_exists:
        return shared._task_blocked(
            f"branch `{context.branch_name}` is not pushed to origin.",
            next_action=f"Run `git push -u origin {context.branch_name}` and re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    draft_result = shared._run_command(
        [config.gh_bin, "pr", "view", pr_url, "--json", "isDraft", "--jq", ".isDraft"]
    )
    if draft_result.returncode != 0:
        return shared._task_blocked(
            shared._result_message(draft_result, "Unable to determine PR draft status."),
            next_action="Resolve the GitHub CLI error, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
            exit_code=ExitCode.ENVIRONMENT_ERROR,
        )
    if draft_result.stdout.strip() == "true":
        return shared._task_blocked(
            "PR is draft; refusing to merge.",
            next_action="Mark the PR ready for review, then re-run `horadus tasks finish`.",
            data={"task_id": context.task_id, "branch_name": context.branch_name, "pr_url": pr_url},
        )

    if pr_state != "MERGED":
        head_alignment_blocker = _branch_head_alignment_blocker(
            branch_name=context.branch_name,
            pr_url=pr_url,
            config=config,
        )
        if head_alignment_blocker is not None:
            blocker_message, blocker_data, blocker_lines = head_alignment_blocker
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    f"Checkout `{context.branch_name}`, ensure the intended task-close commits are pushed so "
                    "the local branch, origin branch, and PR head all match, then re-run "
                    "`horadus tasks finish`."
                ),
                data={"task_id": context.task_id, "pr_url": pr_url, **blocker_data},
                extra_lines=blocker_lines,
            )

        closure_blocker = lifecycle._pre_merge_task_closure_blocker(
            context.task_id,
            branch_name=context.branch_name,
            config=config,
        )
        if closure_blocker is not None:
            blocker_message, blocker_data, blocker_lines = closure_blocker
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    f"Run `uv run --no-sync horadus tasks close-ledgers {context.task_id}`, commit and "
                    f"push the ledger/archive updates on `{context.branch_name}`, then re-run "
                    "`horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
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
                "task_id": context.task_id,
                "branch_name": context.branch_name,
                "pr_url": pr_url,
                "dry_run": True,
            },
            lines,
        )

    if pr_state == "MERGED":
        lines.append("PR already merged; skipping merge step.")
    else:
        lines.append(f"Waiting for PR checks to pass (timeout={config.checks_timeout_seconds}s)...")
        checks_ok, check_lines, check_reason = _coerce_wait_for_required_checks_result(
            _wait_for_required_checks(pr_url=pr_url, config=config)
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
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                },
                extra_lines=check_lines,
            )

        refresh_lines, refresh_blocker = _prepare_current_head_review_window(
            context=context,
            pr_url=pr_url,
            config=config,
        )
        if refresh_blocker is not None:
            blocker_message, blocker_data, blocker_lines = refresh_blocker
            blocker_exit_code = (
                ExitCode.ENVIRONMENT_ERROR
                if blocker_message.startswith(
                    (
                        "unable to determine outdated",
                        "unable to request a fresh current-head review",
                        "PR still has outdated unresolved review threads",
                    )
                )
                else ExitCode.VALIDATION_ERROR
            )
            return shared._task_blocked(
                blocker_message,
                next_action=(
                    "Ensure the current PR head is merge-ready and GitHub review state is readable, "
                    "then re-run `horadus tasks finish`."
                ),
                data={
                    "task_id": context.task_id,
                    "branch_name": context.branch_name,
                    "pr_url": pr_url,
                    **blocker_data,
                },
                exit_code=blocker_exit_code,
                extra_lines=blocker_lines,
            )
        lines.extend(refresh_lines)

        while True:
            lines.append(
                "Waiting for review gate "
                f"(reviewer={config.review_bot_login}, timeout={config.review_timeout_seconds}s)..."
            )
            try:
                review_result = _run_review_gate(pr_url=pr_url, config=config)
            except shared.CommandTimeoutError as exc:
                return shared._task_blocked(
                    "review gate command did not exit after the configured wait window.",
                    next_action=(
                        "Inspect GitHub/Codex review delivery and re-run `horadus tasks finish` "
                        "if the review gate keeps hanging."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[str(exc), *exc.output_lines()],
                )

            try:
                review_gate = _parse_review_gate_result(review_result)
            except ValueError as exc:
                return shared._task_blocked(
                    "review gate returned an unreadable result.",
                    next_action="Resolve the review gate script failure, then re-run `horadus tasks finish`.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[str(exc), *shared._output_lines(review_result)],
                )
            review_lines = _review_gate_lines(review_gate)

            if review_gate.status == "head_changed":
                blocker = _head_changed_review_gate_blocker(
                    context=context,
                    pr_url=pr_url,
                    config=config,
                    review_lines=review_lines,
                )
                if blocker is not None:
                    return blocker
                lines.extend(review_lines)
                request_lines, request_blocker = _fresh_review_request_blocker(
                    pr_url=pr_url,
                    config=config,
                )
                if request_blocker is not None:
                    blocker_message, blocker_data, blocker_lines = request_blocker
                    return shared._task_blocked(
                        blocker_message,
                        next_action=(
                            "Fix the fresh-review request failure for the current PR head, then "
                            "re-run `horadus tasks finish`."
                        ),
                        data={
                            "task_id": context.task_id,
                            "branch_name": context.branch_name,
                            "pr_url": pr_url,
                            **blocker_data,
                        },
                        exit_code=ExitCode.ENVIRONMENT_ERROR,
                        extra_lines=[*review_lines, *blocker_lines],
                    )
                lines.extend(request_lines)
                continue

            if review_gate.status == "block":
                return shared._task_blocked(
                    (
                        "review gate timed out before the required current-head review arrived."
                        if review_gate.reason == "timeout_fail"
                        else "review gate did not pass."
                    ),
                    next_action=(
                        f"Wait for a current-head review from `{config.review_bot_login}`, then "
                        "re-run `horadus tasks finish`."
                        if review_gate.reason == "timeout_fail"
                        else "Address the current-head review feedback, then re-run "
                        "`horadus tasks finish`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=review_result.returncode,
                    extra_lines=review_lines,
                )

            lines.extend(review_lines)

            try:
                unresolved_review_lines = _unresolved_review_thread_lines(
                    pr_url=pr_url, config=config
                )
            except ValueError as exc:
                return shared._task_blocked(
                    "unable to determine unresolved review thread state on the current head.",
                    next_action="Resolve the GitHub review-thread query issue, then re-run `horadus tasks finish`.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[*review_lines, str(exc)],
                )
            if unresolved_review_lines:
                extra_lines = [*review_lines, *unresolved_review_lines]
                if review_gate.timed_out:
                    extra_lines.extend(_maybe_request_fresh_review(pr_url=pr_url, config=config))
                return shared._task_blocked(
                    "PR is blocked by unresolved review comments.",
                    next_action=(
                        "Resolve the unresolved review threads in GitHub and wait for a fresh "
                        "current-head review, then re-run `horadus tasks finish`."
                        if review_gate.timed_out
                        else "Resolve the unresolved review threads in GitHub, then re-run "
                        "`horadus tasks finish`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    extra_lines=extra_lines,
                )

            try:
                stale_thread_ids = _outdated_unresolved_review_thread_ids(
                    pr_url=pr_url, config=config
                )
            except ValueError as exc:
                return shared._task_blocked(
                    "unable to determine outdated review thread state on the current head.",
                    next_action="Resolve the GitHub review-thread query issue, then re-run `horadus tasks finish`.",
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    exit_code=ExitCode.ENVIRONMENT_ERROR,
                    extra_lines=[*review_lines, str(exc)],
                )
            if stale_thread_ids:
                resolved_ok, stale_thread_lines = _resolve_review_threads(
                    thread_ids=stale_thread_ids,
                    config=config,
                )
                if not resolved_ok:
                    return shared._task_blocked(
                        "PR still has outdated unresolved review threads that could not be auto-resolved.",
                        next_action="Re-run `horadus tasks finish`; if the stale-thread blocker persists, inspect GitHub thread state.",
                        data={
                            "task_id": context.task_id,
                            "branch_name": context.branch_name,
                            "pr_url": pr_url,
                        },
                        exit_code=ExitCode.ENVIRONMENT_ERROR,
                        extra_lines=[*review_lines, *stale_thread_lines],
                    )
                lines.extend(stale_thread_lines)

            post_review_blocker = _current_required_checks_blocker(
                pr_url=pr_url,
                config=config,
                block_pending=True,
            )
            if post_review_blocker is not None:
                blocker_message, blocker_lines = post_review_blocker
                return shared._task_blocked(
                    blocker_message,
                    next_action=(
                        "Ensure the current PR head still has green required checks, then re-run "
                        "`horadus tasks finish`."
                    ),
                    data={
                        "task_id": context.task_id,
                        "branch_name": context.branch_name,
                        "pr_url": pr_url,
                    },
                    extra_lines=[*review_lines, *blocker_lines],
                )
            break

        lines.append("Merging PR (squash, delete branch)...")
        try:
            merge_result = shared._run_command_with_timeout(
                [config.gh_bin, "pr", "merge", pr_url, "--squash", "--delete-branch"],
                timeout_seconds=shared.DEFAULT_FINISH_MERGE_COMMAND_TIMEOUT_SECONDS,
            )
        except shared.CommandTimeoutError as exc:
            state_after_result = shared._run_command(
                [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
            )
            state_after = (
                state_after_result.stdout.strip() if state_after_result.returncode == 0 else ""
            )
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
            state_after_result = shared._run_command(
                [config.gh_bin, "pr", "view", pr_url, "--json", "state", "--jq", ".state"]
            )
            state_after = (
                state_after_result.stdout.strip() if state_after_result.returncode == 0 else ""
            )
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
                        auto_state_after_result = shared._run_command(
                            [
                                config.gh_bin,
                                "pr",
                                "view",
                                pr_url,
                                "--json",
                                "state",
                                "--jq",
                                ".state",
                            ]
                        )
                        auto_state_after = (
                            auto_state_after_result.stdout.strip()
                            if auto_state_after_result.returncode == 0
                            else ""
                        )
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
                        auto_state_after_result = shared._run_command(
                            [
                                config.gh_bin,
                                "pr",
                                "view",
                                pr_url,
                                "--json",
                                "state",
                                "--jq",
                                ".state",
                            ]
                        )
                        auto_state_after = (
                            auto_state_after_result.stdout.strip()
                            if auto_state_after_result.returncode == 0
                            else ""
                        )
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
                    merged_ok, merged_lines = _wait_for_pr_state(
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
            "task_id": context.task_id,
            "branch_name": context.branch_name,
            "pr_url": pr_url,
            "merge_commit": merge_commit,
            "lifecycle": lifecycle_data_result,
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
    "_branch_head_alignment_blocker",
    "_coerce_wait_for_required_checks_result",
    "_current_head_finish_blocker",
    "_current_required_checks_blocker",
    "_fresh_review_request_blocker",
    "_head_changed_review_gate_blocker",
    "_maybe_request_fresh_review",
    "_needs_pre_review_fresh_review_request",
    "_outdated_unresolved_review_thread_ids",
    "_parse_review_gate_result",
    "_prepare_current_head_review_window",
    "_required_checks_state",
    "_resolve_finish_context",
    "_resolve_review_threads",
    "_review_gate_lines",
    "_review_thread_lines",
    "_review_threads",
    "_run_pr_scope_guard",
    "_run_review_gate",
    "_unresolved_review_thread_lines",
    "_wait_for_pr_state",
    "_wait_for_required_checks",
    "finish_task_data",
    "handle_finish",
]
