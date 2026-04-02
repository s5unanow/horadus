from __future__ import annotations

import re
import textwrap

_NEXT_TASK_ID_PATTERN = re.compile(
    r"^(?P<prefix>- Next available task IDs start at `TASK-)(?P<number>\d{3,})(?P<suffix>`\.)$",
    re.MULTILINE,
)
_FUTURE_IDEAS_MARKER = "\n---\n\n## Future Ideas (Not Scheduled)\n"


def _render_description_lines(description: list[str] | None, fallback_note: str) -> list[str]:
    raw_lines = description if description else fallback_note.splitlines()
    normalized: list[str] = []
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped:
            if normalized and normalized[-1] != "":
                normalized.append("")
            continue
        normalized.extend(textwrap.wrap(stripped, width=79) or [stripped])
    return normalized or [fallback_note.strip()]


def _format_files(files: list[str]) -> str:
    normalized_files = []
    for item in files:
        stripped = item.strip()
        if not stripped:
            continue
        normalized_files.append(stripped if stripped.startswith("`") else f"`{stripped}`")
    return ", ".join(normalized_files)


def render_backlog_task_block(
    *,
    task_id: str,
    title: str,
    priority: str,
    estimate: str,
    description: list[str],
    files: list[str],
    acceptance_criteria: list[str],
    assessment_refs: list[str],
) -> str:
    lines = [
        f"### {task_id}: {title}",
        f"**Priority**: {priority}",
        f"**Estimate**: {estimate}",
        "",
        *description,
        "",
    ]
    if assessment_refs:
        lines.extend(
            [
                "**Assessment-Ref**:",
                *(f"- {item}" for item in assessment_refs),
                "",
            ]
        )
    if files:
        lines.extend([f"**Files**: {_format_files(files)}", ""])
    lines.extend(
        [
            "**Acceptance Criteria**:",
            *(f"- [ ] {item}" for item in acceptance_criteria),
        ]
    )
    return "\n".join(lines).rstrip()


def allocate_backlog_task_id(backlog_text: str) -> tuple[str, str]:
    match = _NEXT_TASK_ID_PATTERN.search(backlog_text)
    if match is None:
        raise ValueError("Unable to locate the next available task id marker in tasks/BACKLOG.md.")
    next_number = int(match.group("number"))
    task_id = f"TASK-{next_number:03d}"
    updated_text = (
        backlog_text[: match.start()]
        + f"{match.group('prefix')}{next_number + 1:03d}{match.group('suffix')}"
        + backlog_text[match.end() :]
    )
    return task_id, updated_text


def insert_backlog_task_block(backlog_text: str, task_block: str) -> str:
    marker_index = backlog_text.rfind(_FUTURE_IDEAS_MARKER)
    if marker_index == -1:
        raise ValueError("Unable to locate the terminal Future Ideas section in tasks/BACKLOG.md.")
    return (
        backlog_text[:marker_index].rstrip()
        + "\n\n---\n\n"
        + task_block
        + "\n"
        + backlog_text[marker_index:]
    )


__all__ = [
    "allocate_backlog_task_id",
    "insert_backlog_task_block",
    "render_backlog_task_block",
]
