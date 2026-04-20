from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_query as workflow_query_module

pytestmark = pytest.mark.unit


def test_normalized_task_paths_skips_empty_entries_after_cleanup() -> None:
    record = SimpleNamespace(
        files=[
            "`tests/horadus_cli/v2/test_cli.py`",
            "``",
            "tools/horadus/python/horadus_workflow/ (shared helper)",
        ]
    )

    assert workflow_query_module._normalized_task_paths(record) == [
        "tests/horadus_cli/v2/test_cli.py",
        "tools/horadus/python/horadus_workflow/",
    ]


def test_default_context_pack_treats_qualified_workflow_paths_as_shared_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Open Task Ledger",
                "",
                "### TASK-944: Qualified helper fixture",
                "**Priority**: P1",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — qualified workflow helper fixture",
                "",
                "Exercise default context-pack normalization for qualified paths.",
                "",
                "**Files**: `tools/horadus/python/horadus_workflow/` (shared helper)",
                "",
                "**Acceptance Criteria**:",
                "- [ ] default context pack still surfaces shared-helper validation guidance",
                "",
                "---",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tasks_dir / "CURRENT_SPRINT.md").write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-944` Qualified helper fixture\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id="TASK-944", mode="default", output_format="json")
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data is not None
    validation_packs = result.data["caller_aware_validation_packs"]
    assert validation_packs[0]["pack_id"] == "shared-workflow-helpers"
    assert validation_packs[0]["matched_paths"] == ["tools/horadus/python/horadus_workflow/"]
