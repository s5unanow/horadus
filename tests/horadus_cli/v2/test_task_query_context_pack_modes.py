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


def _document_paths(documents: list[dict[str, object]]) -> set[str]:
    return {str(document["path"]) for document in documents}


def _included_orientation_paths(data: dict[str, object]) -> set[str]:
    included = data["retrieval_sources"]["included"]
    return {
        str(source["path"])
        for source in included
        if source.get("reason") == "compact orientation metadata"
    }


def _registry_paths(data: dict[str, object]) -> set[str]:
    entries = data["policy"]["legacy_policy_registry"]["entries"]
    return {str(entry["path"]) for entry in entries}


def _excluded_sources(data: dict[str, object]) -> set[str]:
    excluded = data["retrieval_sources"]["excluded"]
    return {str(source["source"]) for source in excluded}


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
    assert data["task_metadata"]["task_status"] == "active"
    assert data["task_metadata"]["autonomous_eligible"] is True
    assert data["orientation"]["current_sprint"]["active_task_lines"] == [
        "- `TASK-901` Stable live fixture"
    ]
    assert "docs/ARCHITECTURE.md" in _document_paths(data["orientation"]["documents"])
    assert data["derived_test_candidates"] == [
        {
            "match_reason": "declared_test_path",
            "path": "tests/horadus_cli/v2/test_cli.py",
            "source_path": "tests/horadus_cli/v2/test_cli.py",
        }
    ]
    assert data["retrieval_sources"]["included"]
    assert "policy-document front matter" in _excluded_sources(data)
    assert "docs/DATA_MODEL.md" in _included_orientation_paths(data)
    registry = data["policy"]["legacy_policy_registry"]
    assert registry["front_matter_required"] is False
    assert "AGENTS.md" in _registry_paths(data)
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
