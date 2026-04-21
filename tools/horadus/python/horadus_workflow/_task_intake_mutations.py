from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow._task_intake_store import (
    _find_entry,
    _load_task_intake_entries,
    _next_intake_id,
    _write_task_intake_entries,
)
from tools.horadus.python.horadus_workflow.result import ExitCode

TaskIntakeEntry = shared.TaskIntakeEntry


@dataclass(slots=True)
class _PreparedGroomUpdate:
    notes: list[str]
    updated_entries: list[TaskIntakeEntry]


def _build_pending_entry_from_entries(
    *,
    entries: list[TaskIntakeEntry],
    title: str,
    note: str,
    refs: list[str],
    source_task_id: str | None,
    recorded_at: str,
) -> TaskIntakeEntry:
    return TaskIntakeEntry(
        intake_id=_next_intake_id(entries),
        recorded_at=recorded_at,
        title=title,
        note=note,
        refs=refs,
        source_task_id=source_task_id,
        status="pending",
        groom_notes=[],
        promoted_task_id=None,
    )


def build_pending_entry(
    *,
    log_path: Path,
    title: str,
    note: str,
    refs: list[str],
    source_task_id: str | None,
    recorded_at: str,
) -> TaskIntakeEntry:
    return _build_pending_entry_from_entries(
        entries=_load_task_intake_entries(log_path),
        title=title,
        note=note,
        refs=refs,
        source_task_id=source_task_id,
        recorded_at=recorded_at,
    )


def persist_pending_entry(
    *,
    log_path: Path,
    title: str,
    note: str,
    refs: list[str],
    source_task_id: str | None,
    recorded_at: str,
    mutation_lock: Callable[[Path], Any],
) -> TaskIntakeEntry:
    with mutation_lock(log_path):
        entries = _load_task_intake_entries(log_path)
        entry = _build_pending_entry_from_entries(
            entries=entries,
            title=title,
            note=note,
            refs=refs,
            source_task_id=source_task_id,
            recorded_at=recorded_at,
        )
        _write_task_intake_entries(log_path, [*entries, entry])
    return entry


def prepare_groom_update(
    *,
    entries: list[TaskIntakeEntry],
    normalized_ids: list[str],
    action: str,
    notes: list[str],
) -> _PreparedGroomUpdate | tuple[int, dict[str, object], list[str]]:
    missing_ids = [item for item in normalized_ids if _find_entry(entries, item) is None]
    if missing_ids:
        return (
            ExitCode.NOT_FOUND,
            {"missing_intake_ids": missing_ids},
            ["Task intake grooming failed.", f"Unknown intake ids: {', '.join(missing_ids)}"],
        )

    updated_entries: list[TaskIntakeEntry] = []
    for entry in entries:
        if entry.intake_id not in normalized_ids:
            updated_entries.append(entry)
            continue
        if entry.status == "promoted":
            return (
                ExitCode.VALIDATION_ERROR,
                {"intake_id": entry.intake_id, "status": entry.status},
                [
                    "Task intake grooming failed.",
                    f"{entry.intake_id} is already promoted and cannot be {action}ed.",
                ],
            )
        updated_entries.append(
            TaskIntakeEntry(
                intake_id=entry.intake_id,
                recorded_at=entry.recorded_at,
                title=entry.title,
                note=entry.note,
                refs=list(entry.refs),
                source_task_id=entry.source_task_id,
                status="dismissed" if action == "dismiss" else "pending",
                groom_notes=[*entry.groom_notes, *notes],
                promoted_task_id=entry.promoted_task_id,
            )
        )

    return _PreparedGroomUpdate(notes=notes, updated_entries=updated_entries)
