from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

_CURRENT_SPRINT_PLACEHOLDER_PATTERN = re.compile(
    r"^-\s+Sprint opened on .*no Sprint .* tasks are complete yet\.$",
    re.MULTILINE,
)
_COMPLETED_TASKS_HEADER = "# Completed Tasks"
_CLOSED_TASK_ARCHIVE_STATUS_LINE = "**Status**: Archived closed-task ledger (non-authoritative)"
_SPRINT_NUMBER_PATTERN = re.compile(r"^\*\*Sprint Number\*\*:\s*(?P<number>\d+)\s*$", re.MULTILINE)


def _replace_h2_section(content: str, heading: str, body: str) -> str:
    pattern = re.compile(
        rf"(^##\s+{re.escape(heading)}\s*\n)(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        raise ValueError(f"Unable to locate section '{heading}'")
    normalized_body = body.rstrip("\n")
    replacement = f"{match.group(1)}{normalized_body}\n\n"
    return f"{content[: match.start()]}{replacement}{content[match.end() :]}"


def _extract_h2_section_body(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        raise ValueError(f"Unable to locate section '{heading}'")
    return match.group("body")


def _extract_sprint_number(content: str) -> str:
    match = _SPRINT_NUMBER_PATTERN.search(content)
    if match is None:
        raise ValueError("Unable to determine sprint number from tasks/CURRENT_SPRINT.md")
    return match.group("number")


def _remove_task_lines(section_body: str, task_id: str) -> str:
    task_prefix_patterns = (
        re.compile(r"^-\s+`(?P<task_id>TASK-\d+)`(?:\s|$)"),
        re.compile(r"^-\s+(?P<task_id>TASK-\d+)(?:\s|\||$)"),
    )
    kept_lines = []
    for line in section_body.splitlines():
        stripped = line.strip()
        matched_task_id = None
        for pattern in task_prefix_patterns:
            match = pattern.match(stripped)
            if match is not None:
                matched_task_id = match.group("task_id")
                break
        if matched_task_id != task_id:
            kept_lines.append(line)
    return "\n".join(kept_lines).strip("\n")


def _append_completed_sprint_line(section_body: str, task_id: str, title: str) -> str:
    target_line = f"- `{task_id}` {title} ✅"
    lines = [
        line
        for line in section_body.splitlines()
        if line.strip() and _CURRENT_SPRINT_PLACEHOLDER_PATTERN.match(line.strip()) is None
    ]
    if target_line not in lines:
        lines.append(target_line)
    return "\n".join(lines).strip("\n")


def _upsert_completed_ledger_entry(
    content: str,
    *,
    sprint_number: str,
    task_id: str,
    title: str,
) -> str:
    if not content.strip():
        content = f"{_COMPLETED_TASKS_HEADER}\n"
    if _COMPLETED_TASKS_HEADER not in content:
        content = f"{_COMPLETED_TASKS_HEADER}\n\n{content.lstrip()}"

    entry_line = f"- {task_id}: {title} ✅"
    section_heading = f"## Sprint {sprint_number}"
    pattern = re.compile(
        rf"(^##\s+Sprint\s+{re.escape(sprint_number)}\s*\n)(?P<body>.*?)(?=^##\s+Sprint\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        suffix = "" if content.endswith("\n") else "\n"
        return f"{content.rstrip()}{suffix}\n{section_heading}\n{entry_line}\n"

    lines = [line for line in match.group("body").splitlines() if line.strip()]
    if entry_line not in lines:
        lines.append(entry_line)
    replacement = f"{match.group(1)}" + "\n".join(lines) + "\n"
    return f"{content[: match.start()]}{replacement}{content[match.end() :]}"


def _closed_task_archive_preamble(archive_label: str) -> str:
    return "\n".join(
        [
            "# Closed Task Archive",
            "",
            _CLOSED_TASK_ARCHIVE_STATUS_LINE,
            f"**Quarter**: {archive_label}",
            "",
            task_repo.CLOSED_TASK_ARCHIVE_GUIDANCE,
            "",
            "---",
            "",
        ]
    )


def _append_archived_task_block(
    archive_path: Path,
    *,
    archive_label: str,
    task_id: str,
    raw_block: str,
) -> None:
    task_block_match = shared._compat_attr("task_block_match", task_repo)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_exists = archive_path.exists()
    if archive_exists:
        archive_text = archive_path.read_text(encoding="utf-8")
    else:
        archive_text = _closed_task_archive_preamble(archive_label)

    if not archive_exists or task_block_match(task_id, archive_path) is None:
        suffix = "" if archive_text.endswith("\n") else "\n"
        archive_text = f"{archive_text}{suffix}{raw_block.strip()}\n\n---\n"
    archive_path.write_text(archive_text, encoding="utf-8")


def _remove_backlog_task_block(backlog_text: str, task_id: str) -> str:
    pattern = re.compile(
        rf"^###\s+{re.escape(task_id)}:\s+.*?(?:\n---\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn("", backlog_text, count=1)
    if count != 1:
        raise ValueError(f"Unable to remove {task_id} from tasks/BACKLOG.md")
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def close_ledgers_task_data(
    task_input: str,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    task_record = shared._compat_attr("task_record", task_repo)
    archived_task_record = shared._compat_attr("archived_task_record", task_repo)
    task_block_match = shared._compat_attr("task_block_match", task_repo)
    backlog_path = shared._compat_attr("backlog_path", task_repo)
    current_sprint_path = shared._compat_attr("current_sprint_path", task_repo)
    completed_path = shared._compat_attr("completed_path", task_repo)
    current_date = shared._compat_attr("current_date", task_repo)
    closed_tasks_archive_path = shared._compat_attr("closed_tasks_archive_path", task_repo)
    repo_root = shared._compat_attr("repo_root", task_repo)
    task_id = task_repo.normalize_task_id(task_input)
    live_record = task_record(task_id)
    if live_record is None:
        if archived_task_record(task_id) is not None:
            return (
                ExitCode.VALIDATION_ERROR,
                {"task_id": task_id, "already_archived": True},
                [f"{task_id} is already closed and archived."],
            )
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"{task_id} not found in tasks/BACKLOG.md"],
        )

    if task_block_match(task_id) is None:
        return (
            ExitCode.NOT_FOUND,
            {"task_id": task_id},
            [f"{task_id} not found in tasks/BACKLOG.md"],
        )

    backlog_text = backlog_path().read_text(encoding="utf-8")
    sprint_text = current_sprint_path().read_text(encoding="utf-8")
    completed_file = completed_path()
    completed_text = (
        completed_file.read_text(encoding="utf-8")
        if completed_file.exists()
        else f"{_COMPLETED_TASKS_HEADER}\n"
    )

    archive_date = current_date()
    archive_path = closed_tasks_archive_path(archive_date)
    archive_label = archive_path.stem
    updated_backlog = _remove_backlog_task_block(backlog_text, task_id)
    updated_sprint = _replace_h2_section(
        sprint_text,
        "Active Tasks",
        _remove_task_lines(_extract_h2_section_body(sprint_text, "Active Tasks"), task_id),
    )
    updated_sprint = _replace_h2_section(
        updated_sprint,
        "Completed This Sprint",
        _append_completed_sprint_line(
            _extract_h2_section_body(updated_sprint, "Completed This Sprint"),
            task_id,
            live_record.title,
        ),
    )
    try:
        human_blocker_body = _extract_h2_section_body(updated_sprint, "Human Blocker Metadata")
    except ValueError:
        human_blocker_body = None
    if human_blocker_body is not None:
        updated_sprint = _replace_h2_section(
            updated_sprint,
            "Human Blocker Metadata",
            _remove_task_lines(human_blocker_body, task_id),
        )
    sprint_number = _extract_sprint_number(updated_sprint)
    updated_completed = _upsert_completed_ledger_entry(
        completed_text,
        sprint_number=sprint_number,
        task_id=task_id,
        title=live_record.title,
    )

    lines = [
        f"Task ledger close: {task_id}",
        f"- archive_shard={archive_path.relative_to(repo_root())}",
        f"- sprint={sprint_number}",
    ]
    if dry_run:
        lines.append("Dry run: would archive the full task block and update live ledgers.")
        return (
            ExitCode.OK,
            {
                "task_id": task_id,
                "archive_path": str(archive_path.relative_to(repo_root())),
                "sprint_number": sprint_number,
                "dry_run": True,
            },
            lines,
        )

    _append_archived_task_block(
        archive_path,
        archive_label=archive_label,
        task_id=task_id,
        raw_block=live_record.raw_block,
    )
    backlog_path().write_text(updated_backlog, encoding="utf-8")
    current_sprint_path().write_text(updated_sprint, encoding="utf-8")
    completed_file.write_text(updated_completed, encoding="utf-8")
    lines.append(
        "Archived task block and updated tasks/BACKLOG.md, tasks/CURRENT_SPRINT.md, and tasks/COMPLETED.md."
    )
    return (
        ExitCode.OK,
        {
            "task_id": task_id,
            "archive_path": str(archive_path.relative_to(repo_root())),
            "sprint_number": sprint_number,
            "dry_run": False,
        },
        lines,
    )


def handle_close_ledgers(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])
    exit_code, data, lines = close_ledgers_task_data(task_id, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "_append_archived_task_block",
    "_append_completed_sprint_line",
    "_closed_task_archive_preamble",
    "_extract_h2_section_body",
    "_extract_sprint_number",
    "_remove_backlog_task_block",
    "_remove_task_lines",
    "_replace_h2_section",
    "_upsert_completed_ledger_entry",
    "close_ledgers_task_data",
    "handle_close_ledgers",
]
