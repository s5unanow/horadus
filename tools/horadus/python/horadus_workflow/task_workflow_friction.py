from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode


@dataclass(slots=True)
class WorkflowFrictionEntry:
    recorded_at: str
    task_id: str
    command_attempted: str
    fallback_used: str
    friction_type: str
    note: str
    suggested_improvement: str


@dataclass(slots=True)
class WorkflowFrictionPatternSummary:
    friction_type: str
    command_attempted: str
    fallback_used: str
    suggested_improvement: str
    count: int
    task_ids: list[str]
    notes: list[str]
    first_recorded_at: str
    last_recorded_at: str


@dataclass(slots=True)
class WorkflowFrictionImprovementSummary:
    suggested_improvement: str
    count: int
    task_ids: list[str]
    command_attempts: list[str]
    fallback_paths: list[str]
    friction_type_counts: dict[str, int]


def _friction_log_path() -> Path:
    repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
    return repo_root() / shared.FRICTION_LOG_DIRECTORY / shared.FRICTION_LOG_FILENAME


def _friction_summary_path(report_date: date) -> Path:
    repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
    return repo_root() / shared.FRICTION_SUMMARY_DIRECTORY / f"{report_date.isoformat()}.md"


def _parse_report_date(report_date_input: str | None) -> date:
    if report_date_input is None:
        return datetime.now(tz=UTC).date()
    try:
        return date.fromisoformat(report_date_input)
    except ValueError as exc:
        raise ValueError(
            f"Invalid report date {report_date_input!r}. Expected YYYY-MM-DD."
        ) from exc


def _parse_recorded_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _relative_display_path(path: Path) -> str:
    repo_root = shared._compat_attr("repo_root", task_repo)
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def _load_workflow_friction_entries(log_path: Path) -> list[WorkflowFrictionEntry]:
    if not log_path.exists():
        return []

    entries: list[WorkflowFrictionEntry] = []
    required_fields = {
        "recorded_at",
        "task_id",
        "command_attempted",
        "fallback_used",
        "friction_type",
        "note",
        "suggested_improvement",
    }
    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid workflow friction JSON at line {line_number}: {exc.msg}."
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"Invalid workflow friction entry at line {line_number}: expected a JSON object."
            )
        missing_fields = sorted(required_fields - payload.keys())
        if missing_fields:
            raise ValueError(
                "Invalid workflow friction entry at line "
                f"{line_number}: missing fields {', '.join(missing_fields)}."
            )
        entry = WorkflowFrictionEntry(
            recorded_at=str(payload["recorded_at"]),
            task_id=str(payload["task_id"]),
            command_attempted=str(payload["command_attempted"]),
            fallback_used=str(payload["fallback_used"]),
            friction_type=str(payload["friction_type"]),
            note=str(payload["note"]),
            suggested_improvement=str(payload["suggested_improvement"]),
        )
        _parse_recorded_at(entry.recorded_at)
        entries.append(entry)
    return entries


def _entries_for_report_date(
    entries: list[WorkflowFrictionEntry], report_date: date
) -> list[WorkflowFrictionEntry]:
    return [
        entry for entry in entries if _parse_recorded_at(entry.recorded_at).date() == report_date
    ]


def _summarize_workflow_friction(
    entries: list[WorkflowFrictionEntry],
) -> tuple[
    list[WorkflowFrictionPatternSummary],
    list[WorkflowFrictionImprovementSummary],
    Counter[str],
]:
    pattern_groups: dict[tuple[str, str, str, str], list[WorkflowFrictionEntry]] = {}
    improvement_groups: dict[str, list[WorkflowFrictionEntry]] = {}
    friction_type_counts: Counter[str] = Counter()

    for entry in entries:
        friction_type_counts[entry.friction_type] += 1
        pattern_key = (
            entry.friction_type,
            entry.command_attempted,
            entry.fallback_used,
            entry.suggested_improvement,
        )
        pattern_groups.setdefault(pattern_key, []).append(entry)
        improvement_groups.setdefault(entry.suggested_improvement, []).append(entry)

    pattern_summaries: list[WorkflowFrictionPatternSummary] = []
    for pattern_entries in pattern_groups.values():
        sorted_entries = sorted(
            pattern_entries, key=lambda item: _parse_recorded_at(item.recorded_at)
        )
        first_entry = sorted_entries[0]
        unique_notes: list[str] = []
        for item in sorted_entries:
            note = item.note.strip()
            if note and note not in unique_notes:
                unique_notes.append(note)
        pattern_summaries.append(
            WorkflowFrictionPatternSummary(
                friction_type=first_entry.friction_type,
                command_attempted=first_entry.command_attempted,
                fallback_used=first_entry.fallback_used,
                suggested_improvement=first_entry.suggested_improvement,
                count=len(sorted_entries),
                task_ids=sorted({item.task_id for item in sorted_entries}),
                notes=unique_notes[:3],
                first_recorded_at=sorted_entries[0].recorded_at,
                last_recorded_at=sorted_entries[-1].recorded_at,
            )
        )

    pattern_summaries.sort(
        key=lambda item: (-item.count, item.last_recorded_at, item.suggested_improvement)
    )

    improvement_summaries: list[WorkflowFrictionImprovementSummary] = []
    for suggested_improvement, grouped_entries in improvement_groups.items():
        type_counter = Counter(item.friction_type for item in grouped_entries)
        improvement_summaries.append(
            WorkflowFrictionImprovementSummary(
                suggested_improvement=suggested_improvement,
                count=len(grouped_entries),
                task_ids=sorted({item.task_id for item in grouped_entries}),
                command_attempts=sorted({item.command_attempted for item in grouped_entries}),
                fallback_paths=sorted({item.fallback_used for item in grouped_entries}),
                friction_type_counts=dict(sorted(type_counter.items())),
            )
        )

    improvement_summaries.sort(key=lambda item: (-item.count, item.suggested_improvement.lower()))
    return pattern_summaries, improvement_summaries, friction_type_counts


def _render_workflow_friction_summary(
    *,
    report_date: date,
    log_path: Path,
    report_path: Path,
    entries: list[WorkflowFrictionEntry],
    patterns: list[WorkflowFrictionPatternSummary],
    improvements: list[WorkflowFrictionImprovementSummary],
    friction_type_counts: Counter[str],
    missing_log: bool,
) -> str:
    window_start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
    window_end = window_start + timedelta(days=1)
    lines = [
        f"# Horadus Workflow Friction Summary - {report_date.isoformat()}",
        "",
        f"- Report date (UTC): `{report_date.isoformat()}`",
        f"- Summary window: `{window_start.isoformat().replace('+00:00', 'Z')}` to `{window_end.isoformat().replace('+00:00', 'Z')}`",
        f"- Source log: `{_relative_display_path(log_path)}`",
        f"- Summary path: `{_relative_display_path(report_path)}`",
        f"- Entries summarized: `{len(entries)}`",
        f"- Distinct grouped patterns: `{len(patterns)}`",
        "",
        "## Highlights",
    ]
    if missing_log:
        lines.append(
            "- No workflow friction log exists yet; this report is an empty daily checkpoint."
        )
    elif not entries:
        lines.append("- No workflow friction entries were recorded for this UTC day.")
    else:
        top_type, top_count = friction_type_counts.most_common(1)[0]
        lines.extend(
            [
                f"- Most common friction type: `{top_type}` (`{top_count}` entries).",
                f"- Candidate CLI/skill improvements surfaced: `{len(improvements)}`.",
                "- Human review is required before turning any candidate below into a backlog task.",
            ]
        )

    lines.extend(["", "## Grouped Patterns"])
    if not patterns:
        lines.append("- None for this report window.")
    else:
        for index, pattern in enumerate(patterns, start=1):
            notes = "; ".join(pattern.notes) if pattern.notes else "No extra notes recorded."
            lines.extend(
                [
                    f"### {index}. `{pattern.friction_type}` x{pattern.count}",
                    f"- Candidate improvement: {pattern.suggested_improvement}",
                    f"- Command attempted: `{pattern.command_attempted}`",
                    f"- Fallback used: `{pattern.fallback_used}`",
                    f"- Affected tasks: {', '.join(f'`{task_id}`' for task_id in pattern.task_ids)}",
                    f"- Observed notes: {notes}",
                ]
            )

    lines.extend(["", "## Candidate Improvements"])
    if not improvements:
        lines.append("- None. No follow-up candidates were generated for this report window.")
    else:
        for index, improvement in enumerate(improvements, start=1):
            friction_mix = ", ".join(
                f"`{friction_type}` x{count}"
                for friction_type, count in improvement.friction_type_counts.items()
            )
            commands = ", ".join(f"`{command}`" for command in improvement.command_attempts)
            lines.extend(
                [
                    f"{index}. {improvement.suggested_improvement}",
                    f"Seen in `{improvement.count}` entries across {', '.join(f'`{task_id}`' for task_id in improvement.task_ids)}.",
                    f"Friction mix: {friction_mix}",
                    f"Related commands: {commands}",
                ]
            )

    lines.extend(
        [
            "",
            "## Triage Guidance",
            "- Review this summary before proposing workflow follow-up work.",
            "- Do not auto-create backlog tasks from this report; backlog creation requires explicit human review.",
            "- Use the raw JSONL log only when deeper evidence is needed for a reviewed follow-up.",
            "",
            "## Proposed Follow-Up Seeds (Human Review Required)",
        ]
    )
    if not improvements:
        lines.append("- None for this report window.")
    else:
        for improvement in improvements:
            lines.append(
                "- Candidate task seed: "
                f"Investigate Horadus workflow friction around {improvement.suggested_improvement}."
            )

    return "\n".join(lines) + "\n"


def record_friction_data(
    *,
    task_input: str,
    command_attempted: str,
    fallback_used: str,
    friction_type: str,
    note: str,
    suggested_improvement: str,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    task_id = task_repo.normalize_task_id(task_input)
    normalized_type = friction_type.strip().lower()
    if normalized_type not in shared.VALID_FRICTION_TYPES:
        return (
            ExitCode.VALIDATION_ERROR,
            {
                "friction_type": friction_type,
                "valid_friction_types": list(shared.VALID_FRICTION_TYPES),
            },
            [
                "Workflow friction logging failed.",
                (
                    "Unsupported friction type "
                    f"{friction_type!r}; expected one of: {', '.join(shared.VALID_FRICTION_TYPES)}"
                ),
            ],
        )

    entry = WorkflowFrictionEntry(
        recorded_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        task_id=task_id,
        command_attempted=command_attempted.strip(),
        fallback_used=fallback_used.strip(),
        friction_type=normalized_type,
        note=note.strip(),
        suggested_improvement=suggested_improvement.strip(),
    )
    log_path = _friction_log_path()
    repo_root = shared._compat_attr("repo_root", task_repo)
    relative_log_path = str(log_path.relative_to(repo_root()))
    lines = [
        f"Workflow friction log target: {relative_log_path}",
        "Record entries only for real Horadus workflow friction or forced fallback, not routine success cases.",
        "Friction entries remain in gitignored artifacts and are not source-of-truth task/spec/project records.",
        "Normal task execution should not require reading the friction log.",
    ]
    if dry_run:
        lines.append("Dry run: would append structured workflow friction entry.")
        return (
            ExitCode.OK,
            {"dry_run": True, "log_path": relative_log_path, "entry": entry},
            lines,
        )

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
    except OSError as exc:
        lines.extend(
            [
                "Workflow friction logging failed while writing the gitignored artifact.",
                f"Filesystem error: {exc}",
            ]
        )
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {
                "dry_run": False,
                "log_path": relative_log_path,
                "entry": entry,
                "error": str(exc),
            },
            lines,
        )
    lines.append("Recorded structured workflow friction entry.")
    return (
        ExitCode.OK,
        {"dry_run": False, "log_path": relative_log_path, "entry": entry},
        lines,
    )


def summarize_friction_data(
    *,
    report_date_input: str | None,
    output_path_input: str | None,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    try:
        report_date = _parse_report_date(report_date_input)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [str(exc)])

    log_path = _friction_log_path()
    missing_log = not log_path.exists()
    try:
        entries = _load_workflow_friction_entries(log_path)
    except ValueError as exc:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"log_path": _relative_display_path(log_path)},
            [f"Workflow friction summary failed: {exc}"],
        )
    except OSError as exc:
        return (
            ExitCode.ENVIRONMENT_ERROR,
            {"log_path": _relative_display_path(log_path), "error": str(exc)},
            [
                "Workflow friction summary failed while reading the friction log artifact.",
                f"Filesystem error: {exc}",
            ],
        )

    filtered_entries = _entries_for_report_date(entries, report_date)
    patterns, improvements, friction_type_counts = _summarize_workflow_friction(filtered_entries)
    report_path = (
        Path(output_path_input).expanduser()
        if output_path_input is not None
        else _friction_summary_path(report_date)
    )
    if not report_path.is_absolute():
        repo_root = shared._compat_attr("repo_root", task_repo)
        report_path = repo_root() / report_path
    report_markdown = _render_workflow_friction_summary(
        report_date=report_date,
        log_path=log_path,
        report_path=report_path,
        entries=filtered_entries,
        patterns=patterns,
        improvements=improvements,
        friction_type_counts=friction_type_counts,
        missing_log=missing_log,
    )
    lines = [
        f"Workflow friction source: {_relative_display_path(log_path)}",
        f"Daily summary target: {_relative_display_path(report_path)}",
        "Human review remains required before creating backlog tasks from this summary.",
    ]
    data: dict[str, object] = {
        "dry_run": dry_run,
        "report_date": report_date,
        "log_path": _relative_display_path(log_path),
        "report_path": _relative_display_path(report_path),
        "entry_count": len(filtered_entries),
        "pattern_count": len(patterns),
        "improvement_count": len(improvements),
        "missing_log": missing_log,
        "patterns": [asdict(item) for item in patterns],
        "improvements": [asdict(item) for item in improvements],
        "friction_type_counts": dict(sorted(friction_type_counts.items())),
    }
    if dry_run:
        lines.append("Dry run: would write grouped workflow friction summary.")
        data["report_markdown"] = report_markdown
        return (ExitCode.OK, data, lines)

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown, encoding="utf-8")
    except OSError as exc:
        lines.extend(
            [
                "Workflow friction summary failed while writing the report artifact.",
                f"Filesystem error: {exc}",
            ]
        )
        data["error"] = str(exc)
        return (ExitCode.ENVIRONMENT_ERROR, data, lines)

    lines.append("Wrote grouped workflow friction summary.")
    return (ExitCode.OK, data, lines)


def handle_record_friction(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = record_friction_data(
        task_input=task_id,
        command_attempted=args.command_attempted,
        fallback_used=args.fallback_used,
        friction_type=args.friction_type,
        note=args.note,
        suggested_improvement=args.suggested_improvement,
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_summarize_friction(args: Any) -> CommandResult:
    exit_code, data, lines = summarize_friction_data(
        report_date_input=args.date,
        output_path_input=args.output,
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "WorkflowFrictionEntry",
    "WorkflowFrictionImprovementSummary",
    "WorkflowFrictionPatternSummary",
    "_entries_for_report_date",
    "_friction_log_path",
    "_friction_summary_path",
    "_load_workflow_friction_entries",
    "_parse_recorded_at",
    "_parse_report_date",
    "_relative_display_path",
    "_render_workflow_friction_summary",
    "_summarize_workflow_friction",
    "handle_record_friction",
    "handle_summarize_friction",
    "record_friction_data",
    "summarize_friction_data",
]
