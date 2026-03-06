from __future__ import annotations

import shutil
import subprocess  # nosec B404
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.horadus_cli.result import CommandResult, ExitCode
from src.horadus_cli.task_repo import (
    active_section_text,
    backlog_path,
    current_sprint_path,
    normalize_task_id,
    parse_active_tasks,
    parse_human_blockers,
    repo_root,
    search_task_records,
    slugify_name,
    task_record,
)


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        args,
        cwd=cwd or repo_root(),
        capture_output=True,
        text=True,
        check=check,
    )


def _run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        ["/bin/bash", "-lc", command],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _ensure_required_hooks() -> tuple[bool, list[str]]:
    hooks_dir = repo_root() / ".git" / "hooks"
    required = ("pre-commit", "pre-push", "commit-msg")
    missing: list[str] = []
    for hook_name in required:
        hook_path = hooks_dir / hook_name
        if (
            not hook_path.exists()
            or not hook_path.is_file()
            or not hook_path.stat().st_mode & 0o111
        ):
            missing.append(hook_name)
    return (not missing, missing)


def _open_task_prs() -> tuple[bool, list[str] | str]:
    result = _run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            "main",
            "--author",
            "@me",
            "--search",
            "head:codex/task-",
            "--limit",
            "100",
            "--json",
            "number,headRefName,url",
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        return (False, message)
    import json

    payload = json.loads(result.stdout or "[]")
    open_prs = [
        f"#{entry['number']} {entry['headRefName']} {entry['url']}"
        for entry in payload
        if str(entry.get("headRefName", "")).startswith("codex/task-")
    ]
    return (True, open_prs)


def task_preflight_data() -> tuple[int, dict[str, Any], list[str]]:
    if getenv("SKIP_TASK_SEQUENCE_GUARD") == "1":
        data = {"skipped": True}
        return (ExitCode.OK, data, ["Task sequencing guard skipped (SKIP_TASK_SEQUENCE_GUARD=1)."])

    gh_path = shutil.which("gh")
    if gh_path is None:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_command": "gh"},
            ["Task sequencing guard failed.", "GitHub CLI (gh) is required for open-PR checks."],
        )

    hooks_ok, missing_hooks = _ensure_required_hooks()
    if not hooks_ok:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"missing_hooks": missing_hooks},
            [
                "Task sequencing guard failed.",
                f"Required local git hooks are missing: {', '.join(missing_hooks)}.",
            ],
        )

    branch_result = _run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
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

    status_result = _run_command(["git", "status", "--porcelain"])
    if status_result.stdout.strip():
        return (
            ExitCode.VALIDATION_ERROR,
            {"working_tree_clean": False},
            [
                "Task sequencing guard failed.",
                "Working tree must be clean before starting a new task branch.",
            ],
        )

    fetch_result = _run_command(["git", "fetch", "origin", "main", "--quiet"])
    if fetch_result.returncode != 0:
        message = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch failed"
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"fetch_error": message},
            ["Task sequencing guard failed.", message],
        )

    local_sha = _run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = _run_command(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        return (
            ExitCode.VALIDATION_ERROR,
            {"local_main_sha": local_sha, "remote_main_sha": remote_sha},
            ["Task sequencing guard failed.", "Local main is not synced to origin/main."],
        )

    if getenv("ALLOW_OPEN_TASK_PRS") != "1":
        ok, pr_result = _open_task_prs()
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

    return (
        ExitCode.OK,
        {
            "gh_path": gh_path,
            "working_tree_clean": True,
            "local_main_sha": local_sha,
            "remote_main_sha": remote_sha,
        },
        ["Task sequencing guard passed: main is clean/synced and no open task PRs."],
    )


def getenv(name: str) -> str | None:
    import os

    return os.environ.get(name)


def _preflight_result() -> CommandResult:
    exit_code, data, lines = task_preflight_data()
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def eligibility_data(task_input: str) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    sprint_file = Path(getenv("TASK_ELIGIBILITY_SPRINT_FILE") or current_sprint_path())
    if not sprint_file.exists():
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"sprint_file": str(sprint_file)},
            [f"Missing sprint file: {sprint_file}"],
        )

    try:
        _ = active_section_text(sprint_file)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {"sprint_file": str(sprint_file)}, [str(exc)])

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

    preflight_override = getenv("TASK_ELIGIBILITY_PREFLIGHT_CMD")
    if preflight_override and preflight_override != "./scripts/check_task_start_preflight.sh":
        preflight_result = _run_shell(preflight_override)
        if preflight_result.returncode != 0:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "preflight_cmd": preflight_override},
                [f"Task sequencing preflight failed for {task_id}."],
            )
    else:
        preflight_exit, preflight_data, preflight_lines = task_preflight_data()
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


def start_task_data(
    task_input: str, raw_name: str, *, dry_run: bool
) -> tuple[int, dict[str, Any], list[str]]:
    task_id = normalize_task_id(task_input)
    slug = slugify_name(raw_name)
    branch_name = f"codex/task-{task_id[5:]}-{slug}"

    preflight_exit, preflight_data, preflight_lines = task_preflight_data()
    if preflight_exit != ExitCode.OK:
        return (
            preflight_exit,
            {"branch_name": branch_name, "preflight": preflight_data},
            preflight_lines,
        )

    local_exists = (
        _run_command(
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
        _run_command(
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

    lines = ["Task sequencing guard passed: main is clean/synced and no open task PRs."]
    if dry_run:
        lines.append(f"Dry run: would create task branch {branch_name}")
        return (
            ExitCode.OK,
            {"task_id": task_id, "branch_name": branch_name, "dry_run": True},
            lines,
        )

    switch_result = _run_command(["git", "switch", "-c", branch_name])
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


def _task_record_payload(record: Any, *, include_raw: bool = True) -> dict[str, Any]:
    payload = asdict(record)
    if not include_raw:
        payload.pop("raw_block", None)
    payload["backlog_path"] = str(backlog_path().relative_to(repo_root()))
    payload["current_sprint_path"] = str(current_sprint_path().relative_to(repo_root()))
    return payload


def handle_list_active(_args: Any) -> CommandResult:
    tasks = parse_active_tasks()
    blockers = parse_human_blockers()
    blockers_by_task = {blocker.task_id: blocker for blocker in blockers}
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]
    lines = ["Active tasks:"]
    for task in tasks:
        suffix = " [REQUIRES_HUMAN]" if task.requires_human else ""
        note = f" — {task.note}" if task.note else ""
        urgency_note = ""
        blocker = blockers_by_task.get(task.task_id)
        if blocker is not None and blocker.urgency is not None:
            if blocker.urgency.is_overdue:
                overdue_days = abs(blocker.urgency.days_until_next_action or 0)
                urgency_note = f" [OVERDUE by {overdue_days}d]"
            elif blocker.urgency.is_due_today:
                urgency_note = " [DUE TODAY]"
        lines.append(f"- {task.task_id}: {task.title}{suffix}{urgency_note}{note}")
    if overdue_blockers:
        lines.append(
            "- overdue_human_blockers="
            f"{len(overdue_blockers)} ({', '.join(blocker.task_id for blocker in overdue_blockers)})"
        )
    return CommandResult(
        lines=lines,
        data={
            "tasks": [asdict(task) for task in tasks],
            "human_blockers": [asdict(item) for item in blockers],
            "overdue_human_blockers": [asdict(item) for item in overdue_blockers],
        },
    )


def handle_show(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    record = task_record(task_id)
    if record is None:
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# {record.task_id}: {record.title}",
        f"Status: {record.status}",
        f"Priority: {record.priority or 'unknown'}",
        f"Estimate: {record.estimate or 'unknown'}",
    ]
    if record.description:
        lines.append("Description:")
        lines.extend(f"- {item}" for item in record.description)
    if record.files:
        lines.append("Files:")
        lines.extend(f"- {item}" for item in record.files)
    if record.acceptance_criteria:
        lines.append("Acceptance Criteria:")
        lines.extend(record.acceptance_criteria)
    if record.spec_paths:
        lines.append("Specs:")
        lines.extend(f"- {item}" for item in record.spec_paths)
    return CommandResult(lines=lines, data=_task_record_payload(record))


def handle_search(args: Any) -> CommandResult:
    if args.limit is not None and args.limit < 1:
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=["--limit must be a positive integer"],
        )

    query = " ".join(args.query).strip()
    matches = search_task_records(query, status=args.status, limit=args.limit)
    lines = [f"Task search: {query}"]
    lines.append(
        f"- status={args.status}, limit={args.limit if args.limit is not None else 'none'}, "
        f"results={len(matches)}"
    )
    if not matches:
        lines.append("(no matches)")
    else:
        for record in matches:
            lines.append(
                f"- {record.task_id}: {record.title} [{record.status}] "
                f"(priority={record.priority or 'unknown'}, estimate={record.estimate or 'unknown'})"
            )
        if args.include_raw:
            for record in matches:
                lines.extend(["", f"## {record.task_id}", record.raw_block])
    return CommandResult(
        lines=lines,
        data={
            "query": query,
            "status_filter": args.status,
            "limit": args.limit,
            "include_raw": bool(args.include_raw),
            "matches": [
                _task_record_payload(item, include_raw=bool(args.include_raw)) for item in matches
            ],
        },
    )


def handle_context_pack(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    record = task_record(task_id)
    if record is None:
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# Context Pack: {task_id}",
        "",
        "## Backlog Entry",
        record.raw_block,
        "",
        "## Sprint Status",
    ]
    lines.extend(record.sprint_lines or ["(not listed in current sprint)"])
    lines.extend(
        [
            "",
            "## Matching Spec",
        ]
    )
    lines.extend(record.spec_paths or ["(none)"])
    lines.extend(
        [
            "",
            "## Likely Code Areas",
        ]
    )
    lines.extend(record.files or ["(not specified in backlog entry)"])
    lines.extend(
        [
            "",
            "## Suggested Validation Commands",
            "make agent-check",
            "make docs-freshness",
            "uv run --no-sync pytest tests/unit/ -v -m unit",
        ]
    )
    return CommandResult(
        lines=lines,
        data={
            "task": _task_record_payload(record),
            "sprint_lines": record.sprint_lines,
            "spec_paths": record.spec_paths,
            "suggested_validation_commands": [
                "make agent-check",
                "make docs-freshness",
                "uv run --no-sync pytest tests/unit/ -v -m unit",
            ],
        },
    )


def handle_preflight(_args: Any) -> CommandResult:
    return _preflight_result()


def handle_eligibility(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = eligibility_data(task_id)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_start(args: Any) -> CommandResult:
    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = start_task_data(task_id, args.name, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def add_leaf_cli_options(parser: Any) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and describe the command without making changes.",
    )


def register_task_commands(subparsers: Any) -> None:
    tasks_parser = subparsers.add_parser("tasks", help="Repo task and sprint workflow helpers.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")

    list_active_parser = tasks_subparsers.add_parser(
        "list-active",
        help="List active tasks from the current sprint.",
    )
    add_leaf_cli_options(list_active_parser)
    list_active_parser.set_defaults(handler=handle_list_active)

    show_parser = tasks_subparsers.add_parser("show", help="Show a backlog task record.")
    add_leaf_cli_options(show_parser)
    show_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    show_parser.set_defaults(handler=handle_show)

    search_parser = tasks_subparsers.add_parser("search", help="Search backlog tasks by text.")
    add_leaf_cli_options(search_parser)
    search_parser.add_argument("query", nargs="+", help="Query text.")
    search_parser.add_argument(
        "--status",
        choices=["active", "backlog", "completed", "all"],
        default="all",
        help="Filter search results by task status.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of results to return.",
    )
    search_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include the raw backlog block for each matching task.",
    )
    search_parser.set_defaults(handler=handle_search)

    context_pack_parser = tasks_subparsers.add_parser(
        "context-pack",
        help="Show the task backlog/spec/sprint context pack.",
    )
    add_leaf_cli_options(context_pack_parser)
    context_pack_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    context_pack_parser.set_defaults(handler=handle_context_pack)

    preflight_parser = tasks_subparsers.add_parser(
        "preflight",
        help="Validate task-start sequencing preflight on main.",
    )
    add_leaf_cli_options(preflight_parser)
    preflight_parser.set_defaults(handler=handle_preflight)

    eligibility_parser = tasks_subparsers.add_parser(
        "eligibility",
        help="Validate whether a task can be started autonomously.",
    )
    add_leaf_cli_options(eligibility_parser)
    eligibility_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    eligibility_parser.set_defaults(handler=handle_eligibility)

    start_parser = tasks_subparsers.add_parser(
        "start",
        help="Start a task branch with sequencing guards.",
    )
    add_leaf_cli_options(start_parser)
    start_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    start_parser.add_argument("--name", required=True, help="Short branch suffix.")
    start_parser.set_defaults(handler=handle_start)
