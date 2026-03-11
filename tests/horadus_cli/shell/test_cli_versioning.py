from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

import src.horadus_cli.app as cli_app_module
import src.horadus_cli.legacy as legacy_module
import src.horadus_cli.task_commands as task_commands_module
import src.horadus_cli.triage_commands as triage_commands_module
import src.horadus_cli.v1.legacy as v1_legacy_module
import src.horadus_cli.v1.task_commands as v1_task_commands_module
import src.horadus_cli.v1.triage_commands as v1_triage_commands_module

pytestmark = pytest.mark.unit


def test_top_level_legacy_modules_alias_v1_modules() -> None:
    assert legacy_module.register_legacy_commands is v1_legacy_module.register_legacy_commands
    assert (
        task_commands_module.register_task_commands
        is v1_task_commands_module.register_task_commands
    )
    assert triage_commands_module.handle_collect is v1_triage_commands_module.handle_collect


@pytest.mark.parametrize(
    ("legacy_name", "v1_name"),
    [
        ("src.horadus_cli.result", "src.horadus_cli.v1.result"),
        ("src.horadus_cli.task_process", "src.horadus_cli.v1.task_process"),
        ("src.horadus_cli.task_repo", "src.horadus_cli.v1.task_repo"),
        ("src.horadus_cli.task_workflow_core", "src.horadus_cli.v1.task_workflow_core"),
    ],
)
def test_legacy_module_keys_alias_v1_modules(legacy_name: str, v1_name: str) -> None:
    legacy_alias = importlib.import_module(legacy_name)
    v1_module = importlib.import_module(v1_name)

    assert legacy_alias is v1_module


def test_app_router_uses_v1_registration_functions() -> None:
    assert cli_app_module.register_legacy_commands is v1_legacy_module.register_legacy_commands
    assert cli_app_module.register_task_commands is v1_task_commands_module.register_task_commands
    assert (
        cli_app_module.register_triage_commands
        is v1_triage_commands_module.register_triage_commands
    )


@pytest.mark.parametrize(
    ("wrapper_name", "v1_name", "attribute_name"),
    [
        ("task_finish", "task_finish", "handle_finish"),
        ("task_friction", "task_friction", "handle_record_friction"),
        ("task_ledgers", "task_ledgers", "handle_close_ledgers"),
        ("task_lifecycle", "task_lifecycle", "handle_lifecycle"),
        ("task_preflight", "task_preflight", "handle_preflight"),
        ("task_query", "task_query", "handle_show"),
        ("task_shared", "task_shared", "VALID_FRICTION_TYPES"),
        ("task_workflow", "task_workflow", "handle_safe_start"),
    ],
)
def test_task_wrappers_forward_v1_symbols(
    wrapper_name: str, v1_name: str, attribute_name: str
) -> None:
    wrapper_module = importlib.import_module(f"src.horadus_cli.{wrapper_name}")
    v1_module = importlib.import_module(f"src.horadus_cli.v1.{v1_name}")

    assert getattr(wrapper_module, attribute_name) is getattr(v1_module, attribute_name)


@pytest.mark.parametrize(
    "wrapper_name",
    ["result", "task_process", "task_repo", "task_workflow_core"],
)
def test_cached_wrapper_files_execute_directly(wrapper_name: str) -> None:
    wrapper_path = Path("src/horadus_cli") / f"{wrapper_name}.py"
    module_name = f"tests._versioning_exec_{wrapper_name}"
    spec = importlib.util.spec_from_file_location(module_name, wrapper_path)

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert module.__file__ is not None
