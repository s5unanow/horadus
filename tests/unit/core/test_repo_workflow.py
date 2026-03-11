from __future__ import annotations

import pytest

import src.core.repo_workflow as repo_workflow_module

pytestmark = pytest.mark.unit


def test_repo_workflow_command_helpers_render_task_specific_commands() -> None:
    assert repo_workflow_module.CANONICAL_TASK_WORKFLOW_COMMANDS[1].render("TASK-321") == (
        "uv run --no-sync horadus tasks safe-start TASK-321 --name short-name"
    )
    assert repo_workflow_module.canonical_task_workflow_commands_for_task("TASK-321")[-1] == (
        "uv run --no-sync horadus tasks finish TASK-321"
    )


def test_repo_workflow_guidance_helpers_return_expected_statement_groups() -> None:
    assert repo_workflow_module.completion_guidance_statements()
    assert repo_workflow_module.dependency_aware_guidance_statements()
    assert repo_workflow_module.fallback_guidance_statements()
    assert repo_workflow_module.workflow_policy_guardrail_statements()
