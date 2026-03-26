from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tools.horadus.python.horadus_workflow.result import CommandResult
from tools.horadus.python.horadus_workflow.task_repo import (
    backlog_path,
    backlog_task_records,
    completed_path,
    completed_task_ids,
    current_sprint_path,
    line_search,
    parse_active_tasks,
    parse_human_blockers,
    repo_root,
    task_record,
)

TASK_ID_PATTERN = re.compile(r"TASK-\d{3}")


@dataclass(slots=True)
class TaskAwareContext:
    field: str
    source: str
    excerpt: str


@dataclass(slots=True)
class TaskAwareSearchHit:
    task_id: str
    title: str
    status: str
    matched_fields: list[str]
    contexts: list[TaskAwareContext]
    raw_hits: list[dict[str, object]]


@dataclass(slots=True)
class _TaskHitState:
    task_id: str
    title: str
    status: str
    matched_fields: list[str]
    contexts: list[TaskAwareContext]
    raw_hits: list[dict[str, object]]
    context_keys: set[tuple[str, str, str]]
    raw_keys: set[tuple[str, int, str]]


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


def _task_status(task_id: str, *, active_task_ids: set[str], completed_ids: set[str]) -> str:
    if task_id in active_task_ids:
        return "active"
    if task_id in completed_ids:
        return "completed"
    return "backlog"


def _strip_backticks(value: str) -> str:
    return value.strip().strip("`")


def _record_contexts(record: Any, pattern: str) -> list[TaskAwareContext]:
    regex = re.compile(pattern, re.IGNORECASE)
    source = str(record.source_path)
    contexts: list[TaskAwareContext] = []
    field_values = (
        ("title", [record.title]),
        ("description", record.description),
        ("files", [_strip_backticks(item) for item in record.files]),
        ("acceptance_criteria", record.acceptance_criteria),
        ("assessment_refs", record.assessment_refs),
    )
    for field, values in field_values:
        for value in values:
            excerpt = value.strip()
            if excerpt and regex.search(excerpt):
                contexts.append(TaskAwareContext(field=field, source=source, excerpt=excerpt))
    return contexts


def _new_task_hit(task_id: str, title: str, status: str) -> _TaskHitState:
    return _TaskHitState(
        task_id=task_id,
        title=title,
        status=status,
        matched_fields=[],
        contexts=[],
        raw_hits=[],
        context_keys=set(),
        raw_keys=set(),
    )


def _ensure_task_hit(
    hit_map: dict[str, _TaskHitState],
    *,
    task_id: str,
    title: str,
    status: str,
) -> _TaskHitState:
    return hit_map.setdefault(task_id, _new_task_hit(task_id, title, status))


def _add_contexts(
    hit_map: dict[str, _TaskHitState],
    *,
    task_id: str,
    title: str,
    status: str,
    contexts: list[TaskAwareContext],
) -> None:
    if not contexts:
        return
    hit = _ensure_task_hit(hit_map, task_id=task_id, title=title, status=status)
    for context in contexts:
        if context.field not in hit.matched_fields:
            hit.matched_fields.append(context.field)
        context_key = (context.field, context.source, context.excerpt)
        if context_key in hit.context_keys:
            continue
        hit.context_keys.add(context_key)
        hit.contexts.append(context)


def _add_raw_hit(
    hit_map: dict[str, _TaskHitState],
    *,
    task_id: str,
    title: str,
    status: str,
    source: str,
    line_number: int,
    line: str,
) -> None:
    hit = _ensure_task_hit(hit_map, task_id=task_id, title=title, status=status)
    raw_key = (source, line_number, line)
    if raw_key in hit.raw_keys:
        return
    hit.raw_keys.add(raw_key)
    hit.raw_hits.append({"source": source, "line_number": line_number, "line": line})


def _task_hit_payloads(
    hit_map: dict[str, _TaskHitState], *, include_raw: bool
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for task_id, entry in hit_map.items():
        payload: dict[str, object] = {
            "task_id": task_id,
            "title": entry.title,
            "status": entry.status,
            "matched_fields": list(entry.matched_fields),
            "contexts": [asdict(item) for item in entry.contexts],
        }
        if include_raw:
            payload["raw_hits"] = list(entry.raw_hits)
        payloads.append(payload)
    payloads.sort(key=lambda item: int(str(item["task_id"])[5:]))
    return payloads


def _task_summary_line(label: str, hits: list[dict[str, object]]) -> str | None:
    if not hits:
        return None
    task_ids = ", ".join(str(item["task_id"]) for item in hits)
    return f"- {label}={task_ids}"


def _task_refs(value: str) -> list[str]:
    return list(dict.fromkeys(TASK_ID_PATTERN.findall(value)))


def _fallback_task_details(
    task_id: str, *, active_task_ids: set[str], completed_ids: set[str]
) -> tuple[str, str]:
    record = task_record(task_id, include_archive=True)
    if record is not None:
        return str(record.title), str(record.status)
    return task_id, _task_status(
        task_id, active_task_ids=active_task_ids, completed_ids=completed_ids
    )


def _backlog_line_task_ids() -> dict[int, str]:
    mapping: dict[int, str] = {}
    current_task_id: str | None = None
    for line_number, line in enumerate(
        backlog_path().read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = re.match(r"^### (?P<task_id>TASK-\d{3}): ", line)
        if match is not None:
            current_task_id = match.group("task_id")
        if current_task_id is not None:
            mapping[line_number] = current_task_id
    return mapping


def _search_backlog_records(
    pattern: str,
    *,
    active_task_ids: set[str],
    completed_ids: set[str],
) -> dict[str, _TaskHitState]:
    hit_map: dict[str, _TaskHitState] = {}
    for record in backlog_task_records().values():
        contexts = _record_contexts(record, pattern)
        if not contexts:
            continue
        status = _task_status(
            record.task_id,
            active_task_ids=active_task_ids,
            completed_ids=completed_ids,
        )
        _add_contexts(
            hit_map,
            task_id=record.task_id,
            title=record.title,
            status=status,
            contexts=contexts,
        )
    return hit_map


def _attach_backlog_raw_hits(
    hit_map: dict[str, _TaskHitState],
    *,
    pattern: str,
    active_task_ids: set[str],
    completed_ids: set[str],
) -> None:
    line_task_ids = _backlog_line_task_ids()
    records = backlog_task_records()
    for raw_hit in line_search(backlog_path(), pattern):
        task_id = line_task_ids.get(raw_hit.line_number)
        if task_id is None or task_id not in records:
            continue
        record = records[task_id]
        status = _task_status(task_id, active_task_ids=active_task_ids, completed_ids=completed_ids)
        _add_raw_hit(
            hit_map,
            task_id=task_id,
            title=record.title,
            status=status,
            source=raw_hit.source,
            line_number=raw_hit.line_number,
            line=raw_hit.line,
        )


def _attach_completed_hits(
    hit_map: dict[str, _TaskHitState],
    *,
    pattern: str,
    active_task_ids: set[str],
    completed_ids: set[str],
    include_raw: bool,
) -> None:
    for raw_hit in line_search(completed_path(), pattern):
        task_refs = _task_refs(raw_hit.line)
        if not task_refs:
            continue
        for task_id in task_refs:
            title, status = _fallback_task_details(
                task_id,
                active_task_ids=active_task_ids,
                completed_ids=completed_ids,
            )
            _add_contexts(
                hit_map,
                task_id=task_id,
                title=title,
                status=status,
                contexts=[
                    TaskAwareContext(
                        field="completed_summary",
                        source=raw_hit.source,
                        excerpt=raw_hit.line.strip(),
                    )
                ],
            )
            if include_raw:
                _add_raw_hit(
                    hit_map,
                    task_id=task_id,
                    title=title,
                    status=status,
                    source=raw_hit.source,
                    line_number=raw_hit.line_number,
                    line=raw_hit.line,
                )


def _search_proposal_hits(
    pattern: str,
    *,
    recent_paths: list[str],
    active_task_ids: set[str],
    completed_ids: set[str],
    include_raw: bool,
) -> dict[str, _TaskHitState]:
    hit_map: dict[str, _TaskHitState] = {}
    for relative_path in recent_paths:
        for raw_hit in line_search(repo_root() / relative_path, pattern):
            task_refs = _task_refs(raw_hit.line)
            if not task_refs:
                continue
            for task_id in task_refs:
                title, status = _fallback_task_details(
                    task_id,
                    active_task_ids=active_task_ids,
                    completed_ids=completed_ids,
                )
                _add_contexts(
                    hit_map,
                    task_id=task_id,
                    title=title,
                    status=status,
                    contexts=[
                        TaskAwareContext(
                            field="proposal_reference",
                            source=raw_hit.source,
                            excerpt=raw_hit.line.strip(),
                        )
                    ],
                )
                if include_raw:
                    _add_raw_hit(
                        hit_map,
                        task_id=task_id,
                        title=title,
                        status=status,
                        source=raw_hit.source,
                        line_number=raw_hit.line_number,
                        line=raw_hit.line,
                    )
    return hit_map


def _collect_search_hits(
    *,
    keyword_pattern: str | None,
    path_pattern: str | None,
    proposal_pattern: str | None,
    recent_paths: list[str],
    active_task_ids: set[str],
    completed_ids: set[str],
    include_raw: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    keyword_hit_map: dict[str, _TaskHitState] = {}
    if keyword_pattern is not None:
        keyword_hit_map = _search_backlog_records(
            keyword_pattern,
            active_task_ids=active_task_ids,
            completed_ids=completed_ids,
        )
        _attach_completed_hits(
            keyword_hit_map,
            pattern=keyword_pattern,
            active_task_ids=active_task_ids,
            completed_ids=completed_ids,
            include_raw=include_raw,
        )
        if include_raw:
            _attach_backlog_raw_hits(
                keyword_hit_map,
                pattern=keyword_pattern,
                active_task_ids=active_task_ids,
                completed_ids=completed_ids,
            )

    path_hit_map: dict[str, _TaskHitState] = {}
    if path_pattern is not None:
        path_hit_map = _search_backlog_records(
            path_pattern,
            active_task_ids=active_task_ids,
            completed_ids=completed_ids,
        )
        if include_raw:
            _attach_backlog_raw_hits(
                path_hit_map,
                pattern=path_pattern,
                active_task_ids=active_task_ids,
                completed_ids=completed_ids,
            )

    proposal_hit_map: dict[str, _TaskHitState] = {}
    if proposal_pattern is not None:
        proposal_hit_map = _search_proposal_hits(
            proposal_pattern,
            recent_paths=recent_paths,
            active_task_ids=active_task_ids,
            completed_ids=completed_ids,
            include_raw=include_raw,
        )

    return (
        _task_hit_payloads(keyword_hit_map, include_raw=include_raw),
        _task_hit_payloads(path_hit_map, include_raw=include_raw),
        _task_hit_payloads(proposal_hit_map, include_raw=include_raw),
    )


def _summary_lines_for_hits(
    *,
    active_tasks: list[Any],
    blockers: list[Any],
    overdue_blockers: list[Any],
    recent_paths: list[str],
    keyword_hits: list[dict[str, object]],
    path_hits: list[dict[str, object]],
    proposal_hits: list[dict[str, object]],
    args: Any,
) -> list[str]:
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
    for label, hits in (
        ("keyword_tasks", keyword_hits),
        ("path_tasks", path_hits),
        ("proposal_tasks", proposal_hits),
    ):
        summary_line = _task_summary_line(label, hits)
        if summary_line is not None:
            lines.append(summary_line)
    return lines


def handle_collect(args: Any) -> CommandResult:
    keyword_pattern = _compile_or_pattern(args.keyword or [])
    path_pattern = _compile_or_pattern(args.path or [])
    proposal_pattern = _compile_or_pattern(args.proposal_id or [])
    recent_paths = _recent_assessment_paths(args.lookback_days)
    include_raw = bool(getattr(args, "include_raw", False))

    active_tasks = parse_active_tasks()
    active_task_ids = {task.task_id for task in active_tasks}
    completed_ids = completed_task_ids()
    keyword_hits, path_hits, proposal_hits = _collect_search_hits(
        keyword_pattern=keyword_pattern,
        path_pattern=path_pattern,
        proposal_pattern=proposal_pattern,
        recent_paths=recent_paths,
        active_task_ids=active_task_ids,
        completed_ids=completed_ids,
        include_raw=include_raw,
    )

    blockers = parse_human_blockers(task_ids=active_task_ids)
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]
    lines = _summary_lines_for_hits(
        active_tasks=active_tasks,
        blockers=blockers,
        overdue_blockers=overdue_blockers,
        recent_paths=recent_paths,
        keyword_hits=keyword_hits,
        path_hits=path_hits,
        proposal_hits=proposal_hits,
        args=args,
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
                "include_raw": include_raw,
                "keyword_hits": keyword_hits,
                "path_hits": path_hits,
                "proposal_hits": proposal_hits,
            },
            "recent_assessments": recent_paths,
            "lookback_days": args.lookback_days,
        },
    )


__all__ = [
    "CommandResult",
    "_compile_or_pattern",
    "_recent_assessment_paths",
    "backlog_path",
    "backlog_task_records",
    "completed_path",
    "completed_task_ids",
    "current_sprint_path",
    "handle_collect",
    "line_search",
    "parse_active_tasks",
    "parse_human_blockers",
    "repo_root",
    "task_record",
]
