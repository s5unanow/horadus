from __future__ import annotations

import ast
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.app as cli_app_module
import tools.horadus.python.horadus_cli.ops_commands as v2_ops_module
import tools.horadus.python.horadus_cli.task_commands as v2_task_commands_module
import tools.horadus.python.horadus_cli.triage_commands as v2_triage_commands_module

pytestmark = pytest.mark.unit

_CLI_PACKAGE_ROOT = Path("tools/horadus/python/horadus_cli")


def test_app_router_uses_v2_for_every_command_family() -> None:
    assert cli_app_module.register_ops_commands is v2_ops_module.register_ops_commands
    assert cli_app_module.register_task_commands is v2_task_commands_module.register_task_commands
    assert (
        cli_app_module.register_triage_commands
        is v2_triage_commands_module.register_triage_commands
    )


def test_cli_compatibility_wrappers_are_removed_from_src() -> None:
    assert not Path("src/cli.py").exists()
    assert not Path("src/cli_runtime.py").exists()
    assert not Path("src/horadus_cli").exists()


def test_horadus_cli_package_limits_repo_external_imports_to_ops_adapters() -> None:
    package_root = _CLI_PACKAGE_ROOT

    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("src.")
            ):
                raise AssertionError(f"{path} imports non-CLI module {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("src."):
                        raise AssertionError(f"{path} imports non-CLI module {alias.name}")


def test_pyproject_points_horadus_entrypoint_to_tools() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'horadus = "tools.horadus.python.horadus_cli.app:main"' in pyproject
