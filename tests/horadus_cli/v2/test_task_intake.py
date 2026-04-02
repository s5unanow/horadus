from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow._task_intake_backlog as intake_backlog_module
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
                "Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.",
                "",
                "---",
                "",
                "## Task ID Policy",
                "",
                "- Task IDs are global and never reused.",
                "- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.",
                "- Next available task IDs start at `TASK-371`.",
                "- Checklist boxes in this file are planning snapshots; canonical completion status lives in `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`.",
                "",
                "---",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-370: Local task intake",
                "**Priority**: P1",
                "**Estimate**: 4h",
                "",
                "Implement local task intake support.",
                "",
                "**Files**: `tools/horadus/python/horadus_workflow/`",
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
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-370` Local task intake",
                "",
            ]
        )
        + "\n",
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


def test_task_intake_list_data_returns_empty_when_log_is_missing(
    synthetic_intake_repo: Path,
) -> None:
    _ = synthetic_intake_repo
    exit_code, data, lines = task_commands_module.task_intake_list_data(status=None, limit=None)

    assert exit_code == 0
    assert data["entries"] == []
    assert data["count"] == 0
    assert lines[-1] == "- None."


def test_task_intake_helper_functions_cover_path_and_timestamp_edges(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = task_commands_module._task_intake_log_path()
    assert str(repo_path).endswith("artifacts/agent/task-intake/entries.jsonl")
    assert task_commands_module._relative_display_path(repo_path) == (
        "artifacts/agent/task-intake/entries.jsonl"
    )

    monkeypatch.setattr(
        workflow_task_repo_module,
        "repo_root",
        lambda: synthetic_intake_repo / "nested-root",
    )
    assert (
        intake_workflow_module._relative_display_path(Path("/tmp/outside.log"))
        == "/tmp/outside.log"
    )

    assert intake_workflow_module._parse_timestamp("2026-04-02T10:00:00Z") == "2026-04-02T10:00:00Z"
    with pytest.raises(ValueError, match="recorded_at must not be empty"):
        intake_workflow_module._parse_timestamp(" ")
    with pytest.raises(ValueError, match="timezone information"):
        intake_workflow_module._parse_timestamp("2026-04-02T10:00:00")


def test_task_intake_helper_functions_cover_normalization_and_branch_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert intake_workflow_module._normalize_optional_task_id(None) is None
    assert intake_workflow_module._normalize_optional_task_id("   ") is None
    assert intake_workflow_module._normalize_optional_task_id("370") == "TASK-370"
    assert intake_workflow_module._normalize_optional_task_id("080") == "TASK-080"
    assert intake_workflow_module._normalize_optional_task_id("TASK-1000") == "TASK-1000"
    assert intake_workflow_module._normalize_text_list(None) == []
    assert intake_workflow_module._normalize_text_list([" one ", " ", "two"]) == ["one", "two"]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: task_commands_module.subprocess.CompletedProcess(
            args=["git"], returncode=1, stdout="", stderr="nope"
        ),
    )
    assert intake_workflow_module._detect_current_task_id() is None

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: task_commands_module.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="HEAD\n", stderr=""
        ),
    )
    assert intake_workflow_module._detect_current_task_id() is None

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: task_commands_module.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="feature/plain-branch\n", stderr=""
        ),
    )
    assert intake_workflow_module._detect_current_task_id() is None

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: task_commands_module.subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="codex/task-370-local-task-intake\n", stderr=""
        ),
    )
    assert intake_workflow_module._detect_current_task_id() == "TASK-370"


def test_task_intake_helper_functions_cover_validation_failures() -> None:
    with pytest.raises(ValueError, match="expected a JSON object"):
        intake_workflow_module._validate_intake_entry([], line_number=1)
    with pytest.raises(ValueError, match="missing fields"):
        intake_workflow_module._validate_intake_entry({}, line_number=1)

    base_payload = {
        "intake_id": "INTAKE-0001",
        "recorded_at": "2026-04-02T10:00:00Z",
        "title": "Title",
        "note": "Note",
        "refs": [],
        "source_task_id": None,
        "status": "pending",
        "groom_notes": [],
        "promoted_task_id": None,
    }

    with pytest.raises(ValueError, match="refs must be a list of strings"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "refs": "bad"}, line_number=1
        )
    with pytest.raises(ValueError, match="groom_notes must be a list of strings"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "groom_notes": "bad"}, line_number=1
        )
    with pytest.raises(ValueError, match="title must not be empty"):
        intake_workflow_module._validate_intake_entry({**base_payload, "title": " "}, line_number=1)
    with pytest.raises(ValueError, match="note must not be empty"):
        intake_workflow_module._validate_intake_entry({**base_payload, "note": " "}, line_number=1)
    with pytest.raises(ValueError, match="source_task_id must be a string or null"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "source_task_id": 7}, line_number=1
        )
    with pytest.raises(ValueError, match="unsupported status"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "status": "archived"}, line_number=1
        )
    with pytest.raises(ValueError, match="promoted_task_id must be a string or null"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "promoted_task_id": 9}, line_number=1
        )
    with pytest.raises(ValueError, match="must include promoted_task_id"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "status": "promoted"}, line_number=1
        )
    with pytest.raises(ValueError, match="only promoted entries may include promoted_task_id"):
        intake_workflow_module._validate_intake_entry(
            {**base_payload, "promoted_task_id": "TASK-371"}, line_number=1
        )


def test_task_intake_load_and_write_helpers_cover_blank_lines_and_cleanup(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n"
        + json.dumps(
            {
                "intake_id": "INTAKE-0001",
                "recorded_at": "2026-04-02T10:00:00Z",
                "title": "Title",
                "note": "Note",
                "refs": [],
                "source_task_id": None,
                "status": "pending",
                "groom_notes": [],
                "promoted_task_id": None,
            }
        )
        + "\n\n",
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
        intake_workflow_module.tempfile, "NamedTemporaryFile", fake_named_temporary_file
    )
    with pytest.raises(RuntimeError, match="temp creation failed"):
        task_commands_module._write_task_intake_entries(log_path, entries)


def test_task_intake_next_id_and_backlog_helpers_cover_edge_cases() -> None:
    with pytest.raises(ValueError, match="Unexpected intake id"):
        task_commands_module._next_intake_id(
            [
                task_commands_module.TaskIntakeEntry(
                    intake_id="BAD-0001",
                    recorded_at="2026-04-02T10:00:00Z",
                    title="Title",
                    note="Note",
                    refs=[],
                    source_task_id=None,
                    status="pending",
                    groom_notes=[],
                    promoted_task_id=None,
                )
            ]
        )

    assert (
        task_commands_module._next_intake_id(
            [
                task_commands_module.TaskIntakeEntry(
                    intake_id="INTAKE-0002",
                    recorded_at="2026-04-02T10:00:00Z",
                    title="Title",
                    note="Note",
                    refs=[],
                    source_task_id=None,
                    status="pending",
                    groom_notes=[],
                    promoted_task_id=None,
                ),
                task_commands_module.TaskIntakeEntry(
                    intake_id="INTAKE-0010",
                    recorded_at="2026-04-02T10:05:00Z",
                    title="Another",
                    note="Note",
                    refs=[],
                    source_task_id=None,
                    status="pending",
                    groom_notes=[],
                    promoted_task_id=None,
                ),
            ]
        )
        == "INTAKE-0011"
    )

    description = intake_backlog_module._render_description_lines(
        [" first line ", "", "second line"], "fallback"
    )
    assert description == ["first line", "", "second line"]
    assert intake_backlog_module._render_description_lines(None, "fallback") == ["fallback"]
    assert intake_backlog_module._render_description_lines(["", " second line "], "fallback") == [
        "second line"
    ]
    assert intake_backlog_module._format_files(["foo.py", " ", "`bar.py`"]) == (
        "`foo.py`, `bar.py`"
    )

    rendered = task_commands_module._render_backlog_task_block(
        task_id="TASK-371",
        title="Title",
        priority="P1",
        estimate="2h",
        description=["Body"],
        files=[],
        acceptance_criteria=["one"],
        assessment_refs=[],
    )
    assert "**Assessment-Ref**:" not in rendered
    assert "**Files**:" not in rendered

    with pytest.raises(ValueError, match="terminal Future Ideas section"):
        task_commands_module._insert_backlog_task_block("# Backlog\n", "### TASK-371: Title")

    inserted_backlog = intake_backlog_module.insert_backlog_task_block(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-370: Existing",
                "**Acceptance Criteria**:",
                "- [ ] done",
                "",
                "---",
                "",
                "## Future Ideas (Not Scheduled)",
                "",
                "- [ ] None yet.",
                "",
            ]
        ),
        "### TASK-371: Title",
    )
    assert inserted_backlog == "\n".join(
        [
            "# Backlog",
            "",
            "## Open Task Ledger",
            "",
            "### TASK-370: Existing",
            "**Acceptance Criteria**:",
            "- [ ] done",
            "",
            "---",
            "",
            "### TASK-371: Title",
            "",
            "---",
            "",
            "## Future Ideas (Not Scheduled)",
            "",
            "- [ ] None yet.",
            "",
        ]
    )

    promoted_task_id, updated_backlog_text = intake_backlog_module.allocate_backlog_task_id(
        "- Next available task IDs start at `TASK-999`.\n"
    )
    assert promoted_task_id == "TASK-999"
    assert updated_backlog_text == "- Next available task IDs start at `TASK-1000`.\n"

    next_promoted_task_id, next_updated_backlog_text = (
        intake_backlog_module.allocate_backlog_task_id(updated_backlog_text)
    )
    assert next_promoted_task_id == "TASK-1000"
    assert next_updated_backlog_text == "- Next available task IDs start at `TASK-1001`.\n"


def test_task_intake_add_and_list_data_happy_path(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo
    monkeypatch.setattr(task_commands_module, "_detect_current_task_id", lambda: "TASK-370")

    exit_code, data, lines = task_commands_module.task_intake_add_data(
        title="Capture workflow follow-up",
        note="Need a local intake flow that avoids dirty ledgers.",
        refs=["docs/AGENT_RUNBOOK.md"],
        source_task=None,
        dry_run=False,
    )

    assert exit_code == 0
    assert data["entry"]["intake_id"] == "INTAKE-0001"
    assert data["entry"]["source_task_id"] == "TASK-370"
    assert "Task intake recorded." in lines

    list_exit_code, list_data, list_lines = task_commands_module.task_intake_list_data(
        status=None, limit=None
    )

    assert list_exit_code == 0
    assert list_data["count"] == 1
    assert list_data["entries"][0]["refs"] == ["docs/AGENT_RUNBOOK.md"]
    assert any("INTAKE-0001 [pending] Capture workflow follow-up" in line for line in list_lines)


def test_task_intake_list_data_fails_closed_for_malformed_json(
    synthetic_intake_repo: Path,
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("{bad json}\n", encoding="utf-8")

    exit_code, _data, lines = task_commands_module.task_intake_list_data(status=None, limit=None)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines == [
        "Task intake listing failed.",
        "Invalid task intake JSON at line 1: Expecting property name enclosed in double quotes.",
    ]


def test_task_intake_add_and_list_data_cover_validation_edges(
    synthetic_intake_repo: Path,
) -> None:
    _ = synthetic_intake_repo
    assert (
        task_commands_module.task_intake_add_data(
            title=" ",
            note="note",
            refs=None,
            source_task="TASK-370",
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_add_data(
            title="title",
            note=" ",
            refs=None,
            source_task="TASK-370",
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_add_data(
            title="title",
            note="note",
            refs=None,
            source_task="bad",
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("{bad json}\n", encoding="utf-8")
    assert (
        task_commands_module.task_intake_add_data(
            title="title",
            note="note",
            refs=None,
            source_task="TASK-370",
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    assert task_commands_module.task_intake_list_data(status="bad", limit=None)[0] == (
        task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert task_commands_module.task_intake_list_data(status=None, limit=0)[0] == (
        task_commands_module.ExitCode.VALIDATION_ERROR
    )


def test_task_intake_add_data_still_succeeds_with_dirty_tracked_files(
    synthetic_intake_repo: Path,
) -> None:
    backlog_path = synthetic_intake_repo / "tasks" / "BACKLOG.md"
    original_backlog = backlog_path.read_text(encoding="utf-8")
    backlog_path.write_text(original_backlog + "\n<!-- dirty -->\n", encoding="utf-8")

    exit_code, data, _lines = task_commands_module.task_intake_add_data(
        title="Dirty tree follow-up",
        note="Capture should still work while tracked files are dirty.",
        refs=None,
        source_task="TASK-370",
        dry_run=False,
    )

    assert exit_code == 0
    assert data["entry"]["intake_id"] == "INTAKE-0001"
    assert backlog_path.read_text(encoding="utf-8").endswith("\n<!-- dirty -->\n")
    assert (
        synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    ).exists()


def test_task_intake_add_data_dry_run_does_not_write_log(
    synthetic_intake_repo: Path,
) -> None:
    exit_code, data, _lines = task_commands_module.task_intake_add_data(
        title="Dry run",
        note="No mutation expected.",
        refs=["ref-one"],
        source_task="TASK-370",
        dry_run=True,
    )

    assert exit_code == 0
    assert data["dry_run"] is True
    assert not (synthetic_intake_repo / "artifacts" / "agent" / "task-intake").exists()


def test_task_intake_add_data_omits_source_line_when_no_branch_task_detected(
    synthetic_intake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = synthetic_intake_repo
    monkeypatch.setattr(task_commands_module, "_detect_current_task_id", lambda: None)

    exit_code, data, lines = task_commands_module.task_intake_add_data(
        title="No source task",
        note="Capture later work without a branch task id.",
        refs=None,
        source_task=None,
        dry_run=True,
    )

    assert exit_code == 0
    assert data["entry"]["source_task_id"] is None
    assert all(not line.startswith("Source task:") for line in lines)
    assert all(not line.startswith("Refs:") for line in lines)


def test_task_intake_groom_data_batch_dismiss_and_restore(
    synthetic_intake_repo: Path,
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    task_commands_module._write_task_intake_entries(
        log_path,
        [
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0001",
                recorded_at="2026-04-02T10:00:00Z",
                title="One",
                note="First",
                refs=[],
                source_task_id="TASK-370",
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            ),
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0002",
                recorded_at="2026-04-02T10:05:00Z",
                title="Two",
                note="Second",
                refs=[],
                source_task_id=None,
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            ),
        ],
    )

    exit_code, data, _lines = task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001", "INTAKE-0002"],
        action="dismiss",
        append_notes=["Defer until sprint planning."],
        dry_run=False,
    )

    assert exit_code == 0
    assert data["updated_status"] == "dismissed"
    dismissed_entries = task_commands_module._load_task_intake_entries(log_path)
    assert [entry.status for entry in dismissed_entries] == ["dismissed", "dismissed"]
    assert dismissed_entries[0].groom_notes == ["Defer until sprint planning."]

    restore_exit_code, restore_data, _restore_lines = task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001"],
        action="restore",
        append_notes=None,
        dry_run=False,
    )

    assert restore_exit_code == 0
    assert restore_data["updated_status"] == "pending"
    restored_entries = task_commands_module._load_task_intake_entries(log_path)
    assert [entry.status for entry in restored_entries] == ["pending", "dismissed"]


def test_task_intake_groom_data_covers_validation_and_dry_run_edges(
    synthetic_intake_repo: Path,
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    task_commands_module._write_task_intake_entries(
        log_path,
        [
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0001",
                recorded_at="2026-04-02T10:00:00Z",
                title="Promoted",
                note="done",
                refs=[],
                source_task_id=None,
                status="promoted",
                groom_notes=[],
                promoted_task_id="TASK-371",
            )
        ],
    )

    assert (
        task_commands_module.task_intake_groom_data(
            intake_ids=["INTAKE-0001"],
            action="archive",
            append_notes=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_groom_data(
            intake_ids=["bad"],
            action="dismiss",
            append_notes=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_groom_data(
            intake_ids=["INTAKE-0002"],
            action="dismiss",
            append_notes=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.NOT_FOUND
    )
    assert (
        task_commands_module.task_intake_groom_data(
            intake_ids=["INTAKE-0001"],
            action="dismiss",
            append_notes=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    log_path.write_text("{bad json}\n", encoding="utf-8")
    assert (
        task_commands_module.task_intake_groom_data(
            intake_ids=["INTAKE-0001"],
            action="dismiss",
            append_notes=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    task_commands_module._write_task_intake_entries(
        log_path,
        [
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0001",
                recorded_at="2026-04-02T10:00:00Z",
                title="Pending",
                note="note",
                refs=[],
                source_task_id=None,
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            )
        ],
    )
    exit_code, data, _lines = task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001"],
        action="dismiss",
        append_notes=None,
        dry_run=True,
    )
    assert exit_code == 0
    assert data["dry_run"] is True
    assert task_commands_module._load_task_intake_entries(log_path)[0].status == "pending"


def test_task_intake_promote_data_updates_backlog_and_marks_entry_promoted(
    synthetic_intake_repo: Path,
) -> None:
    add_exit_code, add_data, _add_lines = task_commands_module.task_intake_add_data(
        title="Add CLI intake commands",
        note="Need a command surface for capture and promotion.",
        refs=["docs/AGENT_RUNBOOK.md"],
        source_task="TASK-370",
        dry_run=False,
    )
    assert add_exit_code == 0

    exit_code, data, lines = task_commands_module.task_intake_promote_data(
        intake_id=add_data["entry"]["intake_id"],
        priority="P1 (High)",
        estimate="4-6 hours",
        acceptance=["agents can promote intake to backlog"],
        files=["tools/horadus/python/horadus_workflow/task_workflow_intake.py"],
        description=None,
        assessment_refs=["tasks/assessments/example.md"],
        dry_run=False,
    )

    backlog_text = (synthetic_intake_repo / "tasks" / "BACKLOG.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert data["promoted_task_id"] == "TASK-371"
    assert "Task intake promoted." in lines
    assert "- Next available task IDs start at `TASK-372`." in backlog_text
    assert "### TASK-371: Add CLI intake commands" in backlog_text
    assert "**Assessment-Ref**:" in backlog_text
    assert backlog_text.index("### TASK-371: Add CLI intake commands") < backlog_text.index(
        "## Future Ideas (Not Scheduled)"
    )

    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    promoted_entries = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert promoted_entries[0]["status"] == "promoted"
    assert promoted_entries[0]["promoted_task_id"] == "TASK-371"


def test_task_intake_list_data_limit_and_rendering_cover_promoted_entries(
    synthetic_intake_repo: Path,
) -> None:
    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    task_commands_module._write_task_intake_entries(
        log_path,
        [
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0001",
                recorded_at="2026-04-02T10:00:00Z",
                title="Promoted",
                note="Already moved into the backlog.",
                refs=[],
                source_task_id=None,
                status="promoted",
                groom_notes=[],
                promoted_task_id="TASK-1000",
            ),
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0002",
                recorded_at="2026-04-02T10:05:00Z",
                title="Pending",
                note="Should be trimmed by the limit.",
                refs=["docs/AGENT_RUNBOOK.md"],
                source_task_id="TASK-370",
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            ),
        ],
    )

    exit_code, data, lines = task_commands_module.task_intake_list_data(status=None, limit=1)

    assert exit_code == 0
    assert data["count"] == 1
    assert [entry["intake_id"] for entry in data["entries"]] == ["INTAKE-0001"]
    assert any(line == "  promoted_task_id: TASK-1000" for line in lines)
    assert all("source_task:" not in line for line in lines)
    assert all("  refs:" not in line for line in lines)


def test_task_intake_promote_data_covers_validation_and_dry_run_edges(
    synthetic_intake_repo: Path,
) -> None:
    assert (
        task_commands_module.task_intake_promote_data(
            intake_id="bad",
            priority="P1",
            estimate="2h",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    task_commands_module.task_intake_add_data(
        title="Pending",
        note="note",
        refs=None,
        source_task="TASK-370",
        dry_run=False,
    )
    assert (
        task_commands_module.task_intake_promote_data(
            intake_id="INTAKE-0001",
            priority=" ",
            estimate="2h",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_promote_data(
            intake_id="INTAKE-0001",
            priority="P1",
            estimate=" ",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )
    assert (
        task_commands_module.task_intake_promote_data(
            intake_id="INTAKE-0001",
            priority="P1",
            estimate="2h",
            acceptance=[],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    log_path = synthetic_intake_repo / "artifacts" / "agent" / "task-intake" / "entries.jsonl"
    log_path.write_text("{bad json}\n", encoding="utf-8")
    assert (
        task_commands_module.task_intake_promote_data(
            intake_id="INTAKE-0001",
            priority="P1",
            estimate="2h",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )[0]
        == task_commands_module.ExitCode.VALIDATION_ERROR
    )

    task_commands_module._write_task_intake_entries(
        log_path,
        [
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0001",
                recorded_at="2026-04-02T10:00:00Z",
                title="First",
                note="note",
                refs=[],
                source_task_id=None,
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            ),
            task_commands_module.TaskIntakeEntry(
                intake_id="INTAKE-0002",
                recorded_at="2026-04-02T10:05:00Z",
                title="Second",
                note="note two",
                refs=[],
                source_task_id=None,
                status="pending",
                groom_notes=[],
                promoted_task_id=None,
            ),
        ],
    )
    exit_code, data, _lines = task_commands_module.task_intake_promote_data(
        intake_id="INTAKE-0001",
        priority="P1",
        estimate="2h",
        acceptance=["works"],
        files=None,
        description=["explicit description"],
        assessment_refs=None,
        dry_run=True,
    )
    assert exit_code == 0
    assert data["dry_run"] is True
    assert "### TASK-371: First" in data["task_block"]
    assert task_commands_module._load_task_intake_entries(log_path)[0].status == "pending"


def test_task_intake_promote_data_fails_for_unknown_or_non_pending_entries(
    synthetic_intake_repo: Path,
) -> None:
    missing_exit_code, missing_data, missing_lines = task_commands_module.task_intake_promote_data(
        intake_id="INTAKE-0009",
        priority="P1",
        estimate="2h",
        acceptance=["works"],
        files=None,
        description=None,
        assessment_refs=None,
        dry_run=False,
    )

    assert missing_exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert missing_data["intake_id"] == "INTAKE-0009"
    assert missing_lines[-1] == "INTAKE-0009 was not found."

    task_commands_module.task_intake_add_data(
        title="Dismiss me",
        note="Already triaged.",
        refs=None,
        source_task="TASK-370",
        dry_run=False,
    )
    task_commands_module.task_intake_groom_data(
        intake_ids=["INTAKE-0001"],
        action="dismiss",
        append_notes=None,
        dry_run=False,
    )

    dismissed_exit_code, dismissed_data, dismissed_lines = (
        task_commands_module.task_intake_promote_data(
            intake_id="INTAKE-0001",
            priority="P1",
            estimate="2h",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )
    )

    assert dismissed_exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert dismissed_data["status"] == "dismissed"
    assert dismissed_lines[-1] == (
        "INTAKE-0001 is dismissed; only pending entries can be promoted."
    )


def test_task_intake_promote_data_fails_when_backlog_header_is_malformed(
    synthetic_intake_repo: Path,
) -> None:
    backlog_path = synthetic_intake_repo / "tasks" / "BACKLOG.md"
    backlog_path.write_text(
        backlog_path.read_text(encoding="utf-8").replace(
            "- Next available task IDs start at `TASK-371`.",
            "- Next available task ids are unclear.",
        ),
        encoding="utf-8",
    )
    task_commands_module.task_intake_add_data(
        title="Bad backlog header",
        note="Promotion should fail closed when the next id marker is missing.",
        refs=None,
        source_task="TASK-370",
        dry_run=False,
    )

    exit_code, _data, lines = task_commands_module.task_intake_promote_data(
        intake_id="INTAKE-0001",
        priority="P1",
        estimate="2h",
        acceptance=["works"],
        files=None,
        description=None,
        assessment_refs=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[-1] == "Unable to locate the next available task id marker in tasks/BACKLOG.md."


def test_task_intake_handlers_wrap_data_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_intake_add_data",
        lambda **_kwargs: (0, {"ok": True}, ["add"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_intake_list_data",
        lambda **_kwargs: (0, {"ok": True}, ["list"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_intake_groom_data",
        lambda **_kwargs: (0, {"ok": True}, ["groom"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_intake_promote_data",
        lambda **_kwargs: (0, {"ok": True}, ["promote"]),
    )

    assert task_commands_module.handle_task_intake_add(
        argparse.Namespace(title="t", note="n", refs=None, source_task=None, dry_run=False)
    ).lines == ["add"]
    assert task_commands_module.handle_task_intake_list(
        argparse.Namespace(status=None, limit=None)
    ).lines == ["list"]
    assert task_commands_module.handle_task_intake_groom(
        argparse.Namespace(
            intake_ids=["INTAKE-0001"], dismiss=True, append_notes=None, dry_run=False
        )
    ).lines == ["groom"]
    assert task_commands_module.handle_task_intake_promote(
        argparse.Namespace(
            intake_id="INTAKE-0001",
            priority="P1",
            estimate="2h",
            acceptance=["works"],
            files=None,
            description=None,
            assessment_refs=None,
            dry_run=False,
        )
    ).lines == ["promote"]
