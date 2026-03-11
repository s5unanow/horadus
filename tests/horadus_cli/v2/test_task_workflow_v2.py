from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.horadus_cli.v1.task_commands as v1_task_commands_module
import src.horadus_cli.v1.task_query as v1_task_query_module
import src.horadus_cli.v1.task_repo as v1_task_repo_module
import src.horadus_cli.v1.task_workflow_core as v1_task_workflow_core_module
import src.horadus_cli.v2.task_commands as v2_task_commands_module
import src.horadus_cli.v2.task_query as v2_task_query_module
import src.horadus_cli.v2.task_repo as v2_task_repo_module
import src.horadus_cli.v2.task_workflow_core as v2_task_workflow_core_module
from src.horadus_cli.v2.result import CommandResult, emit_result
from tests.horadus_cli.v1.task_repo_fixtures import seed_task_repo_layout

pytestmark = pytest.mark.unit


def _patch_repo_roots(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(v1_task_repo_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(v1_task_workflow_core_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(v2_task_repo_module, "repo_root", lambda: repo_root)
    monkeypatch.setattr(v2_task_workflow_core_module, "repo_root", lambda: repo_root)


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


def test_v2_task_parser_matches_v1_shape() -> None:
    assert _tasks_subcommand_names(v2_task_commands_module) == _tasks_subcommand_names(
        v1_task_commands_module
    )


@pytest.mark.parametrize(
    ("handler_name", "args"),
    [
        ("handle_list_active", SimpleNamespace()),
        ("handle_show", SimpleNamespace(task_id="TASK-301", include_archive=False)),
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
        ("handle_context_pack", SimpleNamespace(task_id="TASK-301", include_archive=False)),
    ],
)
def test_v2_query_handlers_match_v1(
    synthetic_task_repo_v2: Path, handler_name: str, args: SimpleNamespace
) -> None:
    v1_result = getattr(v1_task_query_module, handler_name)(args)
    v2_result = getattr(v2_task_query_module, handler_name)(args)
    assert v2_result.exit_code == v1_result.exit_code
    assert v2_result.data == v1_result.data
    assert v2_result.lines == v1_result.lines


def test_v2_runtime_does_not_import_v1_modules() -> None:
    v2_root = Path("src/horadus_cli/v2")
    for path in sorted(v2_root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "src.horadus_cli.v1" not in text, path.name


def test_v2_emit_result_includes_lines_in_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = emit_result(
        CommandResult(exit_code=0, data={"task": "TASK-299"}, lines=["line-one"]),
        "json",
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lines"] == ["line-one"]
