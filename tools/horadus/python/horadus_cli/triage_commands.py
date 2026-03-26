from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from tools.horadus.python.horadus_cli.task_commands import add_leaf_cli_options
from tools.horadus.python.horadus_workflow import task_repo as workflow_task_repo
from tools.horadus.python.horadus_workflow import triage as workflow_triage

if TYPE_CHECKING:
    from tools.horadus.python.horadus_workflow.result import CommandResult

completed_path = workflow_task_repo.completed_path
backlog_path = workflow_task_repo.backlog_path
backlog_task_records = workflow_task_repo.backlog_task_records
completed_task_ids = workflow_task_repo.completed_task_ids
current_sprint_path = workflow_task_repo.current_sprint_path
line_search = workflow_task_repo.line_search
parse_active_tasks = workflow_task_repo.parse_active_tasks
parse_human_blockers = workflow_task_repo.parse_human_blockers
repo_root = workflow_task_repo.repo_root
task_record = workflow_task_repo.task_record


def _recent_assessment_paths(lookback_days: int) -> list[str]:
    cutoff = datetime.now(tz=UTC).date() - timedelta(days=max(0, lookback_days))
    paths: list[str] = []
    for path in sorted((repo_root() / "artifacts" / "assessments").glob("*/daily/*.md")):
        try:
            file_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if file_date >= cutoff:
            paths.append(str(path.relative_to(repo_root())))
    return paths


def _compile_or_pattern(values: list[str]) -> str | None:
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        return None
    return "|".join(re.escape(value) for value in cleaned)


def handle_collect(args: Any) -> CommandResult:
    original_repo_root = workflow_task_repo.repo_root
    workflow_task_repo.repo_root = repo_root
    workflow_triage.repo_root = repo_root
    workflow_triage.backlog_path = backlog_path
    workflow_triage.backlog_task_records = backlog_task_records
    workflow_triage.completed_path = completed_path
    workflow_triage.completed_task_ids = completed_task_ids
    workflow_triage.current_sprint_path = current_sprint_path
    workflow_triage.line_search = line_search
    workflow_triage.parse_active_tasks = parse_active_tasks
    workflow_triage.parse_human_blockers = parse_human_blockers
    workflow_triage._recent_assessment_paths = _recent_assessment_paths
    workflow_triage._compile_or_pattern = _compile_or_pattern
    workflow_triage.task_record = task_record
    try:
        return workflow_triage.handle_collect(args)
    finally:
        workflow_task_repo.repo_root = original_repo_root


def register_triage_commands(subparsers: Any) -> None:
    triage_parser = subparsers.add_parser("triage", help="Structured triage input collection.")
    triage_subparsers = triage_parser.add_subparsers(dest="triage_command")

    collect_parser = triage_subparsers.add_parser(
        "collect",
        help="Collect current sprint, backlog, completed, and recent assessment inputs for triage.",
    )
    add_leaf_cli_options(collect_parser)
    collect_parser.add_argument(
        "--keyword",
        action="append",
        help="Keyword to search in backlog/completed task ledgers (repeatable).",
    )
    collect_parser.add_argument(
        "--path",
        action="append",
        help="Path/module hint to search in backlog task entries (repeatable).",
    )
    collect_parser.add_argument(
        "--proposal-id",
        action="append",
        help="Proposal id to search in recent assessment artifacts (repeatable).",
    )
    collect_parser.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="How many days of assessment artifacts to include.",
    )
    collect_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw line-level search hits alongside task-aware matches.",
    )
    collect_parser.set_defaults(handler=handle_collect)


__all__ = [
    "_compile_or_pattern",
    "_recent_assessment_paths",
    "completed_path",
    "current_sprint_path",
    "handle_collect",
    "line_search",
    "parse_active_tasks",
    "parse_human_blockers",
    "register_triage_commands",
    "repo_root",
]
