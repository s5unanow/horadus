from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_repo as workflow_task_repo_module
import tools.horadus.python.horadus_workflow.task_workflow_context_pack_implement as context_pack_implement_module
from tests.horadus_cli.v2.context_pack_fixtures import seed_human_gated_task_repo
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


def test_context_pack_implement_mode_marks_human_gated_task_ineligible(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_human_gated_task_repo(tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(workflow_task_repo_module, "repo_root", lambda: tmp_path)

    result = main(["tasks", "context-pack", "TASK-189", "--mode", "implement", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert data["task_metadata"]["task_status"] == "active"
    assert data["task_metadata"]["autonomous_eligible"] is False
    assert data["orientation"]["current_sprint"]["active_task_lines"] == [
        "- `TASK-189` Human-gated fixture [REQUIRES_HUMAN]"
    ]
    assert data["orientation"]["current_sprint"]["selection_note_lines"] == [
        "- `TASK-189` remains human-gated until the operator signs off."
    ]
    assert data["orientation"]["current_sprint"]["suggested_sequence_lines"] == [
        "1. `TASK-189` Exercise the ineligible path."
    ]
    assert data["orientation"]["current_sprint"]["applicable_blockers"][0]["task_id"] == "TASK-189"
    assert data["derived_test_candidates"] == [
        {
            "match_reason": "task_ledger_doc",
            "path": "tests/workflow/test_docs_freshness.py",
            "source_path": "tasks/CURRENT_SPRINT.md",
        },
        {
            "match_reason": "workflow_helper_path",
            "path": "tests/workflow",
            "source_path": "tools/horadus/python/horadus_workflow/",
        },
    ]


def test_included_sources_dedupe_current_sprint_orientation_path() -> None:
    sources = context_pack_implement_module._included_sources(
        {
            "source_path": "tasks/BACKLOG.md",
            "backlog_path": "tasks/BACKLOG.md",
            "current_sprint_path": "tasks/CURRENT_SPRINT.md",
        },
        ["- `TASK-901` Stable live fixture"],
        [],
        {},
    )

    assert [source["path"] for source in sources].count("tasks/CURRENT_SPRINT.md") == 1
