from __future__ import annotations

import re
from pathlib import Path

_BACKLOG_TASK_HEADER_PATTERN = re.compile(r"^### (?P<task_id>TASK-\d{3}): .+$", re.MULTILINE)
_COMPLETED_TASK_LINE_PATTERN = re.compile(r"^-\s+(?P<task_id>TASK-\d{3}):", re.MULTILINE)


def known_followup_task_ids(repo_root: Path, backlog_text: str) -> set[str]:
    task_ids = {
        match.group("task_id") for match in _BACKLOG_TASK_HEADER_PATTERN.finditer(backlog_text)
    }

    completed_path = repo_root / "tasks" / "COMPLETED.md"
    if completed_path.exists():
        task_ids.update(
            match.group("task_id")
            for match in _COMPLETED_TASK_LINE_PATTERN.finditer(
                completed_path.read_text(encoding="utf-8")
            )
        )

    archive_root = repo_root / "archive" / "closed_tasks"
    if archive_root.exists():
        for archive_path in archive_root.glob("*.md"):
            task_ids.update(
                match.group("task_id")
                for match in _BACKLOG_TASK_HEADER_PATTERN.finditer(
                    archive_path.read_text(encoding="utf-8")
                )
            )
    return task_ids
