from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
import tools.horadus.python.horadus_workflow.task_workflow_completion_contract as completion_contract_module
import tools.horadus.python.horadus_workflow.task_workflow_query as workflow_query_module
from tests.horadus_cli.v2.task_repo_fixtures import LIVE_TASK_ID, SHARED_HELPER_TASK_ID

pytestmark = pytest.mark.unit


def test_handle_context_pack_surfaces_shared_helper_validation_pack(
    synthetic_task_repo: Path,
) -> None:
    _ = synthetic_task_repo
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=SHARED_HELPER_TASK_ID, include_archive=False)
    )

    assert result.exit_code == 0
    assert result.lines is not None
    assert "## Completion Contract" in result.lines
    assert "## Caller-Aware Validation Packs" in result.lines
    assert "make typecheck" in result.lines
    assert "uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit" in result.lines
    assert "make test-integration-docker" in result.lines
    assert result.data is not None
    assert result.data["suggested_validation_commands"][-3:] == [
        "make typecheck",
        "uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit",
        "make test-integration-docker",
    ]
    documented = result.data["completion_contract"]["documented_requirements"]
    assert any(
        requirement["requirement_id"] == "integration-proof" and requirement["status"] == "required"
        for requirement in documented
    )
    assert result.data["caller_aware_validation_packs"] == [
        {
            "pack_id": "shared-workflow-helpers",
            "rationale": "Shared workflow helpers fan out to Horadus CLI and workflow callers.",
            "matched_paths": ["tools/horadus/python/horadus_workflow/task_workflow_shared.py"],
            "commands": [
                "make typecheck",
                "uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit",
            ],
        }
    ]


def test_caller_aware_validation_pack_requires_full_repo_typecheck_for_shared_math() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-909",
        title="Shared math fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise shared math validation-pack guidance."],
        files=["`src/core/trend_engine.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    assert workflow_query_module._caller_aware_validation_pack_matches(record) == [
        {
            "pack_id": "shared-domain-math",
            "rationale": "Shared domain math fans out across probability, replay, and forecast callers.",
            "matched_paths": ["src/core/trend_engine.py"],
            "commands": [
                "make typecheck",
                "uv run --no-sync pytest tests/unit/ -v -m unit",
            ],
        }
    ]


def test_suggested_validation_commands_dedupes_pack_commands() -> None:
    assert workflow_query_module._suggested_validation_commands(
        [
            {
                "pack_id": "fixture",
                "rationale": "Exercise duplicate command handling.",
                "matched_paths": ["fixture.py"],
                "commands": ["make agent-check", "make typecheck"],
            }
        ],
        {
            "enforced_requirements": [],
            "documented_requirements": [],
        },
    ) == [
        "make agent-check",
        "uv run --no-sync horadus tasks local-gate --full",
        "make typecheck",
    ]


def test_completion_contract_marks_docs_only_targeted_test_and_integration_as_n_a() -> None:
    contract = completion_contract_module.build_completion_contract(
        "TASK-910",
        normalized_paths=["docs/AGENT_RUNBOOK.md"],
        planning={"waiver_home_path": "tasks/specs/910-docs-only.md"},
        validation_pack_commands=[],
    )

    documented = {item["requirement_id"]: item for item in contract["documented_requirements"]}
    assert documented["targeted-tests"]["status"] == "not_applicable"
    assert documented["integration-proof"]["status"] == "not_applicable"
    assert documented["docs-updates"]["status"] == "required"
    assert "tasks/specs/910-docs-only.md" in documented["targeted-tests"]["note"]


def test_append_completion_contract_lines_skips_commands_line_when_requirement_has_none() -> None:
    lines: list[str] = []

    workflow_query_module._append_completion_contract_lines(
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


def test_handle_show_remains_unchanged_by_caller_aware_validation_packs(
    synthetic_task_repo: Path,
) -> None:
    _ = synthetic_task_repo
    result = task_commands_module.handle_show(
        argparse.Namespace(task_id=LIVE_TASK_ID, include_archive=False)
    )

    assert result.exit_code == 0
    assert result.data is not None
    assert "caller_aware_validation_packs" not in result.data
