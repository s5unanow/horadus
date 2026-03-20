from __future__ import annotations

import getpass
import os
import socket
import subprocess  # nosec B404 - fixed argv `ps` probe only; no shell execution.
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    AutomationLockInfo,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    acquire_legacy_flock_handle as _support_acquire_legacy_flock_handle,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    check_lines as _support_check_lines,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    codex_home_path as _support_codex_home_path,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    legacy_flock_lock_active as _support_legacy_flock_lock_active,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    load_lock_info as _support_load_lock_info,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    lock_metadata_payload as _support_lock_metadata_payload,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    looks_like_legacy_flock_lock as _support_looks_like_legacy_flock_lock,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    metadata_path as _support_metadata_path,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    normalize_lock_path as _support_normalize_lock_path,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    owner_pid_running as _support_owner_pid_running,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    owner_pid_started_at as _support_owner_pid_started_at,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    release_legacy_flock_handle as _support_release_legacy_flock_handle,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    validate_lock_path as _support_validate_lock_path,
)
from tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support import (
    write_metadata as _support_write_metadata,
)

_fcntl: Any
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - unavailable on Windows.
    _fcntl = None

fcntl = _fcntl

_LOCK_METADATA_NAME = "metadata.json"


def _normalize_lock_path(path_value: str) -> Path:
    return _support_normalize_lock_path(path_value)


def _metadata_path(lock_path: Path) -> Path:
    return _support_metadata_path(lock_path)


def _codex_home_path() -> Path:
    return _support_codex_home_path(environ=os.environ, home_path=Path.home)


def _validate_lock_path(lock_path: Path) -> str | None:
    return _support_validate_lock_path(lock_path, codex_home=_codex_home_path())


def _lock_metadata_payload(lock_path: Path, *, owner_pid: int | None) -> dict[str, object]:
    try:
        username = getpass.getuser()
    except OSError:
        username = "unknown"
    return _support_lock_metadata_payload(
        lock_path,
        owner_pid=owner_pid,
        username=username,
        hostname=socket.gethostname(),
        cwd=Path.cwd(),
        acquired_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        owner_started_at=_owner_pid_started_at(owner_pid),
    )


def _write_metadata(metadata_path: Path, payload: dict[str, object]) -> None:
    _support_write_metadata(metadata_path, payload)


def _owner_pid_running(owner_pid: int | None) -> bool | None:
    return _support_owner_pid_running(owner_pid, os_name=os.name, kill=os.kill)


def _owner_pid_started_at(owner_pid: int | None) -> str | None:
    return _support_owner_pid_started_at(owner_pid, os_name=os.name, run_ps=subprocess.run)


def _looks_like_legacy_flock_lock(raw_content: str) -> bool:
    return _support_looks_like_legacy_flock_lock(raw_content)


def _legacy_flock_lock_active(lock_path: Path) -> bool | None:
    return _support_legacy_flock_lock_active(lock_path, fcntl_module=fcntl, os_module=os)


def _acquire_legacy_flock_handle(lock_path: Path) -> int | None:
    return _support_acquire_legacy_flock_handle(lock_path, fcntl_module=fcntl, os_module=os)


def _release_legacy_flock_handle(handle: int) -> None:
    _support_release_legacy_flock_handle(handle, fcntl_module=fcntl, os_module=os)


def _legacy_handle_matches_current_path(lock_path: Path, legacy_handle: int) -> bool:
    try:
        current_stat = lock_path.stat()
    except FileNotFoundError:
        return False
    held_stat = os.fstat(legacy_handle)
    return current_stat.st_dev == held_stat.st_dev and current_stat.st_ino == held_stat.st_ino


def _load_lock_info(lock_path: Path) -> AutomationLockInfo:
    return _support_load_lock_info(
        lock_path,
        legacy_lock_active_fn=_legacy_flock_lock_active,
        owner_pid_running_fn=_owner_pid_running,
        owner_pid_started_at_fn=_owner_pid_started_at,
    )


def _check_lines(info: AutomationLockInfo) -> list[str]:
    return _support_check_lines(info)


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


def _unlock_validation_error(
    info: AutomationLockInfo,
    *,
    message: str | None = None,
) -> tuple[int, dict[str, object], list[str]]:
    lines = ["Automation lock release failed."]
    if message is not None:
        lines.append(message)
    else:
        lines.extend(_check_lines(info))
    return (ExitCode.VALIDATION_ERROR, asdict(info) | {"dry_run": False}, lines)


def _unlock_environment_error(
    *,
    info: AutomationLockInfo,
    message: str,
    exc: OSError,
) -> tuple[int, dict[str, object], list[str]]:
    return (
        ExitCode.ENVIRONMENT_ERROR,
        asdict(info) | {"dry_run": False, "error": str(exc)},
        [
            "Automation lock release failed.",
            message,
            str(exc),
        ],
    )


def _unlock_file_lock(
    lock_path: Path,
    *,
    info: AutomationLockInfo,
    owner_pid: int | None,
) -> tuple[int, dict[str, object], list[str]]:
    if info.status == "broken":
        return _unlock_validation_error(info)
    if info.status == "legacy" and info.legacy_lock_active is not False:
        return _unlock_validation_error(
            info,
            message=(
                "Unlock requires the active legacy flock holder to exit before cleanup."
                if info.legacy_lock_active
                else "Unlock requires manual review because legacy flock status is indeterminate."
            ),
        )
    if info.status == "held" and info.owner_pid is not None:
        if owner_pid is None:
            return _unlock_validation_error(
                info,
                message="Unlock requires --owner-pid to release a live automation lock.",
            )
        if owner_pid != info.owner_pid:
            return _unlock_validation_error(
                info,
                message=f"Unlock owner mismatch: lock is owned by pid {info.owner_pid}, not {owner_pid}.",
            )
    try:
        lock_path.unlink()
    except OSError as exc:
        return _unlock_environment_error(
            info=info,
            message=f"Unable to remove the automation lock file: {lock_path}",
            exc=exc,
        )
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


def _unlock_directory_lock(
    lock_path: Path,
    *,
    info: AutomationLockInfo,
) -> tuple[int, dict[str, object], list[str]]:
    metadata_path = _metadata_path(lock_path)
    try:
        unexpected_entries = sorted(
            entry.name for entry in lock_path.iterdir() if entry.name != _LOCK_METADATA_NAME
        )
    except OSError as exc:
        return _unlock_environment_error(
            info=info,
            message=f"Unable to inspect the automation lock directory: {lock_path}",
            exc=exc,
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
    try:
        if metadata_path.exists():
            metadata_path.unlink()
        lock_path.rmdir()
    except OSError as exc:
        return _unlock_environment_error(
            info=info,
            message=f"Unable to remove the automation lock directory: {lock_path}",
            exc=exc,
        )
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
    path_error = _validate_lock_path(lock_path)
    if path_error is not None:
        info = AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=lock_path.exists(),
            error=path_error,
        )
        lines = _check_lines(info)
        if dry_run:
            lines.append("Dry run: inspected the current lock state without changing it.")
        return (ExitCode.VALIDATION_ERROR, asdict(info) | {"dry_run": dry_run}, lines)
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
    path_error = _validate_lock_path(lock_path)
    if path_error is not None:
        info = AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=lock_path.exists(),
            error=path_error,
        )
        return _lock_validation_error(info, dry_run=dry_run)
    info = _load_lock_info(lock_path)
    if dry_run:
        if info.status == "legacy" and info.legacy_lock_active is False:
            return (
                ExitCode.OK,
                asdict(info) | {"dry_run": True},
                [
                    *_check_lines(info),
                    f"Dry run: would replace the inactive legacy automation lock at {info.path}.",
                ],
            )
        if info.status != "available":
            return _lock_validation_error(info, dry_run=True)
        return (
            ExitCode.OK,
            asdict(info) | {"dry_run": True, "status": "available"},
            [
                f"Automation lock is available: {info.path}",
                f"Dry run: would acquire the automation lock at {info.path}.",
            ],
        )

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _lock_environment_error(
            lock_path,
            message=f"Unable to prepare the lock path: {lock_path}",
            exc=exc,
        )

    info = _load_lock_info(lock_path)
    legacy_handle: int | None = None
    if info.status == "legacy":
        if info.legacy_lock_active is not False:
            return _lock_validation_error(info, dry_run=dry_run)
        legacy_handle = _acquire_legacy_flock_handle(lock_path)
        if legacy_handle is None:
            info = _load_lock_info(lock_path)
            return _lock_validation_error(info, dry_run=dry_run)
        try:
            try:
                legacy_handle_matches_path = _legacy_handle_matches_current_path(
                    lock_path, legacy_handle
                )
            except OSError as exc:
                return _lock_environment_error(
                    lock_path,
                    info=info,
                    message=f"Unable to verify the legacy lock file before cleanup: {lock_path}",
                    exc=exc,
                )
            if not legacy_handle_matches_path:
                info = _load_lock_info(lock_path)
            else:
                try:
                    lock_path.unlink()
                except OSError as exc:
                    return _lock_environment_error(
                        lock_path,
                        info=info,
                        message=f"Unable to clear the inactive legacy lock file: {lock_path}",
                        exc=exc,
                    )
                info = _load_lock_info(lock_path)
        finally:
            _release_legacy_flock_handle(legacy_handle)
    if info.status != "available":
        return _lock_validation_error(info, dry_run=dry_run)

    publish_state, publish_result = _attempt_lock_publish(lock_path, owner_pid=owner_pid)
    if publish_state == "acquired":
        assert publish_result is not None
        return publish_result
    if publish_state == "error":
        assert publish_result is not None
        return publish_result

    info = _load_lock_info(lock_path)
    return _lock_validation_error(info, dry_run=False)


def automation_lock_unlock_data(
    path_value: str, *, owner_pid: int | None, dry_run: bool
) -> tuple[int, dict[str, object], list[str]]:
    lock_path = _normalize_lock_path(path_value)
    path_error = _validate_lock_path(lock_path)
    if path_error is not None:
        info = AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=lock_path.exists(),
            error=path_error,
        )
        if dry_run:
            return (
                ExitCode.VALIDATION_ERROR,
                asdict(info) | {"dry_run": True},
                [
                    *_check_lines(info),
                    f"Dry run: would release the automation lock at {info.path}.",
                ],
            )
        return (
            ExitCode.VALIDATION_ERROR,
            asdict(info) | {"dry_run": False},
            [
                "Automation lock release failed.",
                *_check_lines(info),
            ],
        )
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
        return _unlock_file_lock(lock_path, info=info, owner_pid=owner_pid)

    if not lock_path.is_dir():
        return (
            ExitCode.VALIDATION_ERROR,
            asdict(info) | {"dry_run": False},
            [
                "Automation lock release failed.",
                *_check_lines(info),
            ],
        )

    return _unlock_directory_lock(lock_path, info=info)


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
    exit_code, data, lines = automation_lock_unlock_data(
        args.path,
        owner_pid=getattr(args, "owner_pid", None),
        dry_run=bool(args.dry_run),
    )
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
