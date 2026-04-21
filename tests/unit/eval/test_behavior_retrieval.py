from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.eval.behavior as behavior_module
import src.eval.behavior_cases_retrieval as behavior_cases_retrieval_module

pytestmark = pytest.mark.unit


def test_behavior_suites_include_context_retrieval(tmp_path: Path) -> None:
    result = behavior_module.run_behavior_evals(
        output_dir=tmp_path,
        suites=["context-retrieval"],
    )

    assert result.passes_validation is True
    assert result.selected_suites == ("context-retrieval",)
    assert result.selected_cases == 2
    assert "context-retrieval" in behavior_module.available_behavior_suites()

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["suites"] == [
        {
            "failed_cases": 0,
            "selected_cases": 2,
            "suite": "context-retrieval",
        }
    ]

    for case in payload["cases"]:
        assert case["suite"] == "context-retrieval"
        evidence = case["evidence"]
        assert evidence["retrieval_mode"] == "implement"
        assert evidence["retrieval_phase"] == "phase-1-cli-first"
        assert evidence["authoritative_source_basis"]["policy_registry_id"].startswith(
            "implement-mode-legacy-policy-v"
        )


def test_retrieval_behavior_cases_require_raises_on_false_condition() -> None:
    with pytest.raises(ValueError, match="boom"):
        behavior_cases_retrieval_module._require(False, "boom")


def test_patched_repo_root_restores_missing_task_command_repo_root(
    tmp_path: Path,
) -> None:
    cli_task_repo_module = SimpleNamespace(repo_root=lambda: Path("/cli-root"))
    task_commands_module = SimpleNamespace()
    workflow_task_repo_module = SimpleNamespace(repo_root=lambda: Path("/workflow-root"))

    with behavior_cases_retrieval_module._patched_repo_root(
        repo_root=tmp_path,
        cli_task_repo_module=cli_task_repo_module,
        task_commands_module=task_commands_module,
        workflow_task_repo_module=workflow_task_repo_module,
    ):
        assert cli_task_repo_module.repo_root() == tmp_path
        assert task_commands_module.repo_root() == tmp_path
        assert workflow_task_repo_module.repo_root() == tmp_path

    assert cli_task_repo_module.repo_root() == Path("/cli-root")
    assert not hasattr(task_commands_module, "repo_root")
    assert workflow_task_repo_module.repo_root() == Path("/workflow-root")
