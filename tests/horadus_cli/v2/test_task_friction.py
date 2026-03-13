from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module

pytestmark = pytest.mark.unit


def test_record_friction_data_dry_run_reports_entry_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 197 --squash",
        friction_type="forced_fallback",
        note="Needed a manual merge fallback.",
        suggested_improvement="Teach finish to surface the blocker better.",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert any(
        "Dry run: would append structured workflow friction entry." in line for line in lines
    )
    assert not (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    ).exists()


def test_record_friction_data_appends_structured_jsonl_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks start TASK-265 --name friction-log",
        fallback_used="git switch -c codex/task-265-friction-log",
        friction_type="missing_cli_surface",
        note="Needed lower-level git fallback.",
        suggested_improvement="Expose the missing workflow surface in horadus.",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is False
    assert lines[-1] == "Recorded structured workflow friction entry."

    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    payload = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert payload == [
        {
            "command_attempted": "uv run --no-sync horadus tasks start TASK-265 --name friction-log",
            "fallback_used": "git switch -c codex/task-265-friction-log",
            "friction_type": "missing_cli_surface",
            "note": "Needed lower-level git fallback.",
            "recorded_at": payload[0]["recorded_at"],
            "suggested_improvement": "Expose the missing workflow surface in horadus.",
            "task_id": "TASK-265",
        }
    ]
    assert payload[0]["recorded_at"].endswith("Z")


def test_record_friction_data_reports_filesystem_write_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    def fail_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 199 --squash",
        friction_type="forced_fallback",
        note="Needed manual recovery.",
        suggested_improvement="Surface write failures cleanly.",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["dry_run"] is False
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert data["error"] == "permission denied"
    assert lines[-2:] == [
        "Workflow friction logging failed while writing the gitignored artifact.",
        "Filesystem error: permission denied",
    ]
    assert not (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    ).exists()


def test_record_friction_data_rejects_invalid_friction_type() -> None:
    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 199 --squash",
        friction_type="not-valid",
        note="Needed manual recovery.",
        suggested_improvement="Validate friction types.",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["friction_type"] == "not-valid"
    assert lines[0] == "Workflow friction logging failed."


def test_load_workflow_friction_entries_rejects_invalid_json_and_missing_fields(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "entries.jsonl"
    log_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid workflow friction JSON"):
        task_commands_module._load_workflow_friction_entries(log_path)

    log_path.write_text(json.dumps({"task_id": "TASK-265"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing fields"):
        task_commands_module._load_workflow_friction_entries(log_path)

    log_path.write_text('["not-an-object"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object"):
        task_commands_module._load_workflow_friction_entries(log_path)


def test_load_workflow_friction_entries_skip_blank_lines_and_empty_day_reports_no_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n"
        + json.dumps(
            {
                "recorded_at": "2026-03-07T09:00:00Z",
                "task_id": "TASK-265",
                "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                "fallback_used": "gh pr merge 199 --squash",
                "friction_type": "forced_fallback",
                "note": "Older entry outside the report window.",
                "suggested_improvement": "Surface GitHub review blockers more clearly.",
            },
            sort_keys=True,
        )
        + "\n\n",
        encoding="utf-8",
    )

    entries = task_commands_module._load_workflow_friction_entries(log_path)
    assert len(entries) == 1

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 0
    assert lines[-1] == "Wrote grouped workflow friction summary."
    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    assert (
        "- No workflow friction entries were recorded for this UTC day."
        in report_path.read_text(encoding="utf-8")
    )


def test_summarize_workflow_friction_deduplicates_nonblank_notes() -> None:
    entries = [
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T08:00:00Z",
            task_id="TASK-265",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="Repeated note",
            suggested_improvement="Improve merge recovery",
        ),
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T09:00:00Z",
            task_id="TASK-266",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="Repeated note",
            suggested_improvement="Improve merge recovery",
        ),
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T10:00:00Z",
            task_id="TASK-267",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="",
            suggested_improvement="Improve merge recovery",
        ),
    ]

    patterns, _improvements, counts = task_commands_module._summarize_workflow_friction(entries)

    assert counts["forced_fallback"] == 3
    assert len(patterns) == 1
    assert patterns[0].notes == ["Repeated note"]


def test_summarize_friction_data_writes_grouped_daily_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "recorded_at": "2026-03-08T08:00:00Z",
                        "task_id": "TASK-265",
                        "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                        "fallback_used": "gh pr merge 199 --squash",
                        "friction_type": "forced_fallback",
                        "note": "Needed a manual merge fallback.",
                        "suggested_improvement": "Surface GitHub review blockers more clearly.",
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "recorded_at": "2026-03-08T09:00:00Z",
                        "task_id": "TASK-266",
                        "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                        "fallback_used": "gh pr merge 199 --squash",
                        "friction_type": "forced_fallback",
                        "note": "The old review thread still blocked merge readiness.",
                        "suggested_improvement": "Surface GitHub review blockers more clearly.",
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "recorded_at": "2026-03-07T23:30:00Z",
                        "task_id": "TASK-264",
                        "command_attempted": "uv run --no-sync horadus tasks safe-start TASK-264 --name workflow-drift-check",
                        "fallback_used": "git switch -c codex/task-264-workflow-drift-check",
                        "friction_type": "missing_cli_surface",
                        "note": "Older entry outside the report window.",
                        "suggested_improvement": "Add a missing safe-start flow.",
                    },
                    sort_keys=True,
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 2
    assert data["pattern_count"] == 1
    assert data["improvement_count"] == 1
    assert lines[-1] == "Wrote grouped workflow friction summary."

    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    report = report_path.read_text(encoding="utf-8")
    assert "# Horadus Workflow Friction Summary - 2026-03-08" in report
    assert "### 1. `forced_fallback` x2" in report
    assert "Surface GitHub review blockers more clearly." in report
    assert "`TASK-265`, `TASK-266`" in report
    assert "Do not auto-create backlog tasks from this report" in report
    assert (
        "Investigate Horadus workflow friction around Surface GitHub review blockers more clearly."
        in report
    )


def test_summarize_friction_data_rejects_invalid_report_date() -> None:
    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-99-99",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {}
    assert lines == ["Invalid report date '2026-99-99'. Expected YYYY-MM-DD."]


def test_summarize_friction_data_reports_invalid_log_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("{bad json}\n", encoding="utf-8")

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert lines == [
        "Workflow friction summary failed: Invalid workflow friction JSON at line 1: Expecting property name enclosed in double quotes."
    ]


def test_summarize_friction_data_creates_empty_daily_checkpoint_when_log_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 0
    assert data["missing_log"] is True
    assert lines[-1] == "Wrote grouped workflow friction summary."

    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    report = report_path.read_text(encoding="utf-8")
    assert (
        "No workflow friction log exists yet; this report is an empty daily checkpoint." in report
    )
    assert "- None for this report window." in report


def test_summarize_friction_data_reports_filesystem_read_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("[]\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == log_path:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert data["error"] == "permission denied"
    assert lines == [
        "Workflow friction summary failed while reading the friction log artifact.",
        "Filesystem error: permission denied",
    ]


def test_summarize_friction_data_dry_run_skips_writing_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input="artifacts/custom-report.md",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert lines[-1] == "Dry run: would write grouped workflow friction summary."
    assert not (tmp_path / "artifacts" / "custom-report.md").exists()


def test_summarize_friction_data_reports_filesystem_write_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    original_mkdir = Path.mkdir

    def fail_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == tmp_path / "artifacts":
            raise OSError("disk full")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input="artifacts/report.md",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "disk full"
    assert lines[-2:] == [
        "Workflow friction summary failed while writing the report artifact.",
        "Filesystem error: disk full",
    ]


def test_handle_record_friction_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_record_friction(
        argparse.Namespace(
            task_id="bad-task",
            command_attempted="cmd",
            fallback_used="fallback",
            friction_type="forced_fallback",
            note="note",
            suggested_improvement="improve",
        )
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]
