from __future__ import annotations

import argparse

import pytest

import tools.horadus.python.horadus_cli.task_commands as task_parser_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module

pytestmark = pytest.mark.unit


def test_task_commands_register_task_commands_wires_all_task_subcommands() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    task_parser_module.register_task_commands(subparsers)
    args = parser.parse_args(
        [
            "tasks",
            "record-friction",
            "TASK-297",
            "--command-attempted",
            "uv run --no-sync horadus tasks finish TASK-297",
            "--fallback-used",
            "none",
            "--friction-type",
            "forced_fallback",
            "--note",
            "coverage gap",
            "--suggested-improvement",
            "add wrapper coverage",
            "--format",
            "json",
            "--dry-run",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "record-friction"
    assert args.task_id == "TASK-297"
    assert args.output_format == "json"
    assert args.dry_run is True
    assert args.handler is task_commands_module.handle_record_friction


def test_task_commands_registers_local_review_and_keeps_local_gate_wiring() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    task_parser_module.register_task_commands(subparsers)
    review_args = parser.parse_args(
        [
            "tasks",
            "local-review",
            "--provider",
            "claude",
            "--base",
            "main",
            "--instructions",
            "Focus on regressions.",
            "--allow-provider-fallback",
            "--save-raw-output",
            "--usefulness",
            "not-useful",
        ]
    )
    gate_args = parser.parse_args(["tasks", "local-gate", "--full"])

    assert review_args.tasks_command == "local-review"
    assert review_args.provider == "claude"
    assert review_args.base == "main"
    assert review_args.usefulness == "not-useful"
    assert review_args.handler is task_commands_module.handle_local_review
    assert gate_args.handler is task_commands_module.handle_local_gate


def test_task_commands_registers_automation_lock_subcommands() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    task_parser_module.register_task_commands(subparsers)
    args = parser.parse_args(
        [
            "tasks",
            "automation-lock",
            "lock",
            "--path",
            "/tmp/horadus-lock",
            "--format",
            "json",
            "--dry-run",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "automation-lock"
    assert args.automation_lock_command == "lock"
    assert args.path == "/tmp/horadus-lock"
    assert args.output_format == "json"
    assert args.dry_run is True
    assert args.handler is task_commands_module.handle_automation_lock_lock

    unlock_args = parser.parse_args(
        [
            "tasks",
            "automation-lock",
            "unlock",
            "--path",
            "/tmp/horadus-lock",
            "--owner-pid",
            "123",
        ]
    )
    assert unlock_args.automation_lock_command == "unlock"
    assert unlock_args.owner_pid == 123
    assert unlock_args.handler is task_commands_module.handle_automation_lock_unlock


def test_command_handlers_wrap_data_functions_and_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_finish_task_data(
        task_input: str | None, *, dry_run: bool
    ) -> tuple[int, dict[str, object], list[str]]:
        return (
            task_commands_module.ExitCode.OK,
            {"task_id": task_input, "dry_run": dry_run},
            ["finish"],
        )

    monkeypatch.setattr(
        task_commands_module,
        "finish_task_data",
        fake_finish_task_data,
    )
    monkeypatch.setattr(
        task_commands_module,
        "record_friction_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["record"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "summarize_friction_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["summary"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["lifecycle"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "local_gate_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["gate"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "local_review_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["review"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "automation_lock_check_data",
        lambda *_args, **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["check"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "automation_lock_lock_data",
        lambda *_args, **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["lock"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "automation_lock_unlock_data",
        lambda *_args, **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["unlock"]),
    )

    assert task_commands_module.handle_finish(
        argparse.Namespace(task_id="257", dry_run=False)
    ).lines == ["finish"]
    assert task_commands_module.handle_record_friction(
        argparse.Namespace(
            task_id="257",
            command_attempted="cmd",
            fallback_used="fallback",
            friction_type="forced_fallback",
            note="note",
            suggested_improvement="improve",
            dry_run=False,
        )
    ).lines == ["record"]
    assert task_commands_module.handle_summarize_friction(
        argparse.Namespace(date="2026-03-08", output=None, dry_run=False)
    ).lines == ["summary"]
    assert task_commands_module.handle_lifecycle(
        argparse.Namespace(task_id="257", strict=False, dry_run=False)
    ).lines == ["lifecycle"]
    assert task_commands_module.handle_local_gate(
        argparse.Namespace(full=True, dry_run=False)
    ).lines == ["gate"]
    assert task_commands_module.handle_local_review(
        argparse.Namespace(
            provider="claude",
            base="main",
            instructions=None,
            allow_provider_fallback=False,
            save_raw_output=False,
            usefulness="pending",
            dry_run=False,
        )
    ).lines == ["review"]
    assert task_commands_module.handle_automation_lock_check(
        argparse.Namespace(path="/tmp/check", dry_run=False)
    ).lines == ["check"]
    assert task_commands_module.handle_automation_lock_lock(
        argparse.Namespace(path="/tmp/lock", owner_pid=None, dry_run=False)
    ).lines == ["lock"]
    assert task_commands_module.handle_automation_lock_unlock(
        argparse.Namespace(path="/tmp/unlock", owner_pid=123, dry_run=False)
    ).lines == ["unlock"]

    assert task_commands_module.handle_finish(
        argparse.Namespace(task_id="bad-task", dry_run=False)
    ).error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]
    assert task_commands_module.handle_lifecycle(
        argparse.Namespace(task_id="bad-task", strict=False, dry_run=False)
    ).error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_finish_context_patch_still_flows_through_task_workflow_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = task_commands_module._task_blocked(
        "compat finish blocker.",
        next_action="re-run after compat check.",
    )

    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda _name: "/bin/fake",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: expected,
    )

    assert task_commands_module.finish_task_data("TASK-314", dry_run=False) == expected
