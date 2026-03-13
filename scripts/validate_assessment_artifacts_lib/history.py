"""Task, sprint, and assessment-history loading helpers."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .artifacts import artifact_file_date, iter_markdown_files, parse_artifact
from .constants import RE_ACTIVE_SPRINT_TASK, RE_COMPLETED_TASK, RE_SPRINT_DATES, RE_TASK_TITLE

if TYPE_CHECKING:
    from .models import ParsedArtifact


def load_task_titles(repo_root: Path) -> list[tuple[str, str]]:
    titles: list[tuple[str, str]] = []
    for relative_path in ("tasks/BACKLOG.md", "tasks/COMPLETED.md"):
        path = repo_root / relative_path
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            backlog_match = RE_TASK_TITLE.match(line.strip())
            if backlog_match:
                titles.append((backlog_match.group(1), backlog_match.group(2).strip()))
                continue
            completed_match = RE_COMPLETED_TASK.match(line.strip())
            if completed_match:
                titles.append((completed_match.group(1), completed_match.group(2).strip()))
    return titles


def load_current_sprint_truth(repo_root: Path) -> tuple[dict[str, int], tuple[date, date] | None]:
    sprint_path = repo_root / "tasks/CURRENT_SPRINT.md"
    if not sprint_path.exists():
        return {}, None

    active_tasks: dict[str, int] = {}
    sprint_window: tuple[date, date] | None = None
    in_active_tasks = False

    for line_no, line in enumerate(sprint_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        sprint_match = RE_SPRINT_DATES.match(stripped)
        if sprint_match:
            sprint_window = (
                date.fromisoformat(sprint_match.group(1)),
                date.fromisoformat(sprint_match.group(2)),
            )
            continue

        if stripped == "## Active Tasks":
            in_active_tasks = True
            continue

        if in_active_tasks and stripped.startswith("## "):
            break

        if not in_active_tasks:
            continue

        task_match = RE_ACTIVE_SPRINT_TASK.match(stripped)
        if task_match:
            active_tasks[task_match.group(1)] = line_no

    return active_tasks, sprint_window


def history_artifacts_for_file(
    artifact: ParsedArtifact,
    *,
    lookback_days: int,
    all_files: list[Path],
    repo_root: Path,
    include_same_role: bool,
) -> list[ParsedArtifact]:
    normalized_target_path = artifact.path.resolve()
    file_date = artifact_file_date(artifact.path)
    cutoff = file_date - timedelta(days=lookback_days) if file_date is not None else None
    assessments_root = repo_root / "artifacts" / "assessments"
    candidate_history_files = (
        iter_markdown_files([assessments_root]) if assessments_root.exists() else all_files
    )

    history: list[ParsedArtifact] = []
    for candidate in candidate_history_files:
        if candidate.resolve() == normalized_target_path:
            continue

        candidate_artifact = parse_artifact(candidate)
        if artifact.role is None or candidate_artifact.role is None:
            continue

        same_role = candidate_artifact.role == artifact.role
        if include_same_role and not same_role:
            continue
        if not include_same_role and same_role:
            continue

        candidate_date = artifact_file_date(candidate)
        if cutoff is not None and candidate_date is not None and candidate_date < cutoff:
            continue
        if file_date is not None and candidate_date is not None and candidate_date > file_date:
            continue

        history.append(candidate_artifact)

    return history
