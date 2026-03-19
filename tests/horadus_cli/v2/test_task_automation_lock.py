from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_automation_lock as automation_lock_module

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
