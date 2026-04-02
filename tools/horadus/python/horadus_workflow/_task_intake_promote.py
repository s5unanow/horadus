from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tools.horadus.python.horadus_workflow.task_workflow_shared import TaskIntakeEntry


def build_promoted_entries(
    entries: list[TaskIntakeEntry],
    *,
    intake_id: str,
    promoted_task_id: str,
) -> list[TaskIntakeEntry]:
    updated_entries: list[TaskIntakeEntry] = []
    for entry in entries:
        if entry.intake_id != intake_id:
            updated_entries.append(entry)
            continue
        updated_entries.append(
            TaskIntakeEntry(
                intake_id=entry.intake_id,
                recorded_at=entry.recorded_at,
                title=entry.title,
                note=entry.note,
                refs=list(entry.refs),
                source_task_id=entry.source_task_id,
                status="promoted",
                groom_notes=list(entry.groom_notes),
                promoted_task_id=promoted_task_id,
            )
        )
    return updated_entries


def persist_promoted_intake(
    *,
    backlog_path: Path,
    updated_backlog: str,
    log_path: Path,
    updated_entries: list[TaskIntakeEntry],
    write_entries: Callable[[Path, list[TaskIntakeEntry]], None],
) -> None:
    backlog_path.write_text(updated_backlog, encoding="utf-8")
    # Promotion intentionally updates the canonical backlog first. If the local
    # intake log rewrite fails afterward, the operator-facing task record still
    # exists and the accepted v1 recovery path is to reconcile the local intake
    # artifact manually instead of rolling back backlog.
    write_entries(log_path, updated_entries)


__all__ = ["build_promoted_entries", "persist_promoted_intake"]
