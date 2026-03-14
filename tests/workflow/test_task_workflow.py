from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.horadus.python.horadus_cli.task_commands as task_commands_module
import tools.horadus.python.horadus_cli.task_query as task_query_module
import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_workflow_core_module
import tools.horadus.python.horadus_workflow.task_workflow_policy as task_workflow_policy_module
from tests.horadus_cli.v2.task_repo_fixtures import seed_task_repo_layout
from tools.horadus.python.horadus_cli.result import CommandResult, emit_result

pytestmark = pytest.mark.unit

EXPECTED_TASK_SUBCOMMANDS = sorted(
    [
        "close-ledgers",
        "context-pack",
        "eligibility",
        "finish",
        "lifecycle",
        "list-active",
        "local-gate",
        "preflight",
        "record-friction",
        "safe-start",
        "search",
        "show",
        "start",
        "summarize-friction",
    ]
)


def _patch_repo_roots(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(task_repo_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(task_workflow_core_module, "repo_root", lambda: repo_root)


@pytest.fixture
def synthetic_task_repo_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = seed_task_repo_layout(tmp_path)
    _patch_repo_roots(monkeypatch, repo_root)
    return repo_root


def _tasks_subcommand_names(register_module: object) -> list[str]:
    parser = argparse.ArgumentParser(prog="horadus")
    subparsers = parser.add_subparsers(dest="command")
    register_module.register_task_commands(subparsers)
    tasks_parser = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ).choices["tasks"]
    tasks_action = next(
        action for action in tasks_parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return sorted(tasks_action.choices)


def test_task_parser_matches_expected_shape() -> None:
    assert _tasks_subcommand_names(task_commands_module) == EXPECTED_TASK_SUBCOMMANDS


@pytest.mark.parametrize(
    ("handler_name", "args"),
    [
        ("handle_list_active", SimpleNamespace()),
        ("handle_show", SimpleNamespace(task_id="TASK-901", include_archive=False)),
        (
            "handle_search",
            SimpleNamespace(
                query=["fixture"],
                status="all",
                limit=None,
                include_raw=False,
                include_archive=False,
            ),
        ),
        ("handle_context_pack", SimpleNamespace(task_id="TASK-901", include_archive=False)),
    ],
)
def test_task_query_handlers_return_expected_payload(
    synthetic_task_repo_v2: Path, handler_name: str, args: SimpleNamespace
) -> None:
    _ = synthetic_task_repo_v2
    result = getattr(task_query_module, handler_name)(args)
    assert result.exit_code == 0
    assert result.data is not None


def test_cli_sources_live_only_under_tools() -> None:
    runtime_paths = [
        Path("tools/horadus/python/horadus_cli/app.py"),
        *sorted(Path("tools/horadus/python/horadus_cli").glob("*.py")),
    ]
    for path in runtime_paths:
        text = path.read_text(encoding="utf-8")
        assert "src.horadus_cli" not in text, path.name

    assert not Path("src/cli.py").exists()
    assert not Path("src/cli_runtime.py").exists()
    assert not Path("src/horadus_cli").exists()


def test_v2_emit_result_includes_lines_in_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = emit_result(
        CommandResult(exit_code=0, data={"task": "TASK-901"}, lines=["line-one"]),
        "json",
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lines"] == ["line-one"]


def test_task_workflow_policy_helpers_cover_rendered_commands_and_guidance() -> None:
    first_command = task_workflow_policy_module.CANONICAL_TASK_WORKFLOW_COMMANDS[0]

    assert first_command.render("TASK-999") == "uv run --no-sync horadus tasks preflight"
    assert "AGENTS.md" not in task_workflow_policy_module.WORKFLOW_REFERENCE_PATHS
    assert task_workflow_policy_module.canonical_task_workflow_command_templates()[0] == (
        "uv run --no-sync horadus tasks preflight"
    )
    assert task_workflow_policy_module.canonical_task_workflow_commands_for_task("TASK-999")[
        -1
    ] == ("uv run --no-sync horadus tasks finish TASK-999")
    assert task_workflow_policy_module.completion_guidance_statements()
    assert task_workflow_policy_module.dependency_aware_guidance_statements()
    assert task_workflow_policy_module.fallback_guidance_statements()
    assert task_workflow_policy_module.workflow_policy_guardrail_statements()
