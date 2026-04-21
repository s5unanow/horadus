from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow._task_intake_store as intake_store_module
from tools.horadus.python.horadus_workflow import task_repo as workflow_task_repo_module
from tools.horadus.python.horadus_workflow import task_workflow_intake as intake_workflow_module

pytestmark = pytest.mark.unit


class _FailingLock:
    def __init__(self, message: str) -> None:
        self._message = message

    def __enter__(self) -> None:
        raise intake_workflow_module.TaskIntakeMutationLockError(self._message)

    def __exit__(self, *_args: object) -> bool:
        return False


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


def test_task_intake_load_and_write_helpers_cover_blank_lines_and_cleanup(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        (
            "\n"
            '{"intake_id": "INTAKE-0001", "recorded_at": "2026-04-02T10:00:00Z", "title": "Title", '
            '"note": "Note", "refs": [], "source_task_id": null, "status": "pending", '
            '"groom_notes": [], "promoted_task_id": null}\n\n'
        ),
        encoding="utf-8",
    )

    entries = task_commands_module._load_task_intake_entries(log_path)
    assert len(entries) == 1

    def fake_replace(self: Path, target: Path) -> Path:
        raise RuntimeError("replace failed")

    monkeypatch.setattr(Path, "replace", fake_replace)
    with pytest.raises(RuntimeError, match="replace failed"):
        task_commands_module._write_task_intake_entries(log_path, entries)
    assert sorted(path.name for path in log_path.parent.iterdir()) == ["entries.jsonl"]

    def fake_named_temporary_file(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("temp creation failed")

    monkeypatch.setattr(
        intake_store_module.tempfile, "NamedTemporaryFile", fake_named_temporary_file
    )
    with pytest.raises(RuntimeError, match="temp creation failed"):
        task_commands_module._write_task_intake_entries(log_path, entries)


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


def test_task_intake_add_data_serializes_concurrent_writers(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo
    monkeypatch.setattr(task_commands_module, "_detect_current_task_id", lambda: "TASK-370")

    original_load = intake_workflow_module._load_task_intake_entries

    def slow_load(path: Path) -> list[intake_workflow_module.TaskIntakeEntry]:
        entries = original_load(path)
        time.sleep(0.05)
        return entries

    monkeypatch.setattr(intake_workflow_module, "_load_task_intake_entries", slow_load)

    start = threading.Event()
    results: list[tuple[int, dict[str, object], list[str]]] = []

    def worker(index: int) -> None:
        assert start.wait(timeout=2)
        results.append(
            task_commands_module.task_intake_add_data(
                title=f"Concurrent capture {index}",
                note=f"Need to persist concurrent write {index}.",
                refs=None,
                source_task=None,
                dry_run=False,
            )
        )

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(1, 5)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 4
    assert all(result[0] == task_commands_module.ExitCode.OK for result in results)

    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    entries = task_commands_module._load_task_intake_entries(log_path)
    assert [entry.intake_id for entry in entries] == [
        "INTAKE-0001",
        "INTAKE-0002",
        "INTAKE-0003",
        "INTAKE-0004",
    ]
    assert sorted(entry.title for entry in entries) == [
        "Concurrent capture 1",
        "Concurrent capture 2",
        "Concurrent capture 3",
        "Concurrent capture 4",
    ]


def test_task_intake_add_data_fails_clearly_when_locking_is_unavailable(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo
    monkeypatch.setattr(
        intake_workflow_module,
        "_task_intake_mutation_lock",
        lambda _log_path: _FailingLock("Unable to safely serialize task intake mutations in test."),
    )

    exit_code, data, lines = task_commands_module.task_intake_add_data(
        title="Lock failure",
        note="Surface lock failures clearly.",
        refs=None,
        source_task="TASK-370",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["log_path"] == "artifacts/agent/task-intake/entries.jsonl"
    assert data["error"] == "Unable to safely serialize task intake mutations in test."
    assert lines == [
        "Task intake failed.",
        "Unable to safely serialize task intake mutations in test.",
    ]


def test_task_intake_groom_data_reports_lock_failures(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo
    monkeypatch.setattr(
        intake_workflow_module,
        "_task_intake_mutation_lock",
        lambda _log_path: _FailingLock("groom lock failed"),
    )

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
    monkeypatch.setattr(
        intake_workflow_module,
        "_task_intake_mutation_lock",
        lambda _log_path: _FailingLock("promote lock failed"),
    )

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
