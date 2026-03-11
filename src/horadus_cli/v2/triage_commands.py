from __future__ import annotations

import re
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.horadus_cli.v2.result import CommandResult
from src.horadus_cli.v2.task_commands import add_leaf_cli_options
from src.horadus_cli.v2.task_repo import (
    completed_path,
    current_sprint_path,
    line_search,
    parse_active_tasks,
    parse_human_blockers,
    repo_root,
)


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
    keyword_pattern = _compile_or_pattern(args.keyword or [])
    path_pattern = _compile_or_pattern(args.path or [])
    proposal_pattern = _compile_or_pattern(args.proposal_id or [])
    recent_paths = _recent_assessment_paths(args.lookback_days)

    keyword_hits = []
    if keyword_pattern is not None:
        keyword_hits.extend(line_search(repo_root() / "tasks" / "BACKLOG.md", keyword_pattern))
        keyword_hits.extend(line_search(completed_path(), keyword_pattern))

    path_hits = []
    if path_pattern is not None:
        path_hits.extend(line_search(repo_root() / "tasks" / "BACKLOG.md", path_pattern))

    proposal_hits = []
    if proposal_pattern is not None:
        for relative_path in recent_paths:
            proposal_hits.extend(line_search(repo_root() / relative_path, proposal_pattern))

    active_tasks = parse_active_tasks()
    active_task_ids = {task.task_id for task in active_tasks}
    blockers = parse_human_blockers(task_ids=active_task_ids)
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]

    lines = [
        "Triage input bundle",
        f"- active_tasks={len(active_tasks)}",
        f"- human_blockers={len(blockers)}",
        f"- overdue_human_blockers={len(overdue_blockers)}",
        f"- recent_assessments={len(recent_paths)}",
        f"- keyword_hits={len(keyword_hits)}",
        f"- path_hits={len(path_hits)}",
        f"- proposal_hits={len(proposal_hits)}",
    ]
    if args.keyword:
        lines.append(f"- keywords={', '.join(args.keyword)}")
    if args.path:
        lines.append(f"- paths={', '.join(args.path)}")
    if args.proposal_id:
        lines.append(f"- proposal_ids={', '.join(args.proposal_id)}")
    if overdue_blockers:
        lines.append(
            f"- overdue_tasks={', '.join(blocker.task_id for blocker in overdue_blockers)}"
        )

    return CommandResult(
        lines=lines,
        data={
            "current_sprint": {
                "path": str(current_sprint_path().relative_to(repo_root())),
                "active_tasks": [asdict(task) for task in active_tasks],
                "human_blockers": [asdict(blocker) for blocker in blockers],
                "overdue_human_blockers": [asdict(blocker) for blocker in overdue_blockers],
            },
            "searches": {
                "keywords": args.keyword or [],
                "paths": args.path or [],
                "proposal_ids": args.proposal_id or [],
                "keyword_hits": [asdict(hit) for hit in keyword_hits],
                "path_hits": [asdict(hit) for hit in path_hits],
                "proposal_hits": [asdict(hit) for hit in proposal_hits],
            },
            "recent_assessments": recent_paths,
            "lookback_days": args.lookback_days,
        },
    )


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
    collect_parser.set_defaults(handler=handle_collect)
