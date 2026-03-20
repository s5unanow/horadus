from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_automation_lock as automation_lock_module
import tools.horadus.python.horadus_workflow.task_workflow_automation_lock as automation_lock_impl
import tools.horadus.python.horadus_workflow.task_workflow_automation_lock_support as automation_lock_support

pytestmark = pytest.mark.unit


def _automation_lock_path(tmp_path: Path, automation_id: str = "test-automation") -> Path:
    return tmp_path / ".codex" / "automations" / automation_id / "lock"


@pytest.fixture(autouse=True)
def _set_test_codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.setattr(automation_lock_impl.socket, "gethostname", lambda: "host")


def _write_lock_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_lock_payload(path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "lock_id": "test-lock",
        "acquired_at": "2026-03-20T00:00:00+00:00",
        "hostname": "host",
        "username": "user",
        "cwd": "/tmp",
        "path": str(path),
        "owner_pid": None,
        "owner_started_at": None,
    }
    payload.update(overrides)
    return payload


def test_automation_lock_check_reports_available_path(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=True
    )

    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "available"
    assert data["dry_run"] is True
    assert not lock_path.parent.exists()
    assert lines == [
        f"Automation lock is available: {lock_path}",
        "Dry run: inspected the current lock state without changing it.",
    ]


def test_automation_lock_codex_home_path_falls_back_to_home_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.setattr(automation_lock_impl.Path, "home", lambda: tmp_path)

    assert automation_lock_impl._codex_home_path() == (tmp_path / ".codex").resolve(strict=False)


def test_automation_lock_lock_and_unlock_round_trip(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)

    lock_exit_code, lock_data, lock_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert lock_exit_code == automation_lock_module.ExitCode.OK
    assert lock_data["status"] == "held"
    assert lock_path.is_file()
    metadata = json.loads(lock_path.read_text(encoding="utf-8"))
    assert metadata["path"] == str(lock_path)
    assert metadata["owner_pid"] == os.getpid()
    assert lock_lines[0] == f"Automation lock acquired: {lock_path}"

    unlock_exit_code, unlock_data, unlock_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=False
        )
    )

    assert unlock_exit_code == automation_lock_module.ExitCode.OK
    assert unlock_data["status"] == "released"
    assert unlock_data["removed_file"] is True
    assert not lock_path.exists()
    assert unlock_lines == [f"Automation lock file removed: {lock_path}"]


def test_automation_lock_metadata_payload_and_legacy_file_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)

    monkeypatch.setattr(
        automation_lock_impl.getpass,
        "getuser",
        lambda: (_ for _ in ()).throw(OSError("missing user")),
    )
    monkeypatch.setattr(automation_lock_impl, "_owner_pid_started_at", lambda _pid: "started-at")
    payload = automation_lock_module._lock_metadata_payload(lock_path, owner_pid=123)
    assert payload["username"] == "unknown"
    assert payload["owner_pid"] == 123
    assert payload["owner_started_at"] == "started-at"
    assert automation_lock_impl._looks_like_legacy_flock_lock("\n") is True
    assert automation_lock_impl._looks_like_legacy_flock_lock("not legacy") is False

    broken_dir = tmp_path / ".codex" / "automations" / "directory-lock"
    broken_dir.mkdir(parents=True)
    directory_info = automation_lock_module._load_lock_info(broken_dir)
    assert directory_info.status == "broken"
    assert directory_info.error == "lock path exists but is not a regular file"

    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: False)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")
    legacy_info = automation_lock_module._load_lock_info(lock_path)
    assert legacy_info.status == "legacy"
    assert legacy_info.legacy_lock_active is False
    assert legacy_info.error == "legacy flock lock file"

    lock_path.write_text("legacy flock", encoding="utf-8")
    arbitrary_text_info = automation_lock_module._load_lock_info(lock_path)
    assert arbitrary_text_info.status == "broken"
    assert "invalid metadata.json" in (arbitrary_text_info.error or "")


def test_automation_lock_reports_invalid_payload_shapes(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path.write_text("{bad-json}", encoding="utf-8")
    invalid_json_info = automation_lock_module._load_lock_info(lock_path)
    assert invalid_json_info.status == "broken"
    assert "invalid metadata.json" in (invalid_json_info.error or "")

    lock_path.write_text("[]", encoding="utf-8")
    non_mapping_info = automation_lock_module._load_lock_info(lock_path)
    assert non_mapping_info.status == "broken"
    assert non_mapping_info.error == "invalid metadata.json: expected a JSON object"

    _write_lock_file(lock_path, {})
    missing_required_fields_info = automation_lock_module._load_lock_info(lock_path)
    assert missing_required_fields_info.status == "broken"
    assert (
        missing_required_fields_info.error
        == "invalid metadata.json: expected non-empty string lock_id"
    )

    _write_lock_file(lock_path, _valid_lock_payload(lock_path, owner_pid="bad"))
    bad_owner_info = automation_lock_module._load_lock_info(lock_path)
    assert bad_owner_info.status == "broken"
    assert bad_owner_info.error == "invalid metadata.json: expected integer owner_pid"


@pytest.mark.parametrize("missing_key", ["acquired_at", "hostname", "username", "cwd", "path"])
def test_automation_lock_reports_missing_required_string_fields(
    tmp_path: Path, missing_key: str
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    payload = _valid_lock_payload(lock_path)
    payload[missing_key] = ""
    _write_lock_file(lock_path, payload)

    info = automation_lock_module._load_lock_info(lock_path)

    assert info.status == "broken"
    assert info.error == f"invalid metadata.json: expected non-empty string {missing_key}"


def test_automation_lock_helper_error_lines_cover_broken_and_environment_cases(
    tmp_path: Path,
) -> None:
    lock_path = _automation_lock_path(tmp_path)

    lines = automation_lock_module._check_lines(
        automation_lock_module.AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            error="bad lock",
        )
    )
    assert lines == [
        "Automation lock status: broken",
        f"- path: {lock_path}",
        "- error: bad lock",
    ]

    unlock_exit_code, unlock_data, unlock_lines = automation_lock_impl._unlock_validation_error(
        automation_lock_module.AutomationLockInfo(
            path=str(lock_path),
            status="broken",
            exists=True,
            error="bad lock",
        )
    )
    assert unlock_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert unlock_data["status"] == "broken"
    assert unlock_lines == [
        "Automation lock release failed.",
        "Automation lock status: broken",
        f"- path: {lock_path}",
        "- error: bad lock",
    ]

    env_exit_code, env_data, env_lines = automation_lock_impl._lock_environment_error(
        lock_path,
        info=automation_lock_module.AutomationLockInfo(
            path=str(lock_path),
            status="stale",
            exists=True,
        ),
        message="env failure",
        exc=OSError("blocked"),
    )
    assert env_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert env_data["status"] == "stale"
    assert env_data["error"] == "blocked"
    assert env_lines == [
        "Automation lock acquisition failed.",
        "env failure",
        "blocked",
    ]


def test_automation_lock_helper_edges_cover_pid_probe_windows_fallback_and_flaky_file_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        automation_lock_impl.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(ProcessLookupError("gone")),
    )
    assert automation_lock_impl._owner_pid_running(123) is False

    monkeypatch.setattr(
        automation_lock_impl.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(PermissionError("denied")),
    )
    assert automation_lock_impl._owner_pid_running(123) is True

    monkeypatch.setattr(
        automation_lock_impl.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(OSError("bad pid")),
    )
    assert automation_lock_impl._owner_pid_running(123) is False

    assert (
        automation_lock_support.owner_pid_running(
            123,
            os_name="nt",
            kill=os.kill,
            run_process=None,
        )
        is None
    )
    monkeypatch.setattr(automation_lock_impl.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )
    assert automation_lock_impl._owner_pid_running(123) is True
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1})(),
    )
    assert automation_lock_impl._owner_pid_running(123) is False
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 2})(),
    )
    assert automation_lock_impl._owner_pid_running(123) is None
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("powershell missing")),
    )
    assert automation_lock_impl._owner_pid_running(123) is None
    assert automation_lock_impl._owner_pid_started_at(0) is None
    assert automation_lock_impl._owner_pid_started_at(123) is None
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "2026-03-20T08:00:00+00:00\n"}
        )(),
    )
    assert automation_lock_impl._owner_pid_started_at(123) == "2026-03-20T08:00:00+00:00"
    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1, "stdout": ""})(),
    )
    assert automation_lock_impl._owner_pid_started_at(123) is None
    monkeypatch.setattr(automation_lock_impl.os, "name", "posix", raising=False)

    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("ps missing")),
    )
    assert automation_lock_impl._owner_pid_started_at(123) is None

    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1, "stdout": ""})(),
    )
    assert automation_lock_impl._owner_pid_started_at(123) is None

    monkeypatch.setattr(
        automation_lock_impl.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": 0, "stdout": " Fri Mar 20 08:00:00 2026\n"}
        )(),
    )
    assert automation_lock_impl._owner_pid_started_at(123) == "Fri Mar 20 08:00:00 2026"

    monkeypatch.setattr(automation_lock_impl, "fcntl", None)
    assert automation_lock_impl._legacy_flock_lock_active(Path("/tmp/legacy-lock")) is None
    assert automation_lock_impl._acquire_legacy_flock_handle(Path("/tmp/legacy-lock")) is None
    with pytest.raises(ValueError, match="automation lock target is required"):
        automation_lock_support.automation_lock_path_arg(
            path_value=None,
            automation_id=None,
            codex_home=Path("/tmp/.codex"),
        )
    assert (
        automation_lock_support.unlock_block_reason(
            automation_lock_module.AutomationLockInfo(
                path="/tmp/lock",
                status="available",
                exists=False,
            ),
            owner_pid=None,
        )
        is None
    )

    class FlakyFilePath:
        def __init__(self) -> None:
            self._calls = 0

        def __str__(self) -> str:
            return "/tmp/flaky-lock"

        def exists(self) -> bool:
            return True

        def is_file(self) -> bool:
            self._calls += 1
            return self._calls == 1

    flaky_info = automation_lock_module._load_lock_info(FlakyFilePath())
    assert flaky_info.status == "broken"
    assert flaky_info.error == "missing metadata.json"

    class UnreadableFilePath:
        def __str__(self) -> str:
            return "/tmp/unreadable-lock"

        def exists(self) -> bool:
            return True

        def is_file(self) -> bool:
            return True

        def read_text(self, *, encoding: str) -> str:
            raise OSError("unreadable")

    unreadable_info = automation_lock_module._load_lock_info(UnreadableFilePath())
    assert unreadable_info.status == "broken"
    assert unreadable_info.error == "invalid metadata.json: unreadable"


def test_automation_lock_helper_edges_cover_legacy_flock_probe_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "legacy-lock"
    lock_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        automation_lock_impl.os,
        "open",
        lambda _path, _flags: (_ for _ in ()).throw(OSError("open blocked")),
    )
    assert automation_lock_impl._legacy_flock_lock_active(lock_path) is None

    calls: list[int] = []

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, operation: int) -> None:
            calls.append(operation)
            if len(calls) == 1:
                raise BlockingIOError("busy")

    monkeypatch.setattr(automation_lock_impl.os, "open", lambda _path, _flags: 7)
    monkeypatch.setattr(automation_lock_impl.os, "close", lambda handle: calls.append(-handle))
    monkeypatch.setattr(automation_lock_impl, "fcntl", FakeFcntl)
    assert automation_lock_impl._legacy_flock_lock_active(lock_path) is True
    assert calls[-1] == -7

    class FailingAcquireFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, operation: int) -> None:
            if operation == (FailingAcquireFcntl.LOCK_EX | FailingAcquireFcntl.LOCK_NB):
                raise OSError("acquire failed")

    monkeypatch.setattr(automation_lock_impl, "fcntl", FailingAcquireFcntl)
    assert automation_lock_impl._legacy_flock_lock_active(lock_path) is None

    class FailingUnlockFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, operation: int) -> None:
            if operation == FailingUnlockFcntl.LOCK_UN:
                raise OSError("unlock failed")

    monkeypatch.setattr(automation_lock_impl, "fcntl", FailingUnlockFcntl)
    assert automation_lock_impl._legacy_flock_lock_active(lock_path) is None

    class HealthyFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, _operation: int) -> None:
            return None

    monkeypatch.setattr(automation_lock_impl, "fcntl", HealthyFcntl)
    assert automation_lock_impl._legacy_flock_lock_active(lock_path) is False

    monkeypatch.setattr(automation_lock_impl.os, "open", lambda _path, _flags: 9)
    assert automation_lock_impl._acquire_legacy_flock_handle(lock_path) == 9
    monkeypatch.setattr(automation_lock_impl.os, "close", lambda handle: calls.append(handle))
    automation_lock_impl._release_legacy_flock_handle(9)
    assert calls[-1] == 9

    monkeypatch.setattr(automation_lock_impl, "fcntl", None)
    monkeypatch.setattr(automation_lock_impl.os, "close", lambda handle: calls.append(handle * 100))
    automation_lock_impl._release_legacy_flock_handle(4)
    assert calls[-1] == 400

    class UnlockFailFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, operation: int) -> None:
            if operation == UnlockFailFcntl.LOCK_UN:
                raise OSError("unlock failed")

    monkeypatch.setattr(automation_lock_impl, "fcntl", UnlockFailFcntl)
    monkeypatch.setattr(automation_lock_impl.os, "close", lambda handle: calls.append(handle * 10))
    automation_lock_impl._release_legacy_flock_handle(3)
    assert calls[-1] == 30

    class BusyFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_handle: int, _operation: int) -> None:
            raise BlockingIOError("busy")

    monkeypatch.setattr(automation_lock_impl, "fcntl", BusyFcntl)
    monkeypatch.setattr(automation_lock_impl.os, "open", lambda _path, _flags: 11)
    monkeypatch.setattr(automation_lock_impl.os, "close", lambda handle: calls.append(-handle))
    assert automation_lock_impl._acquire_legacy_flock_handle(lock_path) is None
    assert calls[-1] == -11

    monkeypatch.setattr(automation_lock_impl, "fcntl", HealthyFcntl)
    monkeypatch.setattr(
        automation_lock_impl.os,
        "open",
        lambda _path, _flags: (_ for _ in ()).throw(OSError("open blocked")),
    )
    assert automation_lock_impl._acquire_legacy_flock_handle(lock_path) is None

    same_stat = lock_path.stat()
    monkeypatch.setattr(
        automation_lock_impl.os,
        "fstat",
        lambda _handle: type(
            "StatResult", (), {"st_dev": same_stat.st_dev, "st_ino": same_stat.st_ino}
        )(),
    )
    assert automation_lock_impl._legacy_handle_matches_current_path(lock_path, 5) is True

    monkeypatch.setattr(
        automation_lock_impl.os,
        "fstat",
        lambda _handle: type(
            "StatResult", (), {"st_dev": same_stat.st_dev, "st_ino": same_stat.st_ino + 1}
        )(),
    )
    assert automation_lock_impl._legacy_handle_matches_current_path(lock_path, 5) is False

    lock_path.unlink()
    assert automation_lock_impl._legacy_handle_matches_current_path(lock_path, 5) is False


def test_automation_lock_check_reports_stale_owner_pid(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(
        lock_path,
        {
            "lock_id": "stale",
            "acquired_at": "2026-03-19T00:00:00+00:00",
            "hostname": "host",
            "username": "user",
            "cwd": "/tmp",
            "path": str(lock_path),
            "owner_pid": -1,
        },
    )

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "stale"
    assert data["owner_pid_running"] is False
    assert "- owner_pid_running: no" in lines


def test_automation_lock_check_marks_windows_owner_as_stale_when_powershell_reports_missing(
    tmp_path: Path,
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(
        lock_path,
        _valid_lock_payload(lock_path, lock_id="windows-stale", owner_pid=123),
    )
    info = automation_lock_support.load_lock_info(
        lock_path,
        current_hostname="host",
        legacy_lock_active_fn=lambda _path: None,
        owner_pid_running_fn=lambda owner_pid: automation_lock_support.owner_pid_running(
            owner_pid,
            os_name="nt",
            kill=os.kill,
            run_process=lambda *_args, **_kwargs: type("Result", (), {"returncode": 1})(),
        ),
        owner_pid_started_at_fn=lambda _pid: None,
    )

    assert info.status == "stale"
    assert info.owner_pid_running is False
    assert "- owner_pid_running: no" in automation_lock_module._check_lines(info)


def test_automation_lock_load_info_preserves_remote_host_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path, "remote-host-lock")
    _write_lock_file(
        lock_path,
        _valid_lock_payload(
            lock_path,
            lock_id="remote-lock",
            hostname="remote-host",
            owner_pid=123,
            owner_started_at="remote-start",
        ),
    )
    monkeypatch.setattr(automation_lock_impl.socket, "gethostname", lambda: "local-host")
    monkeypatch.setattr(automation_lock_impl, "_owner_pid_running", lambda _pid: False)
    monkeypatch.setattr(automation_lock_impl, "_owner_pid_started_at", lambda _pid: "local-start")

    info = automation_lock_module._load_lock_info(lock_path)

    assert info.status == "held"
    assert info.hostname == "remote-host"
    assert info.owner_pid_running is None
    assert info.owner_pid_identity_matches is None


def test_automation_lock_load_info_marks_pid_reuse_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(
        lock_path,
        _valid_lock_payload(
            lock_path, lock_id="stale", owner_pid=123, owner_started_at="old-start"
        ),
    )
    monkeypatch.setattr(automation_lock_impl, "_owner_pid_running", lambda _pid: True)
    monkeypatch.setattr(automation_lock_impl, "_owner_pid_started_at", lambda _pid: "new-start")

    info = automation_lock_module._load_lock_info(lock_path)

    assert info.status == "stale"
    assert info.owner_pid_identity_matches is False
    assert "- owner_pid_identity_matches: no" in automation_lock_module._check_lines(info)


def test_automation_lock_load_info_rejects_non_string_owner_started_at(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(lock_path, _valid_lock_payload(lock_path, owner_pid=123, owner_started_at=456))

    info = automation_lock_module._load_lock_info(lock_path)

    assert info.status == "broken"
    assert info.error == "invalid metadata.json: expected string owner_started_at"


def test_automation_lock_rejects_paths_outside_codex_home_contract(tmp_path: Path) -> None:
    invalid_path = tmp_path / "outside-lock"

    check_exit_code, check_data, check_lines = automation_lock_module.automation_lock_check_data(
        str(invalid_path), dry_run=False
    )
    assert check_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert check_data["status"] == "broken"
    assert "must stay under" in (check_data["error"] or "")
    assert check_lines[0] == "Automation lock status: broken"

    lock_exit_code, lock_data, lock_lines = automation_lock_module.automation_lock_lock_data(
        str(invalid_path), owner_pid=None, dry_run=False
    )
    assert lock_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert lock_data["status"] == "broken"
    assert lock_lines[0] == "Automation lock acquisition failed."

    unlock_exit_code, unlock_data, unlock_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(invalid_path), owner_pid=None, dry_run=False
        )
    )
    assert unlock_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert unlock_data["status"] == "broken"
    assert unlock_lines[0] == "Automation lock release failed."

    dry_run_unlock_exit_code, dry_run_unlock_data, dry_run_unlock_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(invalid_path), owner_pid=None, dry_run=True
        )
    )
    assert dry_run_unlock_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert dry_run_unlock_data["dry_run"] is True
    assert dry_run_unlock_lines[-1] == (
        f"Dry run: would release the automation lock at {invalid_path.resolve(strict=False)}."
    )


def test_automation_lock_rejects_non_lock_leaf_under_automations(tmp_path: Path) -> None:
    invalid_path = tmp_path / ".codex" / "automations" / "test-automation" / "metadata.json"

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(invalid_path), dry_run=True
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "broken"
    assert "must use the" in (data["error"] or "")
    assert lines[-1] == "Dry run: inspected the current lock state without changing it."


def test_automation_lock_unlock_covers_dry_run_missing_file_directory_cleanup_and_fake_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = _automation_lock_path(tmp_path)
    dry_exit_code, dry_data, dry_lines = automation_lock_module.automation_lock_unlock_data(
        str(file_path), owner_pid=None, dry_run=True
    )
    assert dry_exit_code == automation_lock_module.ExitCode.OK
    assert dry_data["dry_run"] is True
    assert dry_lines[-1] == f"Dry run: would release the automation lock at {file_path}."

    missing_exit_code, missing_data, missing_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(file_path), owner_pid=None, dry_run=False
        )
    )
    assert missing_exit_code == automation_lock_module.ExitCode.OK
    assert missing_data["status"] == "available"
    assert missing_lines == [f"Automation lock was already absent: {file_path}"]

    _write_lock_file(
        file_path, _valid_lock_payload(file_path, lock_id="unlock", owner_pid=os.getpid())
    )
    held_dry_run_exit_code, held_dry_run_data, held_dry_run_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(file_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert held_dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert held_dry_run_data["dry_run"] is True
    assert held_dry_run_lines[-1] == f"Dry run: would release the automation lock at {file_path}."
    assert file_path.exists()

    file_exit_code, file_data, file_lines = automation_lock_module.automation_lock_unlock_data(
        str(file_path), owner_pid=os.getpid(), dry_run=False
    )
    assert file_exit_code == automation_lock_module.ExitCode.OK
    assert file_data["removed_file"] is True
    assert file_lines == [f"Automation lock file removed: {file_path}"]


def test_automation_lock_unlock_covers_directory_cleanup_and_fake_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_lock = _automation_lock_path(tmp_path, "legacy-lock")
    directory_lock.mkdir(parents=True)
    directory_dry_run_exit_code, directory_dry_run_data, directory_dry_run_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(directory_lock), owner_pid=None, dry_run=True
        )
    )
    assert directory_dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert directory_dry_run_data["dry_run"] is True
    assert directory_dry_run_lines[-1] == (
        f"Dry run: would release the automation lock at {directory_lock}."
    )
    directory_exit_code, directory_data, directory_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(directory_lock), owner_pid=None, dry_run=False
        )
    )
    assert directory_exit_code == automation_lock_module.ExitCode.OK
    assert directory_data["removed_file"] is False
    assert directory_lines == [f"Automation lock released: {directory_lock}"]

    directory_with_metadata = _automation_lock_path(tmp_path, "legacy-lock-with-metadata")
    directory_with_metadata.mkdir(parents=True)
    (directory_with_metadata / "metadata.json").write_text("{}", encoding="utf-8")
    metadata_exit_code, metadata_data, metadata_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(directory_with_metadata), owner_pid=None, dry_run=False
        )
    )
    assert metadata_exit_code == automation_lock_module.ExitCode.OK
    assert metadata_data["removed_file"] is False
    assert metadata_lines == [f"Automation lock released: {directory_with_metadata}"]

    unexpected_lock = _automation_lock_path(tmp_path, "unexpected-lock")
    unexpected_lock.mkdir(parents=True)
    (unexpected_lock / "extra.txt").write_text("extra", encoding="utf-8")
    unexpected_exit_code, unexpected_data, unexpected_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(unexpected_lock), owner_pid=None, dry_run=False
        )
    )
    assert unexpected_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert unexpected_data["unexpected_entries"] == ["extra.txt"]
    assert unexpected_lines == [
        "Automation lock release failed.",
        "Lock directory contains unexpected entries: extra.txt",
    ]

    class FakeOddPath:
        def __str__(self) -> str:
            return str(_automation_lock_path(tmp_path, "odd-lock"))

        def exists(self) -> bool:
            return True

        def is_file(self) -> bool:
            return False

        def is_dir(self) -> bool:
            return False

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: FakeOddPath())
    monkeypatch.setattr(automation_lock_impl, "_validate_lock_path", lambda _path: None)
    odd_exit_code, odd_data, odd_lines = automation_lock_module.automation_lock_unlock_data(
        "ignored", owner_pid=None, dry_run=False
    )
    assert odd_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert odd_data["status"] == "broken"
    assert odd_lines[0] == "Automation lock release failed."


def test_automation_lock_unlock_directory_dry_run_validates_unexpected_entries(
    tmp_path: Path,
) -> None:
    unexpected_lock = _automation_lock_path(tmp_path, "unexpected-lock-dry-run")
    unexpected_lock.mkdir(parents=True)
    (unexpected_lock / "extra.txt").write_text("extra", encoding="utf-8")
    unexpected_exit_code, unexpected_data, unexpected_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(unexpected_lock), owner_pid=None, dry_run=True
        )
    )
    assert unexpected_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert unexpected_data["dry_run"] is True
    assert unexpected_data["unexpected_entries"] == ["extra.txt"]
    assert unexpected_lines == [
        "Automation lock release failed.",
        "Lock directory contains unexpected entries: extra.txt",
    ]


def test_automation_lock_unlock_rejects_missing_or_mismatched_owner_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(
        lock_path, _valid_lock_payload(lock_path, lock_id="held", owner_pid=os.getpid())
    )

    missing_owner_exit_code, _, missing_owner_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(lock_path), owner_pid=None, dry_run=False
        )
    )
    assert missing_owner_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert (
        missing_owner_lines[1] == "Unlock requires --owner-pid to release a live automation lock."
    )
    dry_run_missing_owner_exit_code, dry_run_missing_owner_data, dry_run_missing_owner_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(lock_path), owner_pid=None, dry_run=True
        )
    )
    assert dry_run_missing_owner_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert dry_run_missing_owner_data["dry_run"] is True
    assert (
        dry_run_missing_owner_lines[1]
        == "Unlock requires --owner-pid to release a live automation lock."
    )

    ownerless_lock_path = _automation_lock_path(tmp_path, "ownerless-lock")
    _write_lock_file(ownerless_lock_path, _valid_lock_payload(ownerless_lock_path, owner_pid=None))
    ownerless_exit_code, _, ownerless_lines = automation_lock_module.automation_lock_unlock_data(
        str(ownerless_lock_path), owner_pid=99999, dry_run=False
    )
    assert ownerless_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert (
        ownerless_lines[1]
        == "Unlock requires manual review because the live automation lock has no recorded owner PID."
    )

    mismatch_exit_code, _, mismatch_lines = automation_lock_module.automation_lock_unlock_data(
        str(lock_path), owner_pid=99999, dry_run=False
    )
    assert mismatch_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert mismatch_lines[1] == (
        f"Unlock owner mismatch: lock is owned by pid {os.getpid()}, not 99999."
    )

    legacy_path = _automation_lock_path(tmp_path, "legacy-lock")
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("", encoding="utf-8")
    with open(legacy_path, "r+", encoding="utf-8") as legacy_stream:
        automation_lock_impl.fcntl.flock(
            legacy_stream.fileno(),
            automation_lock_impl.fcntl.LOCK_EX | automation_lock_impl.fcntl.LOCK_NB,
        )
        try:
            legacy_exit_code, _, legacy_lines = automation_lock_module.automation_lock_unlock_data(
                str(legacy_path), owner_pid=None, dry_run=False
            )
        finally:
            automation_lock_impl.fcntl.flock(
                legacy_stream.fileno(), automation_lock_impl.fcntl.LOCK_UN
            )
    assert legacy_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert (
        legacy_lines[1] == "Unlock requires the active legacy flock holder to exit before cleanup."
    )

    unknown_legacy_path = _automation_lock_path(tmp_path, "unknown-legacy-lock")
    unknown_legacy_path.parent.mkdir(parents=True, exist_ok=True)
    unknown_legacy_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: None)
    unknown_exit_code, _, unknown_lines = automation_lock_module.automation_lock_unlock_data(
        str(unknown_legacy_path), owner_pid=None, dry_run=False
    )
    assert unknown_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert (
        unknown_lines[1]
        == "Unlock requires manual review because legacy flock status is indeterminate."
    )


def test_automation_lock_unlock_rejects_broken_file_and_reports_unlink_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_path = _automation_lock_path(tmp_path, "broken-lock")
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text("{bad-json}", encoding="utf-8")

    broken_exit_code, broken_data, broken_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(broken_path), owner_pid=None, dry_run=False
        )
    )
    assert broken_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert broken_data["status"] == "broken"
    assert broken_lines[0] == "Automation lock release failed."

    unlink_path = _automation_lock_path(tmp_path, "unlink-error-lock")
    _write_lock_file(
        unlink_path, _valid_lock_payload(unlink_path, lock_id="held", owner_pid=os.getpid())
    )
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == unlink_path:
            raise OSError("unlink blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    unlink_exit_code, unlink_data, unlink_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(unlink_path), owner_pid=os.getpid(), dry_run=False
        )
    )
    assert unlink_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert unlink_data["error"] == "unlink blocked"
    assert unlink_lines[1] == f"Unable to remove the automation lock file: {unlink_path}"

    directory_path = _automation_lock_path(tmp_path, "legacy-dir-lock")
    directory_path.mkdir(parents=True)
    original_iterdir = Path.iterdir

    def _raising_iterdir(self: Path):
        if self == directory_path:
            raise OSError("iterdir blocked")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _raising_iterdir)
    directory_exit_code, directory_data, directory_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(directory_path), owner_pid=None, dry_run=False
        )
    )
    assert directory_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert directory_data["error"] == "iterdir blocked"
    assert (
        directory_lines[1] == f"Unable to inspect the automation lock directory: {directory_path}"
    )

    removable_directory = _automation_lock_path(tmp_path, "legacy-dir-with-metadata")
    removable_directory.mkdir(parents=True)
    (removable_directory / "metadata.json").write_text("{}", encoding="utf-8")
    original_rmdir = Path.rmdir

    def _raising_rmdir(self: Path) -> None:
        if self == removable_directory:
            raise OSError("rmdir blocked")
        return original_rmdir(self)

    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda self: iter([]) if self == removable_directory else original_iterdir(self),
    )
    monkeypatch.setattr(Path, "rmdir", _raising_rmdir)
    rmdir_exit_code, rmdir_data, rmdir_lines = automation_lock_module.automation_lock_unlock_data(
        str(removable_directory), owner_pid=None, dry_run=False
    )
    assert rmdir_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert rmdir_data["error"] == "rmdir blocked"
    assert rmdir_lines[1] == (
        f"Unable to remove the automation lock directory: {removable_directory}"
    )


@pytest.mark.parametrize("owner_pid", [0, -1])
def test_automation_lock_lock_rejects_non_positive_owner_pid(
    tmp_path: Path, owner_pid: int
) -> None:
    lock_path = _automation_lock_path(tmp_path, f"invalid-owner-{owner_pid}")

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=owner_pid, dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "broken"
    assert data["error"] == "Lock requires --owner-pid to be a positive integer when provided."
    assert lines[0] == "Automation lock acquisition failed."
    assert not lock_path.exists()


def test_automation_lock_check_rejects_incomplete_json_metadata(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path, "incomplete-metadata")
    _write_lock_file(lock_path, {})

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "broken"
    assert data["error"] == "invalid metadata.json: expected non-empty string lock_id"
    assert lines[0] == "Automation lock status: broken"


def test_prepare_stale_lock_for_acquire_tolerates_concurrent_cleanup_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path, "stale-race")
    stale_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="stale",
        exists=True,
        lock_id="stale",
        acquired_at="2026-03-20T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=123,
        owner_started_at=None,
        owner_pid_running=False,
        owner_pid_identity_matches=None,
    )
    available_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="available",
        exists=False,
    )
    load_results = iter([stale_info, available_info])
    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: next(load_results))
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            raise FileNotFoundError("already removed")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)

    info, result = automation_lock_impl._prepare_stale_lock_for_acquire(lock_path, info=stale_info)

    assert result is None
    assert info.status == "available"


def test_automation_lock_handlers_wrap_data_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_paths: list[str] = []

    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_check_data",
        lambda path, **_kwargs: (
            captured_paths.append(path) or automation_lock_module.ExitCode.OK,
            {"ok": True},
            ["check"],
        ),
    )
    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_lock_data",
        lambda path, **_kwargs: (
            captured_paths.append(path) or automation_lock_module.ExitCode.OK,
            {"ok": True},
            ["lock"],
        ),
    )
    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_unlock_data",
        lambda path, **_kwargs: (
            captured_paths.append(path) or automation_lock_module.ExitCode.OK,
            {"ok": True},
            ["unlock"],
        ),
    )
    monkeypatch.setattr(
        automation_lock_impl,
        "_codex_home_path",
        lambda: Path("/tmp/.codex"),
    )

    assert automation_lock_module.handle_automation_lock_check(
        type("Args", (), {"path": "/tmp/check", "dry_run": False})()
    ).lines == ["check"]
    assert automation_lock_module.handle_automation_lock_lock(
        type("Args", (), {"path": "/tmp/lock", "owner_pid": 123, "dry_run": False})()
    ).lines == ["lock"]
    assert automation_lock_module.handle_automation_lock_unlock(
        type("Args", (), {"path": "/tmp/unlock", "owner_pid": 123, "dry_run": False})()
    ).lines == ["unlock"]
    assert automation_lock_module.handle_automation_lock_check(
        type(
            "Args",
            (),
            {"path": None, "automation_id": "horadus-sprint-autopilot", "dry_run": False},
        )()
    ).lines == ["check"]
    assert captured_paths[-1] == str(
        Path("/tmp/.codex/automations/horadus-sprint-autopilot/lock").resolve(strict=False)
    )
