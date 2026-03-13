"""Sprint-grounding validation for assessment artifacts."""

from __future__ import annotations

from pathlib import Path

from .artifacts import artifact_file_date
from .constants import (
    CURRENT_TASK_ASSERTION_PATTERN,
    HISTORICAL_TASK_MARKER_PATTERN,
    RE_TASK_REFERENCE,
)
from .history import load_current_sprint_truth
from .models import Finding


def grounding_findings_for_file(path: Path, *, repo_root: Path) -> list[Finding]:
    file_date = artifact_file_date(path)
    active_tasks, sprint_window = load_current_sprint_truth(repo_root)
    if file_date is None or sprint_window is None:
        return []

    sprint_start, sprint_end = sprint_window
    if not (sprint_start <= file_date <= sprint_end):
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        task_ids = RE_TASK_REFERENCE.findall(line)
        if not task_ids:
            continue
        if not CURRENT_TASK_ASSERTION_PATTERN.search(line):
            continue
        if HISTORICAL_TASK_MARKER_PATTERN.search(line):
            continue

        for task_id in task_ids:
            if task_id in active_tasks:
                continue
            findings.append(
                Finding(
                    path=path,
                    line_no=line_no,
                    message=(
                        f"{task_id}: referenced as current/active/blocking but not present in "
                        "tasks/CURRENT_SPRINT.md Active Tasks. Use current sprint truth for live "
                        "references, or mark historical references explicitly with "
                        "[historical]/[completed]."
                    ),
                )
            )

    return findings
