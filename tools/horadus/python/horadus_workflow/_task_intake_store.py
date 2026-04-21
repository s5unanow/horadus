from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tools.horadus.python.horadus_workflow import _task_intake_entry_validation as entry_validation
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared

_fcntl: Any
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - unavailable on Windows.
    _fcntl = None
fcntl = _fcntl

_INTAKE_ID_PATTERN = re.compile(r"^INTAKE-(?P<number>\d{4,})$")
_TASK_ID_PATTERN = re.compile(r"^(?:TASK-)?(?P<number>\d{3,})$")
_VALID_INTAKE_STATUSES = ("pending", "promoted", "dismissed")
TaskIntakeEntry = shared.TaskIntakeEntry


class TaskIntakeMutationLockError(RuntimeError):
    """Raised when the intake log cannot be mutated under safe serialization."""


def _parse_timestamp(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("recorded_at must not be empty.")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must include timezone information.")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_intake_id(value: str) -> str:
    normalized = value.strip().upper()
    match = _INTAKE_ID_PATTERN.match(normalized)
    if match is None:
        raise ValueError(f"Invalid intake id {value!r}. Expected INTAKE-XXXX.")
    return normalized


def _normalize_optional_task_id(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    match = _TASK_ID_PATTERN.match(stripped.upper())
    if match is None:
        raise ValueError(f"Invalid task id {value!r}. Expected TASK-XXX.")
    return f"TASK-{match.group('number')}"


def _normalize_text_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def _validate_intake_entry(payload: object, *, line_number: int) -> TaskIntakeEntry:
    if not isinstance(payload, dict):
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: expected a JSON object."
        )

    required_fields = {
        "intake_id",
        "recorded_at",
        "title",
        "note",
        "refs",
        "source_task_id",
        "status",
        "groom_notes",
        "promoted_task_id",
    }
    missing_fields = sorted(required_fields - payload.keys())
    if missing_fields:
        raise ValueError(
            "Invalid task intake entry at line "
            f"{line_number}: missing fields {', '.join(missing_fields)}."
        )

    refs_raw = payload["refs"]
    if not isinstance(refs_raw, list) or any(not isinstance(item, str) for item in refs_raw):
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: refs must be a list of strings."
        )
    groom_notes_raw = payload["groom_notes"]
    if not isinstance(groom_notes_raw, list) or any(
        not isinstance(item, str) for item in groom_notes_raw
    ):
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: groom_notes must be a list of strings."
        )

    intake_id = _normalize_intake_id(str(payload["intake_id"]))
    recorded_at = _parse_timestamp(str(payload["recorded_at"]))
    title = str(payload["title"]).strip()
    note = str(payload["note"]).strip()
    entry_validation.validate_entry_title_note(title, note, line_number=line_number)

    source_task_id_raw = payload["source_task_id"]
    if source_task_id_raw is not None and not isinstance(source_task_id_raw, str):
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: source_task_id must be a string or null."
        )
    source_task_id = _normalize_optional_task_id(source_task_id_raw)

    status = str(payload["status"]).strip().lower()
    if status not in _VALID_INTAKE_STATUSES:
        raise ValueError(
            "Invalid task intake entry at line "
            f"{line_number}: unsupported status {status!r}; expected one of "
            f"{', '.join(_VALID_INTAKE_STATUSES)}."
        )

    promoted_task_id_raw = payload["promoted_task_id"]
    if promoted_task_id_raw is not None and not isinstance(promoted_task_id_raw, str):
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: promoted_task_id must be a string or null."
        )
    promoted_task_id = _normalize_optional_task_id(promoted_task_id_raw)
    entry_validation.validate_entry_promotion_fields(
        status=status,
        promoted_task_id=promoted_task_id,
        line_number=line_number,
    )

    return TaskIntakeEntry(
        intake_id=intake_id,
        recorded_at=recorded_at,
        title=title,
        note=note,
        refs=_normalize_text_list(cast("list[str]", refs_raw)),
        source_task_id=source_task_id,
        status=status,
        groom_notes=_normalize_text_list(cast("list[str]", groom_notes_raw)),
        promoted_task_id=promoted_task_id,
    )


def _load_task_intake_entries(path: Path) -> list[TaskIntakeEntry]:
    if not path.exists():
        return []

    entries: list[TaskIntakeEntry] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid task intake JSON at line {line_number}: {exc.msg}.") from exc
        entries.append(_validate_intake_entry(payload, line_number=line_number))
    return entries


def _write_task_intake_entries(path: Path, entries: list[TaskIntakeEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            for entry in entries:
                handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def _next_intake_id(entries: list[TaskIntakeEntry]) -> str:
    max_number = 0
    for entry in entries:
        match = _INTAKE_ID_PATTERN.match(entry.intake_id)
        if match is None:
            raise ValueError(f"Unexpected intake id in local intake log: {entry.intake_id}")
        max_number = max(max_number, int(match.group("number")))
    return f"INTAKE-{max_number + 1:04d}"


def _find_entry(entries: list[TaskIntakeEntry], intake_id: str) -> TaskIntakeEntry | None:
    for entry in entries:
        if entry.intake_id == intake_id:
            return entry
    return None


def _task_intake_lock_path(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.name}.lock")


@contextmanager
def task_intake_mutation_lock(log_path: Path) -> Iterator[None]:
    lock_path = _task_intake_lock_path(log_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        raise TaskIntakeMutationLockError(
            "Unable to safely serialize task intake mutations because exclusive file "
            f"locking is unavailable for {lock_path}."
        )

    try:
        handle = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise TaskIntakeMutationLockError(
            f"Unable to open the task intake lock file {lock_path}: {exc}."
        ) from exc

    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError as exc:
            raise TaskIntakeMutationLockError(
                f"Unable to acquire the task intake lock {lock_path}: {exc}."
            ) from exc
        yield
    finally:
        with suppress(OSError):
            fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


__all__ = [
    "_VALID_INTAKE_STATUSES",
    "TaskIntakeEntry",
    "TaskIntakeMutationLockError",
    "_find_entry",
    "_load_task_intake_entries",
    "_next_intake_id",
    "_normalize_intake_id",
    "_normalize_optional_task_id",
    "_normalize_text_list",
    "_parse_timestamp",
    "_validate_intake_entry",
    "_write_task_intake_entries",
    "task_intake_mutation_lock",
]
