from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tools.horadus.python.horadus_workflow import _task_intake_backlog as backlog_support
from tools.horadus.python.horadus_workflow import _task_intake_mutations as mutation_support
from tools.horadus.python.horadus_workflow import _task_intake_promote as promote_support
from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow._task_intake_store import (
    _VALID_INTAKE_STATUSES,
    TaskIntakeMutationLockError,
    _find_entry,
    _load_task_intake_entries,
    _next_intake_id,
    _normalize_intake_id,
    _normalize_optional_task_id,
    _normalize_text_list,
    _parse_timestamp,
    _validate_intake_entry,
    _write_task_intake_entries,
)
from tools.horadus.python.horadus_workflow._task_intake_store import (
    task_intake_mutation_lock as _task_intake_mutation_lock,
)
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

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
    if dry_run:
        lines = [
            "Dry run: would promote task intake.",
            f"Intake id: {intake_id}",
            f"Would create task: {promoted_task_id}",
            f"Would update backlog: {_relative_display_path(backlog_path)}",
            f"Would update intake log: {_relative_display_path(log_path)}",
        ]
    else:
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


def _task_intake_recorded_result(
    *, entry: TaskIntakeEntry, log_path: Path, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
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


@dataclass(slots=True)
class _PreparedPromotion:
    backlog_path: Path
    promoted_task_id: str
    task_block: str
    updated_backlog: str
    updated_entries: list[TaskIntakeEntry]


def _task_intake_validation_error(
    *, failure_prefix: str, log_path: Path, dry_run: bool, exc: ValueError
) -> tuple[int, dict[str, object], list[str]]:
    return (
        ExitCode.VALIDATION_ERROR,
        {
            "dry_run": dry_run,
            "error": str(exc),
            "log_path": _relative_display_path(log_path),
        },
        [failure_prefix, str(exc)],
    )


def _task_intake_environment_error(
    *, failure_prefix: str, log_path: Path, dry_run: bool, exc: TaskIntakeMutationLockError
) -> tuple[int, dict[str, object], list[str]]:
    return (
        ExitCode.ENVIRONMENT_ERROR,
        {
            "dry_run": dry_run,
            "error": str(exc),
            "log_path": _relative_display_path(log_path),
        },
        [failure_prefix, str(exc)],
    )


def _prepare_promotion(
    *,
    entries: list[TaskIntakeEntry],
    intake_id: str,
    priority: str,
    estimate: str,
    acceptance_items: list[str],
    files: list[str] | None,
    description: list[str] | None,
    assessment_refs: list[str] | None,
    failure_prefix: str,
) -> _PreparedPromotion | tuple[int, dict[str, object], list[str]]:
    target_entry = _find_entry(entries, intake_id)
    if target_entry is None:
        return (
            ExitCode.NOT_FOUND,
            {"intake_id": intake_id},
            [failure_prefix, f"{intake_id} was not found."],
        )
    if target_entry.status != "pending":
        return (
            ExitCode.VALIDATION_ERROR,
            {"intake_id": intake_id, "status": target_entry.status},
            [
                failure_prefix,
                f"{intake_id} is {target_entry.status}; only pending entries can be promoted.",
            ],
        )

    backlog_path = task_repo.backlog_path()
    backlog_text = task_repo.read_text(backlog_path)
    promoted_task_id, backlog_with_incremented_id = _allocate_backlog_task_id(backlog_text)
    task_block = _render_backlog_task_block(
        task_id=promoted_task_id,
        title=target_entry.title,
        priority=priority,
        estimate=estimate,
        description=backlog_support._render_description_lines(description, target_entry.note),
        files=_normalize_text_list(files),
        acceptance_criteria=acceptance_items,
        assessment_refs=_normalize_text_list(assessment_refs),
    )
    return _PreparedPromotion(
        backlog_path=backlog_path,
        promoted_task_id=promoted_task_id,
        task_block=task_block,
        updated_backlog=_insert_backlog_task_block(backlog_with_incremented_id, task_block),
        updated_entries=promote_support.build_promoted_entries(
            entries,
            intake_id=intake_id,
            promoted_task_id=promoted_task_id,
        ),
    )


def task_intake_add_data(
    *,
    title: str,
    note: str,
    refs: list[str] | None,
    source_task: str | None,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    failure_prefix = "Task intake failed."
    title_text = title.strip()
    note_text = note.strip()
    if not title_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            [failure_prefix, "--title must not be empty."],
        )
    if "\n" in title_text or "\r" in title_text:
        return (
            ExitCode.VALIDATION_ERROR,
            {},
            [failure_prefix, "--title must be a single line."],
        )
    if not note_text:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, "--note must not be empty."])

    log_path = _task_intake_log_path()
    try:
        normalized_refs = _normalize_text_list(refs)
        source_task_id = (
            _normalize_optional_task_id(source_task)
            if source_task is not None
            else _detect_current_task_id()
        )
    except ValueError as exc:
        return _task_intake_validation_error(
            failure_prefix=failure_prefix,
            log_path=log_path,
            dry_run=dry_run,
            exc=exc,
        )

    try:
        entry = (
            mutation_support.build_pending_entry(
                log_path=log_path,
                title=title_text,
                note=note_text,
                refs=normalized_refs,
                source_task_id=source_task_id,
                recorded_at=_utc_timestamp(),
            )
            if dry_run
            else mutation_support.persist_pending_entry(
                log_path=log_path,
                title=title_text,
                note=note_text,
                refs=normalized_refs,
                source_task_id=source_task_id,
                recorded_at=_utc_timestamp(),
                mutation_lock=_task_intake_mutation_lock,
            )
        )
    except ValueError as exc:
        return _task_intake_validation_error(
            failure_prefix=failure_prefix,
            log_path=log_path,
            dry_run=dry_run,
            exc=exc,
        )
    except TaskIntakeMutationLockError as exc:
        return _task_intake_environment_error(
            failure_prefix=failure_prefix,
            log_path=log_path,
            dry_run=dry_run,
            exc=exc,
        )
    return _task_intake_recorded_result(
        entry=entry,
        log_path=log_path,
        dry_run=dry_run,
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
        notes = _normalize_text_list(append_notes)
        if dry_run:
            prepared = mutation_support.prepare_groom_update(
                entries=_load_task_intake_entries(log_path),
                normalized_ids=normalized_ids,
                action=action,
                notes=notes,
            )
        else:
            with _task_intake_mutation_lock(log_path):
                prepared = mutation_support.prepare_groom_update(
                    entries=_load_task_intake_entries(log_path),
                    normalized_ids=normalized_ids,
                    action=action,
                    notes=notes,
                )
                if isinstance(prepared, tuple):
                    return prepared
                _write_task_intake_entries(log_path, prepared.updated_entries)
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, ["Task intake grooming failed.", str(exc)])
    except TaskIntakeMutationLockError as exc:
        return _task_intake_environment_error(
            failure_prefix="Task intake grooming failed.",
            log_path=log_path,
            dry_run=dry_run,
            exc=exc,
        )
    if isinstance(prepared, tuple):
        return prepared

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
        if dry_run:
            prepared = _prepare_promotion(
                entries=_load_task_intake_entries(log_path),
                intake_id=normalized_intake_id,
                priority=priority_text,
                estimate=estimate_text,
                acceptance_items=acceptance_items,
                files=files,
                description=description,
                assessment_refs=assessment_refs,
                failure_prefix=failure_prefix,
            )
        else:
            with _task_intake_mutation_lock(log_path):
                prepared = _prepare_promotion(
                    entries=_load_task_intake_entries(log_path),
                    intake_id=normalized_intake_id,
                    priority=priority_text,
                    estimate=estimate_text,
                    acceptance_items=acceptance_items,
                    files=files,
                    description=description,
                    assessment_refs=assessment_refs,
                    failure_prefix=failure_prefix,
                )
                if isinstance(prepared, tuple):
                    return prepared
                promote_support.persist_promoted_intake(
                    backlog_path=prepared.backlog_path,
                    updated_backlog=prepared.updated_backlog,
                    log_path=log_path,
                    updated_entries=prepared.updated_entries,
                    write_entries=_write_task_intake_entries,
                )
    except ValueError as exc:
        return (ExitCode.VALIDATION_ERROR, {}, [failure_prefix, str(exc)])
    except TaskIntakeMutationLockError as exc:
        return _task_intake_environment_error(
            failure_prefix=failure_prefix,
            log_path=log_path,
            dry_run=dry_run,
            exc=exc,
        )
    if isinstance(prepared, tuple):
        return prepared

    return _promote_success_result(
        intake_id=normalized_intake_id,
        promoted_task_id=prepared.promoted_task_id,
        backlog_path=prepared.backlog_path,
        log_path=log_path,
        dry_run=dry_run,
        task_block=prepared.task_block,
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
    "_normalize_optional_task_id",
    "_parse_timestamp",
    "_render_backlog_task_block",
    "_task_intake_log_path",
    "_validate_intake_entry",
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
