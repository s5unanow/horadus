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
import src.horadus_cli.v1.triage_commands as v1_triage_commands_module
import src.horadus_cli.v2.task_commands as v2_task_commands_module
import src.horadus_cli.v2.task_finish as v2_task_finish_module
import src.horadus_cli.v2.task_friction as v2_task_friction_module
import src.horadus_cli.v2.task_ledgers as v2_task_ledgers_module
import src.horadus_cli.v2.task_lifecycle as v2_task_lifecycle_module
import src.horadus_cli.v2.task_preflight as v2_task_preflight_module
import src.horadus_cli.v2.task_query as v2_task_query_module
import src.horadus_cli.v2.task_shared as v2_task_shared_module
import src.horadus_cli.v2.task_workflow as v2_task_workflow_module

pytestmark = pytest.mark.unit


def test_top_level_router_modules_use_v2_for_task_workflow() -> None:
    assert legacy_module.register_legacy_commands is v1_legacy_module.register_legacy_commands
    assert (
        task_commands_module.register_task_commands
        is v2_task_commands_module.register_task_commands
    )
    assert triage_commands_module.handle_collect is v1_triage_commands_module.handle_collect


@pytest.mark.parametrize(
    ("module_name", "target_name"),
    [
        ("src.horadus_cli.result", "src.horadus_cli.v1.result"),
        ("src.horadus_cli.task_process", "src.horadus_cli.v2.task_process"),
        ("src.horadus_cli.task_repo", "src.horadus_cli.v2.task_repo"),
        ("src.horadus_cli.task_workflow_core", "src.horadus_cli.v2.task_workflow_core"),
    ],
)
def test_top_level_module_keys_alias_expected_versions(module_name: str, target_name: str) -> None:
    assert importlib.import_module(module_name) is importlib.import_module(target_name)


def test_app_router_uses_v1_for_legacy_and_v2_for_tasks() -> None:
    assert cli_app_module.register_legacy_commands is v1_legacy_module.register_legacy_commands
    assert cli_app_module.register_task_commands is v2_task_commands_module.register_task_commands
    assert (
        cli_app_module.register_triage_commands
        is v1_triage_commands_module.register_triage_commands
    )


@pytest.mark.parametrize(
    ("wrapper_name", "target_module", "attribute_name"),
    [
        ("task_finish", v2_task_finish_module, "handle_finish"),
        ("task_friction", v2_task_friction_module, "handle_record_friction"),
        ("task_ledgers", v2_task_ledgers_module, "handle_close_ledgers"),
        ("task_lifecycle", v2_task_lifecycle_module, "handle_lifecycle"),
        ("task_preflight", v2_task_preflight_module, "handle_preflight"),
        ("task_query", v2_task_query_module, "handle_show"),
        ("task_shared", v2_task_shared_module, "VALID_FRICTION_TYPES"),
        ("task_workflow", v2_task_workflow_module, "handle_safe_start"),
    ],
)
def test_task_wrappers_forward_v2_symbols(
    wrapper_name: str, target_module: object, attribute_name: str
) -> None:
    wrapper_module = importlib.import_module(f"src.horadus_cli.{wrapper_name}")
    assert getattr(wrapper_module, attribute_name) is getattr(target_module, attribute_name)


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
