from __future__ import annotations

import getpass
import json
import os
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode

_LOCK_METADATA_NAME = "metadata.json"


@dataclass(slots=True)
class AutomationLockInfo:
    path: str
    status: str
    exists: bool
    metadata_path: str | None = None
    lock_id: str | None = None
    acquired_at: str | None = None
    hostname: str | None = None
    username: str | None = None
    cwd: str | None = None
    owner_pid: int | None = None
    owner_pid_running: bool | None = None
    error: str | None = None


def _normalize_lock_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve(strict=False)


def _metadata_path(lock_path: Path) -> Path:
    return lock_path / _LOCK_METADATA_NAME


def _lock_metadata_payload(lock_path: Path, *, owner_pid: int | None) -> dict[str, object]:
    try:
        username = getpass.getuser()
    except OSError:
        username = "unknown"
    return {
        "lock_id": str(uuid.uuid4()),
        "acquired_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "hostname": socket.gethostname(),
        "username": username,
        "cwd": str(Path.cwd()),
        "path": str(lock_path),
        "owner_pid": owner_pid,
    }


def _write_metadata(metadata_path: Path, payload: dict[str, object]) -> None:
    handle = os.open(metadata_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _owner_pid_running(owner_pid: int | None) -> bool | None:
    if owner_pid is None:
        return None
    if owner_pid <= 0:
        return False
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _load_lock_info(lock_path: Path) -> AutomationLockInfo:
    if not lock_path.exists():
        return AutomationLockInfo(path=str(lock_path), status="available", exists=False)
    if not lock_path.is_file():
        return AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            error="lock path exists but is not a regular file",
        )

    metadata_path = lock_path
    if not metadata_path.is_file():
        return AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            metadata_path=str(metadata_path),
            error=f"missing {_LOCK_METADATA_NAME}",
        )

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            metadata_path=str(metadata_path),
            error=f"invalid {_LOCK_METADATA_NAME}: {exc}",
        )

    if not isinstance(payload, dict):
        return AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            metadata_path=str(metadata_path),
            error=f"invalid {_LOCK_METADATA_NAME}: expected a JSON object",
        )

    raw_owner_pid = payload.get("owner_pid")
    if raw_owner_pid is not None and not isinstance(raw_owner_pid, int):
        return AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            metadata_path=str(metadata_path),
            error=f"invalid {_LOCK_METADATA_NAME}: expected integer owner_pid",
        )
    owner_pid = raw_owner_pid if isinstance(raw_owner_pid, int) else None
    owner_pid_running = _owner_pid_running(owner_pid)
    status = "stale" if owner_pid is not None and owner_pid_running is False else "held"

    return AutomationLockInfo(
        path=str(lock_path),
        status=status,
        exists=True,
        metadata_path=str(metadata_path),
        lock_id=str(payload.get("lock_id")) if payload.get("lock_id") is not None else None,
        acquired_at=(
            str(payload.get("acquired_at")) if payload.get("acquired_at") is not None else None
        ),
        hostname=str(payload.get("hostname")) if payload.get("hostname") is not None else None,
        username=str(payload.get("username")) if payload.get("username") is not None else None,
        cwd=str(payload.get("cwd")) if payload.get("cwd") is not None else None,
        owner_pid=owner_pid,
        owner_pid_running=owner_pid_running,
    )


def _check_lines(info: AutomationLockInfo) -> list[str]:
    if info.status == "available":
        return [f"Automation lock is available: {info.path}"]

    lines = [f"Automation lock status: {info.status}", f"- path: {info.path}"]
    if info.metadata_path is not None:
        lines.append(f"- metadata: {info.metadata_path}")
    if info.lock_id is not None:
        lines.append(f"- lock_id: {info.lock_id}")
    if info.acquired_at is not None:
        lines.append(f"- acquired_at: {info.acquired_at}")
    if info.hostname is not None:
        lines.append(f"- hostname: {info.hostname}")
    if info.username is not None:
        lines.append(f"- username: {info.username}")
    if info.cwd is not None:
        lines.append(f"- cwd: {info.cwd}")
    if info.owner_pid is not None:
        lines.append(f"- owner_pid: {info.owner_pid}")
    if info.owner_pid_running is not None:
        lines.append(f"- owner_pid_running: {'yes' if info.owner_pid_running else 'no'}")
    if info.error is not None:
        lines.append(f"- error: {info.error}")
    return lines


def _lock_environment_error(
    lock_path: Path,
    *,
    info: AutomationLockInfo | None = None,
    message: str,
    exc: OSError,
) -> tuple[int, dict[str, object], list[str]]:
    if info is not None:
        data = asdict(info) | {"dry_run": False, "error": str(exc)}
    else:
        data = {
            "path": str(lock_path),
            "status": "error",
            "dry_run": False,
            "error": str(exc),
        }
    return (
        ExitCode.ENVIRONMENT_ERROR,
        data,
        [
            "Automation lock acquisition failed.",
            message,
            str(exc),
        ],
    )


def _lock_validation_error(
    info: AutomationLockInfo,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, object], list[str]]:
    return (
        ExitCode.VALIDATION_ERROR,
        asdict(info) | {"dry_run": dry_run},
        [
            "Automation lock acquisition failed.",
            *_check_lines(info),
        ],
    )


def _clear_stale_lock(
    lock_path: Path,
    *,
    info: AutomationLockInfo,
) -> tuple[bool, tuple[int, dict[str, object], list[str]] | None]:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return (True, None)
    except OSError as exc:
        return (
            False,
            _lock_environment_error(
                lock_path,
                info=info,
                message=f"Unable to clear the stale lock file: {lock_path}",
                exc=exc,
            ),
        )
    return (True, None)


def _attempt_lock_publish(
    lock_path: Path,
    *,
    owner_pid: int | None,
) -> tuple[str, tuple[int, dict[str, object], list[str]] | None]:
    temp_path = lock_path.with_name(f".{lock_path.name}.tmp-{uuid.uuid4().hex}")
    payload = _lock_metadata_payload(lock_path, owner_pid=owner_pid)
    try:
        _write_metadata(temp_path, payload)
        os.link(temp_path, lock_path)
    except FileExistsError:
        return ("exists", None)
    except OSError as exc:
        return (
            "error",
            _lock_environment_error(
                lock_path,
                message=f"Unable to write lock metadata for {lock_path}.",
                exc=exc,
            ),
        )
    finally:
        temp_path.unlink(missing_ok=True)

    info = _load_lock_info(lock_path)
    return (
        "acquired",
        (
            ExitCode.OK,
            asdict(info) | {"dry_run": False},
            [
                f"Automation lock acquired: {info.path}",
                *_check_lines(info)[1:],
            ],
        ),
    )


def automation_lock_check_data(
    path_value: str, *, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    lock_path = _normalize_lock_path(path_value)
    info = _load_lock_info(lock_path)
    lines = _check_lines(info)
    if dry_run:
        lines.append("Dry run: inspected the current lock state without changing it.")
    exit_code = ExitCode.OK if info.status != "broken" else ExitCode.VALIDATION_ERROR
    return (exit_code, asdict(info) | {"dry_run": dry_run}, lines)


def automation_lock_lock_data(
    path_value: str, *, owner_pid: int | None, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    lock_path = _normalize_lock_path(path_value)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _lock_environment_error(
            lock_path,
            message=f"Unable to prepare the lock path: {lock_path}",
            exc=exc,
        )

    while True:
        info = _load_lock_info(lock_path)
        if info.status == "stale":
            if dry_run:
                return (
                    ExitCode.OK,
                    asdict(info) | {"dry_run": True},
                    [
                        *_check_lines(info),
                        f"Dry run: would replace the stale automation lock at {info.path}.",
                    ],
                )
            can_retry, stale_result = _clear_stale_lock(lock_path, info=info)
            if not can_retry:
                assert stale_result is not None
                return stale_result
            continue
        if info.status != "available":
            return _lock_validation_error(info, dry_run=dry_run)
        if dry_run:
            return (
                ExitCode.OK,
                asdict(info) | {"dry_run": True, "status": "available"},
                [
                    f"Automation lock is available: {info.path}",
                    f"Dry run: would acquire the automation lock at {info.path}.",
                ],
            )

        publish_state, publish_result = _attempt_lock_publish(lock_path, owner_pid=owner_pid)
        if publish_state == "acquired":
            assert publish_result is not None
            return publish_result
        if publish_state == "error":
            assert publish_result is not None
            return publish_result

        info = _load_lock_info(lock_path)
        if info.status == "stale":
            can_retry, stale_result = _clear_stale_lock(lock_path, info=info)
            if not can_retry:
                assert stale_result is not None
                return stale_result
            continue
        return _lock_validation_error(info, dry_run=False)


def automation_lock_unlock_data(
    path_value: str, *, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    lock_path = _normalize_lock_path(path_value)
    info = _load_lock_info(lock_path)

    if dry_run:
        return (
            ExitCode.OK,
            asdict(info) | {"dry_run": True},
            [
                *_check_lines(info),
                f"Dry run: would release the automation lock at {info.path}.",
            ],
        )

    if not lock_path.exists():
        return (
            ExitCode.OK,
            asdict(info) | {"dry_run": False, "status": "available"},
            [f"Automation lock was already absent: {info.path}"],
        )

    if lock_path.is_file():
        lock_path.unlink()
        return (
            ExitCode.OK,
            {
                "path": str(lock_path),
                "status": "released",
                "dry_run": False,
                "removed_file": True,
            },
            [f"Automation lock file removed: {lock_path}"],
        )

    if not lock_path.is_dir():
        return (
            ExitCode.VALIDATION_ERROR,
            asdict(info) | {"dry_run": False},
            [
                "Automation lock release failed.",
                *_check_lines(info),
            ],
        )

    metadata_path = _metadata_path(lock_path)
    unexpected_entries = sorted(
        entry.name for entry in lock_path.iterdir() if entry.name != _LOCK_METADATA_NAME
    )
    if unexpected_entries:
        return (
            ExitCode.VALIDATION_ERROR,
            asdict(info) | {"dry_run": False, "unexpected_entries": unexpected_entries},
            [
                "Automation lock release failed.",
                f"Lock directory contains unexpected entries: {', '.join(unexpected_entries)}",
            ],
        )

    if metadata_path.exists():
        metadata_path.unlink()
    lock_path.rmdir()
    return (
        ExitCode.OK,
        {
            "path": str(lock_path),
            "status": "released",
            "dry_run": False,
            "removed_file": False,
        },
        [f"Automation lock released: {lock_path}"],
    )


def handle_automation_lock_check(args: Any) -> CommandResult:
    exit_code, data, lines = automation_lock_check_data(args.path, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_automation_lock_lock(args: Any) -> CommandResult:
    exit_code, data, lines = automation_lock_lock_data(
        args.path,
        owner_pid=getattr(args, "owner_pid", None),
        dry_run=bool(args.dry_run),
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def handle_automation_lock_unlock(args: Any) -> CommandResult:
    exit_code, data, lines = automation_lock_unlock_data(args.path, dry_run=bool(args.dry_run))
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


__all__ = [
    "AutomationLockInfo",
    "_check_lines",
    "_load_lock_info",
    "_lock_metadata_payload",
    "_metadata_path",
    "_normalize_lock_path",
    "_write_metadata",
    "automation_lock_check_data",
    "automation_lock_lock_data",
    "automation_lock_unlock_data",
    "handle_automation_lock_check",
    "handle_automation_lock_lock",
    "handle_automation_lock_unlock",
]
