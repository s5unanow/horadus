from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_workflow_package_has_no_cli_or_app_imports() -> None:
    package_root = Path("tools/horadus/python/horadus_workflow")

    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("src.")
            ):
                raise AssertionError(f"{path} imports disallowed module {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("src."):
                        raise AssertionError(f"{path} imports disallowed module {alias.name}")
