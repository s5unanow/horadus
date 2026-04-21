from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow._task_intake_store as intake_store_module
from tools.horadus.python.horadus_workflow import task_repo as workflow_task_repo_module
from tools.horadus.python.horadus_workflow import task_workflow_intake as intake_workflow_module

pytestmark = pytest.mark.unit


def _seed_intake_repo(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-370: Local task intake",
                "**Priority**: P1",
                "**Estimate**: 4h",
                "",
                "Implement local task intake support.",
                "",
                "**Acceptance Criteria**:",
                "- [ ] intake command exists",
                "",
                "---",
                "",
                "## Future Ideas (Not Scheduled)",
                "",
                "- [ ] None yet.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-370` Local task intake\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")
    return repo_root


@pytest.fixture
def synthetic_intake_repo(tmp_path: Path) -> Path:
    repo_root = _seed_intake_repo(tmp_path)
    workflow_task_repo_module.set_repo_root_override(repo_root)
    try:
        yield repo_root
    finally:
        workflow_task_repo_module.clear_repo_root_override()


def test_task_intake_mutation_lock_covers_platform_and_os_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "artifacts" / "agent" / "task-intake" / "entries.jsonl"

    monkeypatch.setattr(intake_store_module, "fcntl", None)
    with (
        pytest.raises(
            intake_store_module.TaskIntakeMutationLockError,
            match="exclusive file locking is unavailable",
        ),
        intake_store_module.task_intake_mutation_lock(log_path),
    ):
        pass

    class HealthyFcntl:
        LOCK_EX = 1
        LOCK_UN = 8

        @staticmethod
        def flock(_handle: int, _operation: int) -> None:
            return None

    monkeypatch.setattr(intake_store_module, "fcntl", HealthyFcntl)
    monkeypatch.setattr(
        intake_store_module.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )
    with (
        pytest.raises(intake_store_module.TaskIntakeMutationLockError, match="permission denied"),
        intake_store_module.task_intake_mutation_lock(log_path),
    ):
        pass

    class BusyFcntl:
        LOCK_EX = 1
        LOCK_UN = 8

        @staticmethod
        def flock(_handle: int, operation: int) -> None:
            if operation == BusyFcntl.LOCK_EX:
                raise OSError("busy")

    monkeypatch.setattr(intake_store_module, "fcntl", BusyFcntl)
    monkeypatch.setattr(intake_store_module.os, "open", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(intake_store_module.os, "close", lambda _handle: None)
    with (
        pytest.raises(intake_store_module.TaskIntakeMutationLockError, match="busy"),
        intake_store_module.task_intake_mutation_lock(log_path),
    ):
        pass


def test_task_intake_groom_data_dry_run_returns_not_found_without_writing(
    synthetic_intake_repo: Path,
) -> None:
    _ = synthetic_intake_repo

    exit_code, data, lines = task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001"],
        action="dismiss",
        append_notes=None,
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert data["missing_intake_ids"] == ["INTAKE-0001"]
    assert lines[-1] == "Unknown intake ids: INTAKE-0001"


def test_task_intake_groom_data_reports_lock_failures(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo

    @contextmanager
    def fail_lock(_log_path: Path) -> object:
        raise intake_workflow_module.TaskIntakeMutationLockError("groom lock failed")
        yield

    monkeypatch.setattr(intake_workflow_module, "_task_intake_mutation_lock", fail_lock)

    exit_code, data, lines = task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001"],
        action="dismiss",
        append_notes=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "groom lock failed"
    assert lines == ["Task intake grooming failed.", "groom lock failed"]


def test_task_intake_promote_data_dry_run_returns_not_found_without_writing(
    synthetic_intake_repo: Path,
) -> None:
    _ = synthetic_intake_repo

    exit_code, data, lines = task_commands_module.task_intake_promote_data(
        intake_id="INTAKE-0001",
        priority="P1",
        estimate="2h",
        acceptance=["works"],
        files=None,
        description=None,
        assessment_refs=None,
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert data["intake_id"] == "INTAKE-0001"
    assert lines[-1] == "INTAKE-0001 was not found."


def test_task_intake_promote_data_reports_lock_failures(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo

    @contextmanager
    def fail_lock(_log_path: Path) -> object:
        raise intake_workflow_module.TaskIntakeMutationLockError("promote lock failed")
        yield

    monkeypatch.setattr(intake_workflow_module, "_task_intake_mutation_lock", fail_lock)

    exit_code, data, lines = task_commands_module.task_intake_promote_data(
        intake_id="INTAKE-0001",
        priority="P1",
        estimate="2h",
        acceptance=["works"],
        files=None,
        description=None,
        assessment_refs=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "promote lock failed"
    assert lines == ["Task intake promotion failed.", "promote lock failed"]
