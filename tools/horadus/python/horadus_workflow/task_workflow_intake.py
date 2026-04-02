from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tools.horadus.python.horadus_workflow import _task_intake_backlog as backlog_support
from tools.horadus.python.horadus_workflow import _task_intake_entry_validation as entry_validation
from tools.horadus.python.horadus_workflow import _task_intake_promote as promote_support
from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

_INTAKE_ID_PATTERN = re.compile(r"^INTAKE-(?P<number>\d{4})$")
_TASK_ID_PATTERN = re.compile(r"^(?:TASK-)?(?P<number>\d{3,})$")
_VALID_INTAKE_STATUSES = ("pending", "promoted", "dismissed")
TaskIntakeEntry = shared.TaskIntakeEntry


def _task_intake_log_path() -> Path:
    repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
    return repo_root() / shared.INTAKE_LOG_DIRECTORY / shared.INTAKE_LOG_FILENAME


def _relative_display_path(path: Path) -> str:
    repo_root = cast("Callable[[], Path]", shared._compat_attr("repo_root", task_repo))
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _detect_current_task_id() -> str | None:
    branch_result = shared._run_command(["git", "branch", "--show-current"])
    if branch_result.returncode != 0:
        return None
    branch_name = branch_result.stdout.strip()
    if not branch_name or branch_name == "HEAD":
        return None
    return shared._task_id_from_branch_name(branch_name)


def _render_backlog_task_block(
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
    return backlog_support.render_backlog_task_block(
        task_id=task_id,
        title=title,
        priority=priority,
        estimate=estimate,
        description=description,
        files=files,
        acceptance_criteria=acceptance_criteria,
        assessment_refs=assessment_refs,
    )


def _allocate_backlog_task_id(backlog_text: str) -> tuple[str, str]:
    return backlog_support.allocate_backlog_task_id(backlog_text)


def _insert_backlog_task_block(backlog_text: str, task_block: str) -> str:
    return backlog_support.insert_backlog_task_block(backlog_text, task_block)


def _promote_success_result(
    *,
    intake_id: str,
    promoted_task_id: str,
    backlog_path: Path,
    log_path: Path,
    dry_run: bool,
    task_block: str,
) -> tuple[int, dict[str, object], list[str]]:
    lines = [
        "Task intake promoted.",
        f"Intake id: {intake_id}",
        f"Created task: {promoted_task_id}",
        f"Updated backlog: {_relative_display_path(backlog_path)}",
        f"Updated intake log: {_relative_display_path(log_path)}",
    ]
    return (
        ExitCode.OK,
        {
            "intake_id": intake_id,
            "promoted_task_id": promoted_task_id,
            "backlog_path": _relative_display_path(backlog_path),
            "log_path": _relative_display_path(log_path),
            "dry_run": dry_run,
            "task_block": task_block,
        },
        lines,
    )


def task_intake_add_data(
    *,
    title: str,
    note: str,
    refs: list[str] | None,
    source_task: str | None,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    title_text = title.strip()
    note_text = note.strip()
    if not title_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            ["Task intake failed.", "--title must not be empty."],
        )
    if "\n" in title_text or "\r" in title_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            ["Task intake failed.", "--title must be a single line."],
        )
    if not note_text:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake failed.", "--note must not be empty."])

    try:
        source_task_id = (
            _normalize_optional_task_id(source_task)
            if source_task is not None
            else _detect_current_task_id()
        )
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake failed.", str(exc)])

    log_path = _task_intake_log_path()
    try:
        entries = _load_task_intake_entries(log_path)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake failed.", str(exc)])

    entry = TaskIntakeEntry(
        intake_id=_next_intake_id(entries),
        recorded_at=_utc_timestamp(),
        title=title_text,
        note=note_text,
        refs=_normalize_text_list(refs),
        source_task_id=source_task_id,
        status="pending",
        groom_notes=[],
        promoted_task_id=None,
    )
    if not dry_run:
        _write_task_intake_entries(log_path, [*entries, entry])

    lines = [
        "Task intake recorded.",
        f"Intake id: {entry.intake_id}",
        f"Status: {entry.status}",
        f"Stored in: {_relative_display_path(log_path)}",
    ]
    if entry.source_task_id is not None:
        lines.append(f"Source task: {entry.source_task_id}")
    if entry.refs:
        lines.append(f"Refs: {', '.join(entry.refs)}")

    return (
        ExitCode.OK,
        {
            "entry": asdict(entry),
            "log_path": _relative_display_path(log_path),
            "dry_run": dry_run,
        },
        lines,
    )


def task_intake_list_data(
    *,
    status: str | None,
    limit: int | None,
) -> tuple[int, dict[str, object], list[str]]:
    if status is not None and status not in _VALID_INTAKE_STATUSES:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            [
                "Task intake listing failed.",
                f"Unsupported status {status!r}; expected one of {', '.join(_VALID_INTAKE_STATUSES)}.",
            ],
        )
    if limit is not None and limit < 1:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            ["Task intake listing failed.", "--limit must be a positive integer."],
        )

    log_path = _task_intake_log_path()
    try:
        entries = _load_task_intake_entries(log_path)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake listing failed.", str(exc)])

    filtered_entries = [entry for entry in entries if status is None or entry.status == status]
    if limit is not None:
        filtered_entries = filtered_entries[:limit]

    lines = [
        "Task intake entries:",
        f"Source: {_relative_display_path(log_path)}",
        f"Count: {len(filtered_entries)}",
    ]
    if not filtered_entries:
        lines.append("- None.")
    else:
        for entry in filtered_entries:
            lines.append(f"- {entry.intake_id} [{entry.status}] {entry.title}")
            lines.append(f"  note: {entry.note}")
            if entry.source_task_id is not None:
                lines.append(f"  source_task: {entry.source_task_id}")
            if entry.refs:
                lines.append(f"  refs: {', '.join(entry.refs)}")
            if entry.promoted_task_id is not None:
                lines.append(f"  promoted_task_id: {entry.promoted_task_id}")

    return (
        ExitCode.OK,
        {
            "entries": [asdict(entry) for entry in filtered_entries],
            "status_filter": status,
            "count": len(filtered_entries),
            "log_path": _relative_display_path(log_path),
        },
        lines,
    )


def task_intake_groom_data(
    *,
    intake_ids: list[str],
    action: str,
    append_notes: list[str] | None,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    if action not in {"dismiss", "restore"}:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            ["Task intake grooming failed.", f"Unsupported grooming action {action!r}."],
        )

    try:
        normalized_ids = list(dict.fromkeys(_normalize_intake_id(value) for value in intake_ids))
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake grooming failed.", str(exc)])

    log_path = _task_intake_log_path()
    try:
        entries = _load_task_intake_entries(log_path)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake grooming failed.", str(exc)])

    missing_ids = [item for item in normalized_ids if _find_entry(entries, item) is None]
    if missing_ids:
        return (
            ExitCode.NOT_FOUND,
            {"missing_intake_ids": missing_ids},
            ["Task intake grooming failed.", f"Unknown intake ids: {', '.join(missing_ids)}"],
        )

    notes = _normalize_text_list(append_notes)
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

    if not dry_run:
        _write_task_intake_entries(log_path, updated_entries)

    updated_status = "dismissed" if action == "dismiss" else "pending"
    lines = [
        "Task intake updated.",
        f"Action: {action}",
        f"Updated status: {updated_status}",
        f"Intake ids: {', '.join(normalized_ids)}",
        f"Stored in: {_relative_display_path(log_path)}",
    ]
    if notes:
        lines.append(f"Appended notes: {len(notes)}")

    return (
        ExitCode.OK,
        {
            "intake_ids": normalized_ids,
            "action": action,
            "updated_status": updated_status,
            "log_path": _relative_display_path(log_path),
            "dry_run": dry_run,
        },
        lines,
    )


def task_intake_promote_data(
    *,
    intake_id: str,
    priority: str,
    estimate: str,
    acceptance: list[str],
    files: list[str] | None,
    description: list[str] | None,
    assessment_refs: list[str] | None,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    failure_prefix = "Task intake promotion failed."
    try:
        normalized_intake_id = _normalize_intake_id(intake_id)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, str(exc)])

    priority_text = priority.strip()
    estimate_text = estimate.strip()
    acceptance_items = _normalize_text_list(acceptance)
    if not priority_text:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, "--priority must not be empty."])
    if not estimate_text:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, "--estimate must not be empty."])
    if not acceptance_items:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            [failure_prefix, "At least one --acceptance value is required."],
        )

    log_path = _task_intake_log_path()
    try:
        entries = _load_task_intake_entries(log_path)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, str(exc)])

    target_entry = _find_entry(entries, normalized_intake_id)
    if target_entry is None:
        return (
            ExitCode.NOT_FOUND,
            {"intake_id": normalized_intake_id},
            [failure_prefix, f"{normalized_intake_id} was not found."],
        )
    if target_entry.status != "pending":
        return (
            ExitCode.VALIDATION_ERROR,
            {"intake_id": normalized_intake_id, "status": target_entry.status},
            [
                failure_prefix,
                f"{normalized_intake_id} is {target_entry.status}; only pending entries can be promoted.",
            ],
        )

    backlog_path = task_repo.backlog_path()
    backlog_text = task_repo.read_text(backlog_path)
    try:
        promoted_task_id, backlog_with_incremented_id = _allocate_backlog_task_id(backlog_text)
        task_block = _render_backlog_task_block(
            task_id=promoted_task_id,
            title=target_entry.title,
            priority=priority_text,
            estimate=estimate_text,
            description=backlog_support._render_description_lines(description, target_entry.note),
            files=_normalize_text_list(files),
            acceptance_criteria=acceptance_items,
            assessment_refs=_normalize_text_list(assessment_refs),
        )
        updated_backlog = _insert_backlog_task_block(backlog_with_incremented_id, task_block)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, str(exc)])

    updated_entries = promote_support.build_promoted_entries(
        entries,
        intake_id=normalized_intake_id,
        promoted_task_id=promoted_task_id,
    )

    if not dry_run:
        promote_support.persist_promoted_intake(
            backlog_path=backlog_path,
            updated_backlog=updated_backlog,
            log_path=log_path,
            updated_entries=updated_entries,
            write_entries=_write_task_intake_entries,
        )

    return _promote_success_result(
        intake_id=normalized_intake_id,
        promoted_task_id=promoted_task_id,
        backlog_path=backlog_path,
        log_path=log_path,
        dry_run=dry_run,
        task_block=task_block,
    )


def handle_task_intake_add(args: Any) -> CommandResult:
    exit_code, data, lines = task_intake_add_data(
        title=args.title,
        note=args.note,
        refs=list(getattr(args, "refs", []) or []),
        source_task=getattr(args, "source_task", None),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_task_intake_list(args: Any) -> CommandResult:
    exit_code, data, lines = task_intake_list_data(
        status=getattr(args, "status", None),
        limit=getattr(args, "limit", None),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_task_intake_groom(args: Any) -> CommandResult:
    action = "dismiss" if getattr(args, "dismiss", False) else "restore"
    exit_code, data, lines = task_intake_groom_data(
        intake_ids=list(args.intake_ids),
        action=action,
        append_notes=list(getattr(args, "append_notes", []) or []),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_task_intake_promote(args: Any) -> CommandResult:
    exit_code, data, lines = task_intake_promote_data(
        intake_id=args.intake_id,
        priority=args.priority,
        estimate=args.estimate,
        acceptance=list(args.acceptance),
        files=list(getattr(args, "files", []) or []),
        description=list(getattr(args, "description", []) or []),
        assessment_refs=list(getattr(args, "assessment_refs", []) or []),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "TaskIntakeEntry",
    "_allocate_backlog_task_id",
    "_detect_current_task_id",
    "_find_entry",
    "_insert_backlog_task_block",
    "_load_task_intake_entries",
    "_next_intake_id",
    "_normalize_intake_id",
    "_render_backlog_task_block",
    "_task_intake_log_path",
    "_write_task_intake_entries",
    "handle_task_intake_add",
    "handle_task_intake_groom",
    "handle_task_intake_list",
    "handle_task_intake_promote",
    "task_intake_add_data",
    "task_intake_groom_data",
    "task_intake_list_data",
    "task_intake_promote_data",
]
