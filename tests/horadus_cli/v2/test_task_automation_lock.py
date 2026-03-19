from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_automation_lock as automation_lock_module
import tools.horadus.python.horadus_workflow.task_workflow_automation_lock as automation_lock_impl

pytestmark = pytest.mark.unit


def test_automation_lock_check_reports_available_path(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.OK
    assert data["status"] == "available"
    assert lines == [f"Automation lock is available: {lock_path}"]


def test_automation_lock_lock_and_unlock_round_trip(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

    lock_exit_code, lock_data, lock_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), dry_run=False
    )

    assert lock_exit_code == automation_lock_module.ExitCode.OK
    assert lock_data["status"] == "held"
    assert lock_path.is_dir()
    metadata = json.loads((lock_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["path"] == str(lock_path)
    assert lock_lines[0] == f"Automation lock acquired: {lock_path}"

    unlock_exit_code, unlock_data, unlock_lines = (
        automation_lock_module.automation_lock_unlock_data(str(lock_path), dry_run=False)
    )

    assert unlock_exit_code == automation_lock_module.ExitCode.OK
    assert unlock_data["status"] == "released"
    assert not lock_path.exists()
    assert unlock_lines == [f"Automation lock released: {lock_path}"]


def test_automation_lock_lock_fails_when_lock_is_already_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"
    first_exit_code, _, _ = automation_lock_module.automation_lock_lock_data(
        str(lock_path), dry_run=False
    )

    second_exit_code, second_data, second_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), dry_run=False
    )

    assert first_exit_code == automation_lock_module.ExitCode.OK
    assert second_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert second_data["status"] == "held"
    assert second_lines[0] == "Automation lock acquisition failed."
    assert f"- path: {lock_path}" in second_lines


def test_automation_lock_check_reports_broken_directory(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"
    lock_path.mkdir(parents=True)

    exit_code, data, lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=False
    )

    assert exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert data["status"] == "broken"
    assert lines[0] == "Automation lock status: broken"
    assert "- error: missing metadata.json" in lines


def test_automation_lock_helpers_cover_metadata_and_broken_path_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "automation" / "lock"
    lock_path.parent.mkdir(parents=True)

    monkeypatch.setattr(
        automation_lock_impl.getpass,
        "getuser",
        lambda: (_ for _ in ()).throw(OSError("missing user")),
    )
    payload = automation_lock_module._lock_metadata_payload(lock_path)
    assert payload["username"] == "unknown"

    file_path = tmp_path / "file-lock"
    file_path.write_text("legacy lock", encoding="utf-8")
    file_info = automation_lock_module._load_lock_info(file_path)
    assert file_info.status == "broken"
    assert file_info.error == "lock path exists as a file instead of a directory"

    metadata_path = lock_path / "metadata.json"
    lock_path.mkdir()
    metadata_path.write_text("{not-json}", encoding="utf-8")
    invalid_json_info = automation_lock_module._load_lock_info(lock_path)
    assert invalid_json_info.status == "broken"
    assert "invalid metadata.json" in (invalid_json_info.error or "")

    metadata_path.write_text("[]", encoding="utf-8")
    non_mapping_info = automation_lock_module._load_lock_info(lock_path)
    assert non_mapping_info.status == "broken"
    assert non_mapping_info.error == "invalid metadata.json: expected a JSON object"

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


def test_automation_lock_check_and_lock_dry_run_paths_are_reported(tmp_path: Path) -> None:
    lock_path = tmp_path / "automation" / "lock"

    check_exit_code, check_data, check_lines = automation_lock_module.automation_lock_check_data(
        str(lock_path), dry_run=True
    )
    lock_exit_code, lock_data, lock_lines = automation_lock_module.automation_lock_lock_data(
        str(lock_path), dry_run=True
    )

    assert check_exit_code == automation_lock_module.ExitCode.OK
    assert check_data["dry_run"] is True
    assert check_lines[-1] == "Dry run: inspected the current lock state without changing it."
    assert lock_exit_code == automation_lock_module.ExitCode.OK
    assert lock_data["dry_run"] is True
    assert lock_lines[-1] == f"Dry run: would acquire the automation lock at {lock_path}."


def test_automation_lock_lock_handles_mkdir_and_metadata_write_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeParent:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            raise OSError("parent blocked")

    class FakeMissingPath:
        parent = FakeParent()

        def __str__(self) -> str:
            return "/tmp/fake-lock"

        def exists(self) -> bool:
            return False

        def is_file(self) -> bool:
            return False

        def is_dir(self) -> bool:
            return False

        def mkdir(self, *, mode: int) -> None:
            raise AssertionError("should not reach mkdir")

    class FakeRaceParent:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            return None

    class FakeRacePath(FakeMissingPath):
        parent = FakeRaceParent()

        def mkdir(self, *, mode: int) -> None:
            raise FileExistsError("race")

    missing_path = FakeMissingPath()
    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: missing_path)
    mkdir_exit_code, mkdir_data, mkdir_lines = automation_lock_module.automation_lock_lock_data(
        "ignored", dry_run=False
    )
    assert mkdir_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert mkdir_data["status"] == "error"
    assert mkdir_lines[1] == "Unable to create the lock directory: /tmp/fake-lock"

    race_path = FakeRacePath()
    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: race_path)
    race_exit_code, race_data, race_lines = automation_lock_module.automation_lock_lock_data(
        "ignored", dry_run=False
    )
    assert race_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert race_data["status"] == "available"
    assert race_lines[0] == "Automation lock acquisition failed."

    lock_path = tmp_path / "automation" / "write-failure-lock"

    def _failing_write(metadata_path: Path, payload: dict[str, str]) -> None:
        metadata_path.write_text(json.dumps(payload), encoding="utf-8")
        raise OSError("metadata blocked")

    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: lock_path)
    monkeypatch.setattr(automation_lock_impl, "_write_metadata", _failing_write)
    write_exit_code, write_data, write_lines = automation_lock_module.automation_lock_lock_data(
        "ignored", dry_run=False
    )

    assert write_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert write_data["status"] == "error"
    assert write_lines[1] == f"Unable to write lock metadata for {lock_path}."
    assert not lock_path.exists()

    stubborn_lock_path = tmp_path / "automation" / "stubborn-lock"
    original_rmdir = Path.rmdir

    def _still_failing_write(_metadata_path: Path, _payload: dict[str, str]) -> None:
        raise OSError("still blocked")

    def _raising_rmdir(self: Path) -> None:
        if self == stubborn_lock_path:
            raise OSError("cleanup blocked")
        return original_rmdir(self)

    monkeypatch.setattr(
        automation_lock_impl, "_normalize_lock_path", lambda _value: stubborn_lock_path
    )
    monkeypatch.setattr(automation_lock_impl, "_write_metadata", _still_failing_write)
    monkeypatch.setattr(Path, "rmdir", _raising_rmdir)
    stubborn_exit_code, stubborn_data, stubborn_lines = (
        automation_lock_module.automation_lock_lock_data("ignored", dry_run=False)
    )

    assert stubborn_exit_code == automation_lock_module.ExitCode.ENVIRONMENT_ERROR
    assert stubborn_data["status"] == "error"
    assert stubborn_lines[1] == f"Unable to write lock metadata for {stubborn_lock_path}."


def test_automation_lock_unlock_covers_dry_run_missing_file_and_unexpected_entries(
    tmp_path: Path,
) -> None:
    dry_run_path = tmp_path / "automation" / "dry-run-lock"
    dry_exit_code, dry_data, dry_lines = automation_lock_module.automation_lock_unlock_data(
        str(dry_run_path), dry_run=True
    )
    assert dry_exit_code == automation_lock_module.ExitCode.OK
    assert dry_data["dry_run"] is True
    assert dry_lines[-1] == f"Dry run: would release the automation lock at {dry_run_path}."

    missing_exit_code, missing_data, missing_lines = (
        automation_lock_module.automation_lock_unlock_data(str(dry_run_path), dry_run=False)
    )
    assert missing_exit_code == automation_lock_module.ExitCode.OK
    assert missing_data["status"] == "available"
    assert missing_lines == [f"Automation lock was already absent: {dry_run_path}"]

    file_path = tmp_path / "automation-file-lock"
    file_path.write_text("legacy lock", encoding="utf-8")
    file_exit_code, file_data, file_lines = automation_lock_module.automation_lock_unlock_data(
        str(file_path), dry_run=False
    )
    assert file_exit_code == automation_lock_module.ExitCode.OK
    assert file_data["removed_file"] is True
    assert file_lines == [f"Automation lock file removed: {file_path}"]
    assert not file_path.exists()

    unexpected_lock = tmp_path / "automation" / "unexpected-lock"
    unexpected_lock.mkdir(parents=True)
    (unexpected_lock / "metadata.json").write_text("{}", encoding="utf-8")
    (unexpected_lock / "extra.txt").write_text("extra", encoding="utf-8")
    unexpected_exit_code, unexpected_data, unexpected_lines = (
        automation_lock_module.automation_lock_unlock_data(str(unexpected_lock), dry_run=False)
    )
    assert unexpected_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert unexpected_data["unexpected_entries"] == ["extra.txt"]
    assert unexpected_lines == [
        "Automation lock release failed.",
        "Lock directory contains unexpected entries: extra.txt",
    ]


def test_automation_lock_unlock_handles_non_directory_and_missing_metadata_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeOddPath:
        def __str__(self) -> str:
            return "/tmp/odd-lock"

        def exists(self) -> bool:
            return True

        def is_file(self) -> bool:
            return False

        def is_dir(self) -> bool:
            return False

    odd_path = FakeOddPath()
    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: odd_path)
    odd_exit_code, odd_data, odd_lines = automation_lock_module.automation_lock_unlock_data(
        "ignored", dry_run=False
    )
    assert odd_exit_code == automation_lock_module.ExitCode.VALIDATION_ERROR
    assert odd_data["status"] == "broken"
    assert odd_lines[0] == "Automation lock release failed."

    lock_path = tmp_path / "automation" / "missing-metadata-lock"
    lock_path.mkdir(parents=True)
    monkeypatch.setattr(automation_lock_impl, "_normalize_lock_path", lambda _value: lock_path)
    cleanup_exit_code, cleanup_data, cleanup_lines = (
        automation_lock_module.automation_lock_unlock_data("ignored", dry_run=False)
    )
    assert cleanup_exit_code == automation_lock_module.ExitCode.OK
    assert cleanup_data["removed_file"] is False
    assert cleanup_lines == [f"Automation lock released: {lock_path}"]
    assert not lock_path.exists()


def test_automation_lock_handlers_wrap_data_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        type("Args", (), {"path": "/tmp/lock", "dry_run": False})()
    ).lines == ["lock"]
    assert automation_lock_module.handle_automation_lock_unlock(
        type("Args", (), {"path": "/tmp/unlock", "dry_run": False})()
    ).lines == ["unlock"]
