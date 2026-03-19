from __future__ import annotations

import argparse
from typing import Any

from tools.horadus.python.horadus_cli.task_automation_lock import (
    handle_automation_lock_check,
    handle_automation_lock_lock,
    handle_automation_lock_unlock,
)
from tools.horadus.python.horadus_cli.task_finish import handle_finish
from tools.horadus.python.horadus_cli.task_friction import (
    handle_record_friction,
    handle_summarize_friction,
)
from tools.horadus.python.horadus_cli.task_ledgers import handle_close_ledgers
from tools.horadus.python.horadus_cli.task_lifecycle import handle_lifecycle
from tools.horadus.python.horadus_cli.task_preflight import (
    handle_eligibility,
    handle_preflight,
    handle_start,
)
from tools.horadus.python.horadus_cli.task_query import (
    handle_context_pack,
    handle_list_active,
    handle_search,
    handle_show,
)
from tools.horadus.python.horadus_cli.task_shared import VALID_FRICTION_TYPES
from tools.horadus.python.horadus_cli.task_workflow import (
    DEFAULT_LOCAL_REVIEW_BASE_BRANCH,
    SUPPORTED_LOCAL_REVIEW_PROVIDERS,
    VALID_LOCAL_REVIEW_USEFULNESS,
    handle_local_gate,
    handle_local_review,
    handle_safe_start,
)


def add_leaf_cli_options(parser: Any) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Validate and describe the command without making changes.",
    )


def _register_local_review_parser(tasks_subparsers: Any) -> None:
    local_review_parser = tasks_subparsers.add_parser(
        "local-review",
        help="Run an opt-in local pre-push review via a supported local agent CLI.",
    )
    add_leaf_cli_options(local_review_parser)
    local_review_parser.add_argument(
        "--provider",
        choices=list(SUPPORTED_LOCAL_REVIEW_PROVIDERS),
        help="Review provider override. Defaults to .env.harness or the repo default.",
    )
    local_review_parser.add_argument(
        "--base",
        default=DEFAULT_LOCAL_REVIEW_BASE_BRANCH,
        help="Base branch used for the branch diff review target.",
    )
    local_review_parser.add_argument(
        "--instructions",
        help="Optional additional review instructions layered onto the repo-owned rubric.",
    )
    local_review_parser.add_argument(
        "--allow-provider-fallback",
        action="store_true",
        help="Allow fallback after runtime/auth/config failures instead of only missing CLIs.",
    )
    local_review_parser.add_argument(
        "--save-raw-output",
        action="store_true",
        help="Keep the provider raw output under artifacts/agent/local-review/runs/.",
    )
    local_review_parser.add_argument(
        "--usefulness",
        choices=list(VALID_LOCAL_REVIEW_USEFULNESS),
        default="pending",
        help="Optional lightweight usefulness annotation for local-review telemetry.",
    )
    local_review_parser.set_defaults(handler=handle_local_review)


def _register_local_gate_parser(tasks_subparsers: Any) -> None:
    local_gate_parser = tasks_subparsers.add_parser(
        "local-gate",
        help="Run the canonical post-task local validation gate.",
    )
    add_leaf_cli_options(local_gate_parser)
    local_gate_parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full CI-parity local gate.",
    )
    local_gate_parser.set_defaults(handler=handle_local_gate)


def _register_automation_lock_parser(tasks_subparsers: Any) -> None:
    automation_lock_parser = tasks_subparsers.add_parser(
        "automation-lock",
        help="Check, acquire, or release a repo-owned automation lock path.",
    )
    automation_lock_subparsers = automation_lock_parser.add_subparsers(
        dest="automation_lock_command"
    )

    check_parser = automation_lock_subparsers.add_parser(
        "check",
        help="Inspect the current state of an automation lock path.",
    )
    add_leaf_cli_options(check_parser)
    check_parser.add_argument("--path", required=True, help="Lock path to inspect.")
    check_parser.set_defaults(handler=handle_automation_lock_check)

    lock_parser = automation_lock_subparsers.add_parser(
        "lock",
        help="Acquire an automation lock path if it is currently available.",
    )
    add_leaf_cli_options(lock_parser)
    lock_parser.add_argument("--path", required=True, help="Lock path to acquire.")
    lock_parser.add_argument(
        "--owner-pid",
        type=int,
        default=None,
        help="Optional long-lived owner PID used for stale-lock detection and recovery.",
    )
    lock_parser.set_defaults(handler=handle_automation_lock_lock)

    unlock_parser = automation_lock_subparsers.add_parser(
        "unlock",
        help="Release an automation lock path.",
    )
    add_leaf_cli_options(unlock_parser)
    unlock_parser.add_argument("--path", required=True, help="Lock path to release.")
    unlock_parser.add_argument(
        "--owner-pid",
        type=int,
        default=None,
        help="Optional owner PID required to release a live automation lock safely.",
    )
    unlock_parser.set_defaults(handler=handle_automation_lock_unlock)


def register_task_commands(subparsers: Any) -> None:
    tasks_parser = subparsers.add_parser("tasks", help="Repo task and sprint workflow helpers.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")

    list_active_parser = tasks_subparsers.add_parser(
        "list-active",
        help="List active tasks from the current sprint.",
    )
    add_leaf_cli_options(list_active_parser)
    list_active_parser.set_defaults(handler=handle_list_active)

    show_parser = tasks_subparsers.add_parser("show", help="Show a live or archived task record.")
    add_leaf_cli_options(show_parser)
    show_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    show_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Allow lookup in archived backlog snapshots when the task is no longer live.",
    )
    show_parser.set_defaults(handler=handle_show)

    search_parser = tasks_subparsers.add_parser("search", help="Search live backlog tasks by text.")
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
    search_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Include archived backlog snapshots in the search results.",
    )
    search_parser.set_defaults(handler=handle_search)

    context_pack_parser = tasks_subparsers.add_parser(
        "context-pack",
        help="Show the task backlog/spec/sprint context pack.",
    )
    add_leaf_cli_options(context_pack_parser)
    context_pack_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    context_pack_parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Allow archived backlog lookup when the task is no longer live.",
    )
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

    safe_start_parser = tasks_subparsers.add_parser(
        "safe-start",
        help="Run autonomous task-start eligibility plus guarded branch start.",
    )
    add_leaf_cli_options(safe_start_parser)
    safe_start_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    safe_start_parser.add_argument("--name", required=True, help="Short branch suffix.")
    safe_start_parser.set_defaults(handler=handle_safe_start)

    close_ledgers_parser = tasks_subparsers.add_parser(
        "close-ledgers",
        help="Archive the full task block and update the live task ledgers.",
    )
    add_leaf_cli_options(close_ledgers_parser)
    close_ledgers_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    close_ledgers_parser.set_defaults(handler=handle_close_ledgers)

    record_friction_parser = tasks_subparsers.add_parser(
        "record-friction",
        help="Append a structured Horadus workflow friction entry to local gitignored artifacts.",
    )
    add_leaf_cli_options(record_friction_parser)
    record_friction_parser.add_argument("task_id", help="Task id (TASK-XXX or XXX).")
    record_friction_parser.add_argument(
        "--command-attempted",
        required=True,
        help="Canonical command or workflow step that triggered friction.",
    )
    record_friction_parser.add_argument(
        "--fallback-used",
        required=True,
        help="Fallback command or manual action used instead.",
    )
    record_friction_parser.add_argument(
        "--friction-type",
        required=True,
        choices=list(VALID_FRICTION_TYPES),
        help="Structured friction category.",
    )
    record_friction_parser.add_argument(
        "--note",
        required=True,
        help="Short note describing the friction.",
    )
    record_friction_parser.add_argument(
        "--suggested-improvement",
        required=True,
        help="Short suggestion for improving Horadus or its guidance.",
    )
    record_friction_parser.set_defaults(handler=handle_record_friction)

    summarize_friction_parser = tasks_subparsers.add_parser(
        "summarize-friction",
        help="Summarize daily Horadus workflow friction into a compact report artifact.",
    )
    add_leaf_cli_options(summarize_friction_parser)
    summarize_friction_parser.add_argument(
        "--date",
        default=None,
        help="UTC report date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    summarize_friction_parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional report path. Defaults to "
            "artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md"
        ),
    )
    summarize_friction_parser.set_defaults(handler=handle_summarize_friction)

    finish_parser = tasks_subparsers.add_parser(
        "finish",
        help="Complete the current task PR lifecycle and sync local main.",
    )
    add_leaf_cli_options(finish_parser)
    finish_parser.add_argument(
        "task_id",
        nargs="?",
        help="Optional task id (TASK-XXX or XXX) to verify against the current task branch.",
    )
    finish_parser.set_defaults(handler=handle_finish)

    lifecycle_parser = tasks_subparsers.add_parser(
        "lifecycle",
        help="Report task lifecycle state and optionally verify repo-policy completion.",
    )
    add_leaf_cli_options(lifecycle_parser)
    lifecycle_parser.add_argument(
        "task_id",
        nargs="?",
        help="Optional task id (TASK-XXX or XXX). Required when not on the task branch.",
    )
    lifecycle_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless the task is fully complete by repo policy.",
    )
    lifecycle_parser.set_defaults(handler=handle_lifecycle)

    _register_automation_lock_parser(tasks_subparsers)
    _register_local_review_parser(tasks_subparsers)
    _register_local_gate_parser(tasks_subparsers)
