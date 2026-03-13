from __future__ import annotations

import json
import subprocess  # nosec B404
from typing import Any

from tools.horadus.python.horadus_workflow import task_workflow_lifecycle as lifecycle
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import ExitCode

from . import checks, preconditions


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


def _current_head_finish_blocker(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[str, dict[str, object], list[str]] | None:
    head_alignment_blocker = preconditions._branch_head_alignment_blocker(
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

    checks_blocker = checks._current_required_checks_blocker(
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


def review_gate_data(
    *, context: shared.FinishContext, pr_url: str, config: shared.FinishConfig
) -> tuple[int, dict[str, object], list[str]]:
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

    lines = list(refresh_lines)
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
            unresolved_review_lines = _unresolved_review_thread_lines(pr_url=pr_url, config=config)
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
            stale_thread_ids = _outdated_unresolved_review_thread_ids(pr_url=pr_url, config=config)
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

        post_review_blocker = checks._current_required_checks_blocker(
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

    return (ExitCode.OK, {}, lines)


__all__ = [
    "_current_head_finish_blocker",
    "_fresh_review_request_blocker",
    "_head_changed_review_gate_blocker",
    "_maybe_request_fresh_review",
    "_needs_pre_review_fresh_review_request",
    "_outdated_unresolved_review_thread_ids",
    "_parse_review_gate_result",
    "_prepare_current_head_review_window",
    "_resolve_review_threads",
    "_review_gate_lines",
    "_review_thread_lines",
    "_review_threads",
    "_run_review_gate",
    "_unresolved_review_thread_lines",
]
