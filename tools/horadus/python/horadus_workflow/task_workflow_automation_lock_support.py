from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    owner_started_at: str | None = None
    owner_pid_running: bool | None = None
    owner_pid_identity_matches: bool | None = None
    legacy_lock_active: bool | None = None
    error: str | None = None


def metadata_path(lock_path: Path) -> Path:
    return lock_path / _LOCK_METADATA_NAME


def normalize_lock_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve(strict=False)


def codex_home_path(*, environ: Mapping[str, str], home_path: Callable[[], Path]) -> Path:
    codex_home = environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve(strict=False)
    return (home_path() / ".codex").resolve(strict=False)


def validate_lock_path(lock_path: Path, *, codex_home: Path) -> str | None:
    try:
        relative_path = lock_path.relative_to(codex_home)
    except ValueError:
        return (
            "Automation lock path must stay under "
            f"{codex_home / 'automations' / '<automation-id>' / 'lock'}."
        )
    parts = relative_path.parts
    if len(parts) != 3 or parts[0] != "automations" or parts[2] != "lock" or not parts[1]:
        return (
            "Automation lock path must use the "
            f"{codex_home / 'automations' / '<automation-id>' / 'lock'} contract."
        )
    return None


def automation_lock_path_arg(
    *, path_value: str | None, automation_id: str | None, codex_home: Path
) -> str:
    if automation_id:
        return str((codex_home / "automations" / automation_id / "lock").resolve(strict=False))
    if path_value is None:
        raise ValueError("automation lock target is required")
    return path_value


def unlock_block_reason(info: AutomationLockInfo, *, owner_pid: int | None) -> str | None:
    if info.status == "legacy" and info.legacy_lock_active is not False:
        return (
            "Unlock requires the active legacy flock holder to exit before cleanup."
            if info.legacy_lock_active
            else "Unlock requires manual review because legacy flock status is indeterminate."
        )
    if info.status != "held":
        return None
    if info.owner_pid is None:
        return "Unlock requires manual review because the live automation lock has no recorded owner PID."
    if owner_pid is None:
        return "Unlock requires --owner-pid to release a live automation lock."
    if owner_pid != info.owner_pid:
        return f"Unlock owner mismatch: lock is owned by pid {info.owner_pid}, not {owner_pid}."
    return None


def lock_metadata_payload(
    lock_path: Path,
    *,
    owner_pid: int | None,
    username: str,
    hostname: str,
    cwd: Path,
    acquired_at: str,
    owner_started_at: str | None,
) -> dict[str, object]:
    return {
        "lock_id": str(uuid.uuid4()),
        "acquired_at": acquired_at,
        "hostname": hostname,
        "username": username,
        "cwd": str(cwd),
        "path": str(lock_path),
        "owner_pid": owner_pid,
        "owner_started_at": owner_started_at,
    }


def write_metadata(metadata_path_value: Path, payload: dict[str, object]) -> None:
    handle = os.open(metadata_path_value, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def owner_pid_running(
    owner_pid: int | None,
    *,
    os_name: str,
    kill: Callable[[int, int], None],
    run_process: Callable[..., Any] | None = None,
) -> bool | None:
    if owner_pid is None:
        return None
    if owner_pid <= 0:
        return False
    if os_name == "nt":
        if run_process is None:
            return None
        try:
            result = run_process(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f"$p = Get-Process -Id {owner_pid} -ErrorAction SilentlyContinue; "
                        "if ($null -eq $p) { exit 1 } else { exit 0 }"
                    ),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:
            return None
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        return None
    try:
        kill(owner_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def owner_pid_started_at(
    owner_pid: int | None,
    *,
    os_name: str,
    run_ps: Callable[..., Any],
) -> str | None:
    if owner_pid is None or owner_pid <= 0 or os_name == "nt":
        return None
    try:
        result = run_ps(
            ["ps", "-p", str(owner_pid), "-o", "lstart="],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    started_at = " ".join(result.stdout.split())
    return started_at or None


def looks_like_legacy_flock_lock(raw_content: str) -> bool:
    return raw_content.strip() == ""


def legacy_flock_lock_active(
    lock_path: Path,
    *,
    fcntl_module: Any,
    os_module: Any,
) -> bool | None:
    if fcntl_module is None:
        return None
    try:
        handle = os_module.open(lock_path, os.O_RDWR)
    except OSError:
        return None
    try:
        try:
            fcntl_module.flock(handle, fcntl_module.LOCK_EX | fcntl_module.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return None
        try:
            fcntl_module.flock(handle, fcntl_module.LOCK_UN)
        except OSError:
            return None
        return False
    finally:
        os_module.close(handle)


def acquire_legacy_flock_handle(
    lock_path: Path, *, fcntl_module: Any, os_module: Any
) -> int | None:
    if fcntl_module is None:
        return None
    try:
        handle = os_module.open(lock_path, os.O_RDWR)
    except OSError:
        return None
    try:
        fcntl_module.flock(handle, fcntl_module.LOCK_EX | fcntl_module.LOCK_NB)
    except (BlockingIOError, OSError):
        os_module.close(handle)
        return None
    return int(handle)


def release_legacy_flock_handle(handle: int, *, fcntl_module: Any, os_module: Any) -> None:
    try:
        if fcntl_module is not None:
            fcntl_module.flock(handle, fcntl_module.LOCK_UN)
    except OSError:
        pass
    finally:
        os_module.close(handle)


def _metadata_path_value(path_value: Path | None) -> str | None:
    return str(path_value) if path_value is not None else None


def _lock_info(
    lock_path: Path,
    status: str,
    exists: bool,
    *,
    metadata_path: str | None = None,
    lock_id: str | None = None,
    acquired_at: str | None = None,
    hostname: str | None = None,
    username: str | None = None,
    cwd: str | None = None,
    owner_pid: int | None = None,
    owner_started_at: str | None = None,
    owner_pid_running: bool | None = None,
    owner_pid_identity_matches: bool | None = None,
    legacy_lock_active: bool | None = None,
    error: str | None = None,
) -> AutomationLockInfo:
    return AutomationLockInfo(
        path=str(lock_path),
        status=status,
        exists=exists,
        metadata_path=metadata_path,
        lock_id=lock_id,
        acquired_at=acquired_at,
        hostname=hostname,
        username=username,
        cwd=cwd,
        owner_pid=owner_pid,
        owner_started_at=owner_started_at,
        owner_pid_running=owner_pid_running,
        owner_pid_identity_matches=owner_pid_identity_matches,
        legacy_lock_active=legacy_lock_active,
        error=error,
    )


def _broken_lock_info(
    lock_path: Path,
    *,
    error: str,
    metadata_path_value: Path | None = None,
) -> AutomationLockInfo:
    return _lock_info(
        lock_path,
        "broken",
        True,
        metadata_path=_metadata_path_value(metadata_path_value),
        error=error,
    )


def _legacy_lock_info(
    lock_path: Path,
    *,
    metadata_path_value: Path,
    legacy_lock_active_value: bool | None,
) -> AutomationLockInfo:
    return _lock_info(
        lock_path,
        "legacy",
        True,
        metadata_path=str(metadata_path_value),
        legacy_lock_active=legacy_lock_active_value,
        error="legacy flock lock file",
    )


def _load_payload_mapping(
    lock_path: Path,
    metadata_path_value: Path,
    *,
    legacy_lock_active_fn: Callable[[Path], bool | None],
) -> tuple[dict[str, object] | None, AutomationLockInfo | None]:
    try:
        raw_payload = metadata_path_value.read_text(encoding="utf-8")
    except OSError as exc:
        return (
            None,
            _broken_lock_info(
                lock_path,
                metadata_path_value=metadata_path_value,
                error=f"invalid {_LOCK_METADATA_NAME}: {exc}",
            ),
        )
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        if looks_like_legacy_flock_lock(raw_payload):
            return (
                None,
                _legacy_lock_info(
                    lock_path,
                    metadata_path_value=metadata_path_value,
                    legacy_lock_active_value=legacy_lock_active_fn(lock_path),
                ),
            )
        return (
            None,
            _broken_lock_info(
                lock_path,
                metadata_path_value=metadata_path_value,
                error=f"invalid {_LOCK_METADATA_NAME}: {exc}",
            ),
        )
    if not isinstance(payload, dict):
        return (
            None,
            _broken_lock_info(
                lock_path,
                metadata_path_value=metadata_path_value,
                error=f"invalid {_LOCK_METADATA_NAME}: expected a JSON object",
            ),
        )
    return (payload, None)


def _required_payload_string(
    lock_path: Path,
    *,
    metadata_path_value: Path,
    payload: dict[str, object],
    key: str,
) -> tuple[str | None, AutomationLockInfo | None]:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return (value, None)
    return (
        None,
        _broken_lock_info(
            lock_path,
            metadata_path_value=metadata_path_value,
            error=f"invalid {_LOCK_METADATA_NAME}: expected non-empty string {key}",
        ),
    )


def _owner_identity_state(
    lock_path: Path,
    *,
    metadata_path_value: Path,
    payload: dict[str, object],
    owner_pid_running_fn: Callable[[int | None], bool | None],
    owner_pid_started_at_fn: Callable[[int | None], str | None],
) -> tuple[int | None, str | None, bool | None, bool | None, AutomationLockInfo | None]:
    raw_owner_pid = payload.get("owner_pid")
    if raw_owner_pid is not None and not isinstance(raw_owner_pid, int):
        return (
            None,
            None,
            None,
            None,
            _broken_lock_info(
                lock_path,
                metadata_path_value=metadata_path_value,
                error=f"invalid {_LOCK_METADATA_NAME}: expected integer owner_pid",
            ),
        )
    raw_owner_started_at = payload.get("owner_started_at")
    if raw_owner_started_at is not None and not isinstance(raw_owner_started_at, str):
        return (
            None,
            None,
            None,
            None,
            _broken_lock_info(
                lock_path,
                metadata_path_value=metadata_path_value,
                error=f"invalid {_LOCK_METADATA_NAME}: expected string owner_started_at",
            ),
        )
    owner_pid = raw_owner_pid if isinstance(raw_owner_pid, int) else None
    owner_started_at_value = raw_owner_started_at if isinstance(raw_owner_started_at, str) else None
    owner_pid_running_value = owner_pid_running_fn(owner_pid)
    owner_pid_identity_matches: bool | None = None
    if owner_pid is not None and owner_pid_running_value:
        current_owner_started_at = owner_pid_started_at_fn(owner_pid)
        if owner_started_at_value is not None and current_owner_started_at is not None:
            owner_pid_identity_matches = current_owner_started_at == owner_started_at_value
    return (
        owner_pid,
        owner_started_at_value,
        owner_pid_running_value,
        owner_pid_identity_matches,
        None,
    )


def _payload_metadata_state(
    lock_path: Path,
    *,
    metadata_path_value: Path,
    payload: dict[str, object],
) -> tuple[str, str, str, str, str, str, AutomationLockInfo | None]:
    values: list[str] = []
    for key in ("lock_id", "acquired_at", "hostname", "username", "cwd"):
        value, error = _required_payload_string(
            lock_path,
            metadata_path_value=metadata_path_value,
            payload=payload,
            key=key,
        )
        if error is not None:
            return ("", "", "", "", "", "", error)
        assert value is not None
        values.append(value)
    path_value, path_error = _required_payload_string(
        lock_path,
        metadata_path_value=metadata_path_value,
        payload=payload,
        key="path",
    )
    if path_error is not None:
        return ("", "", "", "", "", "", path_error)
    assert path_value is not None
    return (values[0], values[1], values[2], values[3], values[4], path_value, None)


def load_lock_info(
    lock_path: Path,
    *,
    legacy_lock_active_fn: Callable[[Path], bool | None],
    owner_pid_running_fn: Callable[[int | None], bool | None],
    owner_pid_started_at_fn: Callable[[int | None], str | None],
) -> AutomationLockInfo:
    if not lock_path.exists():
        return _lock_info(lock_path, "available", False)
    if not lock_path.is_file():
        return _broken_lock_info(lock_path, error="lock path exists but is not a regular file")

    metadata_path_value = lock_path
    if not metadata_path_value.is_file():
        return _broken_lock_info(
            lock_path,
            metadata_path_value=metadata_path_value,
            error=f"missing {_LOCK_METADATA_NAME}",
        )
    payload, payload_error = _load_payload_mapping(
        lock_path,
        metadata_path_value,
        legacy_lock_active_fn=legacy_lock_active_fn,
    )
    if payload_error is not None:
        return payload_error
    assert payload is not None
    (
        lock_id_value,
        acquired_at_value,
        hostname_value,
        username_value,
        cwd_value,
        _path_value,
        payload_metadata_error,
    ) = _payload_metadata_state(
        lock_path,
        metadata_path_value=metadata_path_value,
        payload=payload,
    )
    if payload_metadata_error is not None:
        return payload_metadata_error
    (
        owner_pid,
        owner_started_at_value,
        owner_pid_running_value,
        owner_pid_identity_matches,
        owner_identity_error,
    ) = _owner_identity_state(
        lock_path,
        metadata_path_value=metadata_path_value,
        payload=payload,
        owner_pid_running_fn=owner_pid_running_fn,
        owner_pid_started_at_fn=owner_pid_started_at_fn,
    )
    if owner_identity_error is not None:
        return owner_identity_error
    status = "held"
    if owner_pid is not None and (
        owner_pid_running_value is False or owner_pid_identity_matches is False
    ):
        status = "stale"
    return _lock_info(
        lock_path,
        status,
        True,
        metadata_path=str(metadata_path_value),
        lock_id=lock_id_value,
        acquired_at=acquired_at_value,
        hostname=hostname_value,
        username=username_value,
        cwd=cwd_value,
        owner_pid=owner_pid,
        owner_started_at=owner_started_at_value,
        owner_pid_running=owner_pid_running_value,
        owner_pid_identity_matches=owner_pid_identity_matches,
        legacy_lock_active=None,
        error=None,
    )


def check_lines(info: AutomationLockInfo) -> list[str]:
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
    if info.owner_started_at is not None:
        lines.append(f"- owner_started_at: {info.owner_started_at}")
    if info.owner_pid_running is not None:
        lines.append(f"- owner_pid_running: {'yes' if info.owner_pid_running else 'no'}")
    if info.owner_pid_identity_matches is not None:
        lines.append(
            f"- owner_pid_identity_matches: {'yes' if info.owner_pid_identity_matches else 'no'}"
        )
    if info.legacy_lock_active is not None:
        lines.append(f"- legacy_lock_active: {'yes' if info.legacy_lock_active else 'no'}")
    if info.error is not None:
        lines.append(f"- error: {info.error}")
    return lines
