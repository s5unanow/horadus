from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_automation_lock as automation_lock_module
import tools.horadus.python.horadus_workflow.task_workflow_automation_lock as automation_lock_impl

pytestmark = pytest.mark.unit


def _automation_lock_path(tmp_path: Path, automation_id: str = "test-automation") -> Path:
    return tmp_path / ".codex" / "automations" / automation_id / "lock"


@pytest.fixture(autouse=True)
def _set_test_codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))


def _write_lock_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    payload = automation_lock_module._lock_metadata_payload(lock_path, owner_pid=123)
    assert payload["username"] == "unknown"
    assert payload["owner_pid"] == 123

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

    _write_lock_file(lock_path, {"owner_pid": "bad"})
    bad_owner_info = automation_lock_module._load_lock_info(lock_path)
    assert bad_owner_info.status == "broken"
    assert bad_owner_info.error == "invalid metadata.json: expected integer owner_pid"


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

    monkeypatch.setattr(automation_lock_impl.os, "name", "nt", raising=False)
    assert automation_lock_impl._owner_pid_running(123) is None
    monkeypatch.setattr(automation_lock_impl, "fcntl", None)
    assert automation_lock_impl._legacy_flock_lock_active(Path("/tmp/legacy-lock")) is None

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


def test_automation_lock_rejects_non_lock_leaf_under_automations(tmp_path: Path) -> None:
    invalid_path = tmp_path / ".codex" / "automations" / "test-automation" / "metadata.json"

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(invalid_path), dry_run=True
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "broken"
    assert "must use the" in (data["error"] or "")
    assert lines[-1] == "Dry run: inspected the current lock state without changing it."


def test_automation_lock_lock_dry_run_and_live_held_paths(tmp_path: Path) -> None:
    lock_path = _automation_lock_path(tmp_path)

    dry_run_exit_code, dry_run_data, dry_run_lines = (
        automation_lock_module.automation_lock_lock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert dry_run_data["dry_run"] is True
    assert dry_run_lines[-1] == f"Dry run: would acquire the automation lock at {lock_path}."

    _write_lock_file(
        lock_path,
        {
            "lock_id": "held",
            "acquired_at": "2026-03-19T00:00:00+00:00",
            "hostname": "host",
            "username": "user",
            "cwd": "/tmp",
            "path": str(lock_path),
            "owner_pid": os.getpid(),
        },
    )
    held_exit_code, held_data, held_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert held_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert held_data["status"] == "held"
    assert held_lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_surfaces_stale_file_without_reclaiming(tmp_path: Path) -> None:
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

    dry_run_exit_code, dry_run_data, dry_run_lines = (
        automation_lock_module.automation_lock_lock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert dry_run_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert dry_run_data["status"] == "stale"
    assert dry_run_lines[0] == "Automation lock acquisition failed."

    live_exit_code, live_data, live_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert live_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert live_data["status"] == "stale"
    assert live_lines[0] == "Automation lock acquisition failed."
    assert lock_path.exists()


def test_automation_lock_lock_migrates_inactive_legacy_flock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: False)

    dry_run_exit_code, dry_run_data, dry_run_lines = (
        automation_lock_module.automation_lock_lock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert dry_run_data["status"] == "legacy"
    assert dry_run_lines[-1] == (
        f"Dry run: would replace the inactive legacy automation lock at {lock_path}."
    )

    live_exit_code, live_data, live_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert live_exit_code == automation_lock_module.ExitCode.OK
    assert live_data["status"] == "held"
    assert live_data["owner_pid"] == os.getpid()
    assert live_lines[0] == f"Automation lock acquired: {lock_path}"


def test_automation_lock_lock_blocks_active_legacy_flock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: True)

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "legacy"
    assert data["legacy_lock_active"] is True
    assert lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_handles_prepare_and_write_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)

    class RaisingParent:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            raise OSError("parent blocked")

    class FakePath:
        parent = RaisingParent()

        def __str__(self) -> str:
            return str(_automation_lock_path(tmp_path, "fake-lock"))

        def exists(self) -> bool:
            return False

        def is_file(self) -> bool:
            return False

        def with_name(self, _name: str) -> Path:
            return Path("/tmp/unused")

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: FakePath())
    monkeypatch.setattr(automation_lock_impl, "_validate_lock_path", lambda _path: None)
    prepare_exit_code, prepare_data, prepare_lines = (
        automation_lock_module.automation_lock_lock_data("ignored", owner_pid=None, dry_run=False)
    )
    assert prepare_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert prepare_data["status"] == "error"
    assert prepare_lines[1] == (
        f"Unable to prepare the lock path: {_automation_lock_path(tmp_path, 'fake-lock')}"
    )

    def _failing_write(_path: Path, _payload: dict[str, object]) -> None:
        raise OSError("metadata blocked")

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: lock_path)
    monkeypatch.setattr(automation_lock_impl, "_write_metadata", _failing_write)
    write_exit_code, write_data, write_lines = automation_lock_module.automation_lock_lock_data(
        "ignored", owner_pid=None, dry_run=False
    )
    assert write_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert write_data["status"] == "error"
    assert write_lines[1] == f"Unable to write lock metadata for {lock_path}."

    lock_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: False)
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            raise OSError("legacy cleanup blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    legacy_exit_code, legacy_data, legacy_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )
    assert legacy_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert legacy_data["status"] == "legacy"
    assert legacy_lines[1] == f"Unable to clear the inactive legacy lock file: {lock_path}"


def test_automation_lock_lock_handles_contention_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    original_link = os.link
    calls = {"count": 0}

    def _held_race(src: str, dst: str, *, follow_symlinks: bool = True) -> None:
        if calls["count"] == 0:
            calls["count"] += 1
            _write_lock_file(
                Path(dst),
                {
                    "lock_id": "held-race",
                    "acquired_at": "2026-03-19T00:00:00+00:00",
                    "hostname": "host",
                    "username": "user",
                    "cwd": "/tmp",
                    "path": str(dst),
                    "owner_pid": os.getpid(),
                },
            )
            raise FileExistsError("race")
        return original_link(src, dst, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(automation_lock_impl.os, "link", _held_race)
    held_exit_code, held_data, held_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )
    assert held_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert held_data["status"] == "held"
    assert held_lines[0] == "Automation lock acquisition failed."

    lock_path.unlink()
    calls["count"] = 0

    def _stale_race(src: str, dst: str, *, follow_symlinks: bool = True) -> None:
        if calls["count"] == 0:
            calls["count"] += 1
            _write_lock_file(
                Path(dst),
                {
                    "lock_id": "stale-race",
                    "acquired_at": "2026-03-19T00:00:00+00:00",
                    "hostname": "host",
                    "username": "user",
                    "cwd": "/tmp",
                    "path": str(dst),
                    "owner_pid": -1,
                },
            )
            raise FileExistsError("race")
        return original_link(src, dst, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(automation_lock_impl.os, "link", _stale_race)
    stale_exit_code, stale_data, stale_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert stale_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert stale_data["status"] == "stale"
    assert stale_lines[0] == "Automation lock acquisition failed."


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

    _write_lock_file(file_path, {"lock_id": "unlock", "owner_pid": os.getpid()})
    file_exit_code, file_data, file_lines = automation_lock_module.automation_lock_unlock_data(
        str(file_path), owner_pid=os.getpid(), dry_run=False
    )
    assert file_exit_code == automation_lock_module.ExitCode.OK
    assert file_data["removed_file"] is True
    assert file_lines == [f"Automation lock file removed: {file_path}"]

    directory_lock = _automation_lock_path(tmp_path, "legacy-lock")
    directory_lock.mkdir(parents=True)
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


def test_automation_lock_unlock_rejects_missing_or_mismatched_owner_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    _write_lock_file(lock_path, {"lock_id": "held", "owner_pid": os.getpid()})

    missing_owner_exit_code, _, missing_owner_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(lock_path), owner_pid=None, dry_run=False
        )
    )
    assert missing_owner_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert (
        missing_owner_lines[1] == "Unlock requires --owner-pid to release a live automation lock."
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
    _write_lock_file(unlink_path, {"lock_id": "held"})
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == unlink_path:
            raise OSError("unlink blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    unlink_exit_code, unlink_data, unlink_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(unlink_path), owner_pid=None, dry_run=False
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


def test_automation_lock_handlers_wrap_data_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_check_data",
        lambda *_args, **_kwargs: (automation_lock_module.ExitCode.OK, {"ok": True}, ["check"]),
    )
    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_lock_data",
        lambda *_args, **_kwargs: (automation_lock_module.ExitCode.OK, {"ok": True}, ["lock"]),
    )
    monkeypatch.setattr(
        automation_lock_impl,
        "automation_lock_unlock_data",
        lambda *_args, **_kwargs: (automation_lock_module.ExitCode.OK, {"ok": True}, ["unlock"]),
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
