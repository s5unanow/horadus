from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.horadus_cli.v2.context_pack_assertions import (
    document_paths,
    excluded_sources,
    included_orientation_paths,
    registry_paths,
)
from tests.horadus_cli.v2.helpers import LIVE_TASK_ID
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


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
    assert "docs/ARCHITECTURE.md" in document_paths(data["orientation"]["documents"])
    assert data["derived_test_candidates"] == [
        {
            "match_reason": "declared_test_path",
            "path": "tests/horadus_cli/v2/test_cli.py",
            "source_path": "tests/horadus_cli/v2/test_cli.py",
        }
    ]
    assert data["retrieval_sources"]["included"]
    assert "policy-document front matter" in excluded_sources(data)
    assert "docs/DATA_MODEL.md" in included_orientation_paths(data)
    registry = data["policy"]["legacy_policy_registry"]
    assert registry["front_matter_required"] is False
    assert "AGENTS.md" in registry_paths(data)
    assert data["policy"]["code_backed_policy"]["workflow_commands"]
    assert (
        f"uv run --no-sync horadus tasks context-pack {LIVE_TASK_ID} --mode implement --format json"
        in data["workflow"]["commands"]
    )
    assert data["workflow"]["completion_contract"]
