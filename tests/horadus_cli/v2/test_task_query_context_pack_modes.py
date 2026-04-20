from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_context_pack_text as context_pack_text_module
from tests.horadus_cli.v2.helpers import ARCHIVED_TASK_ID, LIVE_TASK_ID
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


def test_main_tasks_context_pack_explicit_default_preserves_broad_json_output(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = synthetic_task_repo

    result = main(["tasks", "context-pack", LIVE_TASK_ID, "--mode", "default", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["task"]["task_id"] == LIVE_TASK_ID
    assert "suggested_validation_commands" in payload["data"]
    assert "completion_contract" in payload["data"]
    assert "mode_metadata" not in payload["data"]


def test_main_tasks_context_pack_implement_json_output(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = synthetic_task_repo

    result = main(
        ["tasks", "context-pack", LIVE_TASK_ID, "--mode", "implement", "--format", "json"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert "lines" not in payload
    assert data["mode_metadata"]["mode"] == "implement"
    assert data["mode_metadata"]["schema_version"] == "context_pack_implement_v1"
    assert "suggested_validation_commands" not in data
    assert data["task_metadata"]["task_id"] == LIVE_TASK_ID
    assert data["task_metadata"]["declared_paths"] == ["tests/horadus_cli/v2/test_cli.py"]
    assert data["retrieval_sources"]["included"]
    spec_resolution = data["retrieval_sources"]["task_spec_resolution"]
    assert spec_resolution["selected_paths"] == ["tasks/specs/901-stable-live-fixture.md"]
    assert spec_resolution["ambiguous"] is False
    assert any(
        source["source"] == "policy-document front matter"
        for source in data["retrieval_sources"]["excluded"]
    )
    registry = data["policy"]["legacy_policy_registry"]
    assert registry["front_matter_required"] is False
    assert any(entry["path"] == "AGENTS.md" for entry in registry["entries"])
    assert data["policy"]["code_backed_policy"]["workflow_commands"]
    assert (
        f"uv run --no-sync horadus tasks context-pack {LIVE_TASK_ID} --mode implement --format json"
        in data["workflow"]["commands"]
    )
    assert data["workflow"]["completion_contract"]


def test_context_pack_implement_mode_requires_json_output(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = synthetic_task_repo

    result = main(["tasks", "context-pack", LIVE_TASK_ID, "--mode", "implement"])

    assert result == int(task_commands_module.ExitCode.VALIDATION_ERROR)
    captured = capsys.readouterr()
    assert "context-pack --mode implement requires --format json" in captured.err


def test_context_pack_implement_mode_fails_closed_on_ambiguous_specs(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (synthetic_task_repo / "tasks" / "specs" / "901-second-candidate.md").write_text(
        "# TASK-901 second legacy spec\n",
        encoding="utf-8",
    )

    result = main(
        ["tasks", "context-pack", LIVE_TASK_ID, "--mode", "implement", "--format", "json"]
    )

    assert result == int(task_commands_module.ExitCode.VALIDATION_ERROR)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert "ambiguous canonical task spec candidates" in payload["errors"][0]


def test_handle_context_pack_rejects_invalid_mode() -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=LIVE_TASK_ID, mode="invalid", output_format="json")
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["--mode must be one of: default, implement"]


def test_append_completion_contract_lines_skips_commands_line_when_requirement_has_none() -> None:
    lines: list[str] = []

    context_pack_text_module.append_completion_contract_lines(
        lines,
        {
            "enforced_requirements": [
                {
                    "requirement_id": "fixture",
                    "status": "required",
                    "summary": "Fixture enforced requirement.",
                    "reason": "Exercise the no-command branch.",
                    "commands": [],
                    "note": "Still render the note.",
                }
            ],
            "documented_requirements": [],
        },
    )

    assert "  Commands:" not in "\n".join(lines)
    assert "  Note: Still render the note." in lines


def test_context_pack_implement_mode_scopes_archived_lookup_when_explicit(
    synthetic_task_repo: Path,
) -> None:
    _ = synthetic_task_repo

    result = task_commands_module.handle_context_pack(
        argparse.Namespace(
            task_id=ARCHIVED_TASK_ID,
            mode="implement",
            output_format="json",
            include_archive=True,
        )
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data is not None
    excluded = result.data["retrieval_sources"]["excluded"]
    assert (
        f"uv run --no-sync horadus tasks context-pack {ARCHIVED_TASK_ID} "
        "--include-archive --mode implement --format json"
    ) in result.data["workflow"]["commands"]
    assert any(
        source["source"] == "archive/closed_tasks/* except requested task"
        and "explicitly requested task" in source["reason"]
        for source in excluded
    )
