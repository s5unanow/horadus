from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_automation_lock as automation_lock_module
import tools.horadus.python.horadus_workflow.task_workflow_automation_lock as automation_lock_impl

pytestmark = pytest.mark.unit


def _write_lock_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_automation_lock_check_reports_available_path(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=True
    )

    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "available"
    assert data["dry_run"] is True
    assert lines == [
        f"Automation lock is available: {lock_path}",
        "Dry run: inspected the current lock state without changing it.",
    ]


def test_automation_lock_lock_and_unlock_round_trip(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

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


def test_automation_lock_check_and_helpers_cover_broken_payload_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"

    monkeypatch.setattr(
        automation_lock_impl.getpass,
        "getuser",
        lambda: (_ for _ in ()).throw(OSError("missing user")),
    )
    payload = automation_lock_module._lock_metadata_payload(lock_path, owner_pid=123)
    assert payload["username"] == "unknown"
    assert payload["owner_pid"] == 123

    broken_dir = tmp_path / "directory-lock"
    broken_dir.mkdir()
    directory_info = automation_lock_module._load_lock_info(broken_dir)
    assert directory_info.status == "broken"
    assert directory_info.error == "lock path exists but is not a regular file"

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("legacy flock", encoding="utf-8")
    legacy_info = automation_lock_module._load_lock_info(lock_path)
    assert legacy_info.status == "legacy"
    assert legacy_info.error == "legacy flock lock file"

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


def test_automation_lock_check_reports_stale_owner_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"
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


def test_automation_lock_lock_dry_run_and_live_held_paths(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

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


def test_automation_lock_lock_reclaims_stale_file_and_reports_stale_dry_run(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "automation" / "lock"
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
    assert dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert dry_run_data["status"] == "stale"
    assert dry_run_lines[-1] == f"Dry run: would replace the stale automation lock at {lock_path}."

    live_exit_code, live_data, _live_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert live_exit_code == automation_lock_module.ExitCode.OK
    assert live_data["status"] == "held"
    assert live_data["owner_pid"] == os.getpid()


def test_automation_lock_lock_reclaims_legacy_flock_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")

    dry_run_exit_code, dry_run_data, dry_run_lines = (
        automation_lock_module.automation_lock_lock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert dry_run_data["status"] == "legacy"
    assert dry_run_lines[-1] == f"Dry run: would replace the legacy automation lock at {lock_path}."

    live_exit_code, live_data, _live_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert live_exit_code == automation_lock_module.ExitCode.OK
    assert live_data["status"] == "held"
    assert live_data["owner_pid"] == os.getpid()


def test_automation_lock_lock_handles_prepare_write_and_stale_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"

    class RaisingParent:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            raise OSError("parent blocked")

    class FakePath:
        parent = RaisingParent()

        def __str__(self) -> str:
            return "/tmp/fake-lock"

        def exists(self) -> bool:
            return False

        def is_file(self) -> bool:
            return False

        def with_name(self, _name: str) -> Path:
            return Path("/tmp/unused")

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: FakePath())
    prepare_exit_code, prepare_data, prepare_lines = (
        automation_lock_module.automation_lock_lock_data("ignored", owner_pid=None, dry_run=False)
    )
    assert prepare_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert prepare_data["status"] == "error"
    assert prepare_lines[1] == "Unable to prepare the lock path: /tmp/fake-lock"

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
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            raise OSError("stale cleanup blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    stale_exit_code, stale_data, stale_lines = automation_lock_module.automation_lock_lock_data(
        "ignored", owner_pid=None, dry_run=False
    )
    assert stale_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert stale_data["status"] == "stale"
    assert stale_lines[1] == f"Unable to clear the stale lock file: {lock_path}"


def test_automation_lock_lock_retries_when_stale_lock_disappears_mid_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"
    _write_lock_file(
        lock_path,
        {
            "lock_id": "stale-disappearing",
            "acquired_at": "2026-03-19T00:00:00+00:00",
            "hostname": "host",
            "username": "user",
            "cwd": "/tmp",
            "path": str(lock_path),
            "owner_pid": -1,
        },
    )
    original_unlink = Path.unlink
    calls = {"count": 0}

    def _raise_after_delete(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path and calls["count"] == 0:
            calls["count"] += 1
            original_unlink(self, missing_ok=missing_ok)
            raise FileNotFoundError("gone")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raise_after_delete)
    exit_code, data, _lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )
    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "held"


def test_automation_lock_lock_handles_contention_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"
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
    stale_exit_code, stale_data, _stale_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert stale_exit_code == automation_lock_module.ExitCode.OK
    assert stale_data["status"] == "held"
    assert stale_data["owner_pid"] == os.getpid()


def test_automation_lock_lock_reports_stale_cleanup_error_from_contention_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"
    original_unlink = Path.unlink

    def _stale_race(src: str, dst: str, *, follow_symlinks: bool = True) -> None:
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

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            raise OSError("blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(automation_lock_impl.os, "link", _stale_race)
    monkeypatch.setattr(Path, "unlink", _raising_unlink)
    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )
    assert exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert data["status"] == "stale"
    assert lines[1] == f"Unable to clear the stale lock file: {lock_path}"


def test_automation_lock_lock_retries_when_stale_contention_file_is_already_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"
    original_unlink = Path.unlink
    original_link = os.link
    calls = {"count": 0}

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

    def _raise_file_not_found(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            original_unlink(self, missing_ok=missing_ok)
            raise FileNotFoundError("gone")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(automation_lock_impl.os, "link", _stale_race)
    monkeypatch.setattr(Path, "unlink", _raise_file_not_found)
    exit_code, data, _lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )
    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "held"


def test_automation_lock_unlock_covers_dry_run_missing_file_directory_cleanup_and_fake_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = tmp_path / "automation" / "lock"
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

    directory_lock = tmp_path / "automation" / "legacy-lock"
    directory_lock.mkdir(parents=True)
    directory_exit_code, directory_data, directory_lines = (
        automation_lock_module.automation_lock_unlock_data(
            str(directory_lock), owner_pid=None, dry_run=False
        )
    )
    assert directory_exit_code == automation_lock_module.ExitCode.OK
    assert directory_data["removed_file"] is False
    assert directory_lines == [f"Automation lock released: {directory_lock}"]

    directory_with_metadata = tmp_path / "automation" / "legacy-lock-with-metadata"
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

    unexpected_lock = tmp_path / "automation" / "unexpected-lock"
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
            return "/tmp/odd-lock"

        def exists(self) -> bool:
            return True

        def is_file(self) -> bool:
            return False

        def is_dir(self) -> bool:
            return False

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: FakeOddPath())
    odd_exit_code, odd_data, odd_lines = automation_lock_module.automation_lock_unlock_data(
        "ignored", owner_pid=None, dry_run=False
    )
    assert odd_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert odd_data["status"] == "broken"
    assert odd_lines[0] == "Automation lock release failed."


def test_automation_lock_unlock_rejects_missing_or_mismatched_owner_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"
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


def test_automation_lock_unlock_rejects_broken_file_and_reports_unlink_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_path = tmp_path / "automation" / "broken-lock"
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

    unlink_path = tmp_path / "automation" / "unlink-error-lock"
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
