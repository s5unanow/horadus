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
    held_dry_run_exit_code, held_dry_run_data, held_dry_run_lines = (
        automation_lock_module.automation_lock_lock_data(
            str(lock_path), owner_pid=os.getpid(), dry_run=True
        )
    )
    assert held_dry_run_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert held_dry_run_data["status"] == "held"
    assert held_dry_run_data["dry_run"] is True
    assert held_dry_run_lines[0] == "Automation lock acquisition failed."
    assert held_dry_run_lines[1] == "Automation lock status: held"

    held_exit_code, held_data, held_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert held_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert held_data["status"] == "held"
    assert held_lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_reclaims_stale_file(tmp_path: Path) -> None:
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
    assert dry_run_exit_code == automation_lock_module.ExitCode.OK
    assert dry_run_data["status"] == "stale"
    assert dry_run_lines[-1] == f"Dry run: would replace the stale automation lock at {lock_path}."

    live_exit_code, live_data, live_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )
    assert live_exit_code == automation_lock_module.ExitCode.OK
    assert live_data["status"] == "held"
    assert live_data["owner_pid"] == os.getpid()
    assert live_lines[0] == f"Automation lock acquired: {lock_path}"
    assert lock_path.exists()


def test_automation_lock_lock_rechecks_stale_state_before_reclaiming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    stale_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="stale",
        exists=True,
        lock_id="stale-lock",
        acquired_at="2026-03-19T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=-1,
        owner_pid_running=False,
    )
    held_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="held",
        exists=True,
        lock_id="replacement-lock",
        acquired_at="2026-03-20T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=os.getpid(),
        owner_started_at="new-start",
        owner_pid_running=True,
        owner_pid_identity_matches=True,
    )
    states = iter([stale_info, stale_info, held_info])

    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: next(states))
    monkeypatch.setattr(
        type(lock_path),
        "unlink",
        lambda *_args, **_kwargs: pytest.fail("stale reclaim should not unlink a replaced lock"),
        raising=False,
    )

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "held"
    assert lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_rechecks_stale_identity_before_reclaiming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    stale_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="stale",
        exists=True,
        lock_id="stale-lock",
        acquired_at="2026-03-19T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=-1,
        owner_pid_running=False,
    )
    replaced_stale_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="stale",
        exists=True,
        lock_id="replacement-lock",
        acquired_at="2026-03-20T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=-1,
        owner_pid_running=False,
    )
    states = iter([stale_info, stale_info, replaced_stale_info])

    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: next(states))
    monkeypatch.setattr(
        type(lock_path),
        "unlink",
        lambda *_args, **_kwargs: pytest.fail("stale reclaim should not unlink a replaced lock"),
        raising=False,
    )

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "stale"
    assert data["lock_id"] == "replacement-lock"
    assert lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_reports_stale_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    stale_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="stale",
        exists=True,
        lock_id="stale-lock",
        acquired_at="2026-03-19T00:00:00+00:00",
        hostname="host",
        username="user",
        cwd="/tmp",
        owner_pid=-1,
        owner_pid_running=False,
    )
    states = iter([stale_info, stale_info, stale_info])

    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: next(states))
    original_unlink = Path.unlink

    def _raising_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == lock_path:
            raise OSError("stale cleanup blocked")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _raising_unlink)

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=os.getpid(), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert data["status"] == "stale"
    assert data["error"] == "stale cleanup blocked"
    assert lines[1] == f"Unable to clear the stale automation lock file: {lock_path}"


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


def test_automation_lock_lock_rechecks_legacy_state_during_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(automation_lock_impl, "_legacy_flock_lock_active", lambda _path: False)
    monkeypatch.setattr(automation_lock_impl, "_acquire_legacy_flock_handle", lambda _path: 7)
    monkeypatch.setattr(
        automation_lock_impl,
        "_legacy_handle_matches_current_path",
        lambda *_args: (
            _write_lock_file(
                lock_path,
                {
                    "lock_id": "replacement",
                    "acquired_at": "2026-03-20T00:00:00+00:00",
                    "hostname": "host",
                    "username": "user",
                    "cwd": "/tmp",
                    "path": str(lock_path),
                    "owner_pid": os.getpid(),
                },
            )
            or False
        ),
    )
    monkeypatch.setattr(automation_lock_impl, "_release_legacy_flock_handle", lambda _handle: None)

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "held"
    assert lines[0] == "Automation lock acquisition failed."


def test_automation_lock_lock_reports_legacy_verification_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    legacy_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="legacy",
        exists=True,
        legacy_lock_active=False,
        error="legacy flock lock file",
    )

    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: legacy_info)
    monkeypatch.setattr(automation_lock_impl, "_acquire_legacy_flock_handle", lambda _path: 7)
    monkeypatch.setattr(
        automation_lock_impl,
        "_legacy_handle_matches_current_path",
        lambda *_args: (_ for _ in ()).throw(OSError("verify failed")),
    )
    monkeypatch.setattr(automation_lock_impl, "_release_legacy_flock_handle", lambda _handle: None)

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert data["status"] == "legacy"
    assert data["error"] == "verify failed"
    assert lines[1] == f"Unable to verify the legacy lock file before cleanup: {lock_path}"


def test_automation_lock_lock_reports_when_legacy_handle_cannot_be_acquired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = _automation_lock_path(tmp_path)
    legacy_info = automation_lock_module.AutomationLockInfo(
        path=str(lock_path),
        status="legacy",
        exists=True,
        legacy_lock_active=False,
        error="legacy flock lock file",
    )

    monkeypatch.setattr(automation_lock_impl, "_load_lock_info", lambda _path: legacy_info)
    monkeypatch.setattr(automation_lock_impl, "_acquire_legacy_flock_handle", lambda _path: None)

    exit_code, data, lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), owner_pid=None, dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "legacy"
    assert lines[0] == "Automation lock acquisition failed."


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
