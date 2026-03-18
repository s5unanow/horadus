from __future__ import annotations

import ast
from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.import_boundaries as import_boundaries_module
from tools.horadus.python.horadus_workflow.import_boundaries import (
    analyze_repo_import_boundaries,
    format_boundary_violations,
)

pytestmark = pytest.mark.unit


def test_repo_import_boundary_contract_passes_for_live_repo() -> None:
    violations = analyze_repo_import_boundaries(Path.cwd())

    assert violations == ()


def test_import_boundary_analyzer_accepts_allowed_runtime_bridge_fixture(
    tmp_path: Path,
) -> None:
    _write_module(tmp_path, "src.core.config", "settings = object()\n")
    _write_module(tmp_path, "src.storage.database", "engine = object()\n")
    _write_module(
        tmp_path,
        "src.api.routes.health",
        "from src.core.config import settings\nfrom src.storage.database import engine\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_workflow.result",
        "class CommandResult: ...\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_cli.result",
        "from tools.horadus.python.horadus_workflow.result import CommandResult\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_app_cli_runtime",
        "from src.core.config import settings\nfrom src.storage.database import engine\n",
    )

    violations = analyze_repo_import_boundaries(tmp_path)

    assert violations == ()


def test_import_boundary_analyzer_rejects_forbidden_src_layer_edge(tmp_path: Path) -> None:
    _write_module(tmp_path, "src.processing.pipeline", "def run() -> None:\n    return None\n")
    _write_module(
        tmp_path,
        "src.storage.models",
        "from src.processing.pipeline import run\n",
    )

    violations = analyze_repo_import_boundaries(tmp_path)

    assert any(violation.kind == "forbidden-src-layer-edge" for violation in violations)
    assert "storage -> processing" in "\n".join(format_boundary_violations(violations))


def test_import_boundary_analyzer_rejects_tooling_import_leak(tmp_path: Path) -> None:
    _write_module(tmp_path, "src.core.config", "settings = object()\n")
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_cli.bad",
        "from src.core.config import settings\n",
    )

    violations = analyze_repo_import_boundaries(tmp_path)

    assert any(violation.kind == "forbidden-tools-to-src-edge" for violation in violations)
    assert "only the documented runtime bridge may cross" in "\n".join(
        format_boundary_violations(violations)
    )


def test_import_boundary_analyzer_rejects_cycles(tmp_path: Path) -> None:
    _write_module(tmp_path, "src.core.a", "from src.core import b\n")
    _write_module(tmp_path, "src.core.b", "from src.core import a\n")

    violations = analyze_repo_import_boundaries(tmp_path)

    assert any(violation.kind == "import-cycle" for violation in violations)
    assert "src.core.a -> src.core.b -> src.core.a" in "\n".join(
        format_boundary_violations(violations)
    )


def test_import_boundary_analyzer_rejects_src_to_tools_and_cross_tool_group_edges(
    tmp_path: Path,
) -> None:
    _write_module(tmp_path, "src.core.config", "settings = object()\n")
    _write_module(
        tmp_path,
        "src.core.bad",
        "from tools.horadus.python.horadus_workflow.result import CommandResult\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_workflow.result",
        "class CommandResult: ...\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_cli.result",
        "class CLIResult: ...\n",
    )
    _write_module(
        tmp_path,
        "tools.horadus.python.horadus_workflow.bad",
        "from tools.horadus.python.horadus_cli.result import CLIResult\n",
    )

    violations = analyze_repo_import_boundaries(tmp_path)
    violation_kinds = {violation.kind for violation in violations}

    assert "src-imports-tools" in violation_kinds
    assert "forbidden-tools-edge" in violation_kinds


def test_import_boundary_helper_edges_cover_resolution_and_skip_paths(tmp_path: Path) -> None:
    _write_module(tmp_path, "src.core.config", "settings = object()\n")
    _write_module(
        tmp_path,
        "src.core.sample",
        (
            "from __future__ import annotations\n"
            "from src.core import sample\n"
            "from .config import settings\n"
            "if TYPE_CHECKING:\n"
            "    import src.core.config\n"
            "import typing\n"
            "if typing.TYPE_CHECKING:\n"
            "    from src.core import config\n"
        ),
    )
    ignored_path = tmp_path / "src" / "core" / "__pycache__" / "ignored.py"
    ignored_path.parent.mkdir(parents=True, exist_ok=True)
    ignored_path.write_text("import src.core.config\n", encoding="utf-8")

    tracked_modules = import_boundaries_module._tracked_modules(tmp_path)
    sample_module = tracked_modules["src.core.sample"]
    import_edges = import_boundaries_module._collect_import_edges(tracked_modules)

    assert all("__pycache__" not in module.path.parts for module in tracked_modules.values())
    assert {(edge.importer, edge.imported) for edge in import_edges} == {
        ("src.core.sample", "src.core.config")
    }

    star_node = ast.parse("from src.core import *").body[0]
    assert isinstance(star_node, ast.ImportFrom)
    assert import_boundaries_module._resolve_from_import_targets(
        current_module=sample_module,
        node=star_node,
        tracked_modules=tracked_modules,
    ) == ("src.core",)

    too_high_relative_node = ast.parse("from ....missing import nope").body[0]
    assert isinstance(too_high_relative_node, ast.ImportFrom)
    assert (
        import_boundaries_module._resolve_import_from_base(
            current_module=sample_module,
            node=too_high_relative_node,
        )
        is None
    )
    assert (
        import_boundaries_module._resolve_from_import_targets(
            current_module=sample_module,
            node=too_high_relative_node,
            tracked_modules=tracked_modules,
        )
        == ()
    )
    missing_star_node = ast.parse("from external.unknown import *").body[0]
    assert isinstance(missing_star_node, ast.ImportFrom)
    assert (
        import_boundaries_module._resolve_from_import_targets(
            current_module=sample_module,
            node=missing_star_node,
            tracked_modules=tracked_modules,
        )
        == ()
    )

    root_package = import_boundaries_module.TrackedModule(
        name="src",
        path=tmp_path / "src" / "__init__.py",
        is_package=True,
    )
    empty_base_node = ast.parse("from .. import nope").body[0]
    assert isinstance(empty_base_node, ast.ImportFrom)
    assert (
        import_boundaries_module._resolve_import_from_base(
            current_module=root_package,
            node=empty_base_node,
        )
        is None
    )
    assert import_boundaries_module._module_kind("external.module") is None
    assert import_boundaries_module._src_layer("external.module") is None
    assert import_boundaries_module._tool_group("external.module") is None
    assert (
        import_boundaries_module._dependency_direction_violations(
            (
                import_boundaries_module.ImportEdge(
                    importer="external.module",
                    imported="another.module",
                    path=tmp_path / "external.py",
                    line_number=1,
                ),
            )
        )
        == ()
    )


def _write_module(repo_root: Path, module_name: str, content: str) -> None:
    path = repo_root / Path(*module_name.split("."))
    file_path = path.with_suffix(".py")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _touch_init_packages(repo_root, file_path.parent)
    file_path.write_text(content, encoding="utf-8")


def _touch_init_packages(repo_root: Path, package_dir: Path) -> None:
    current = package_dir
    while current != repo_root.parent and current != repo_root:
        init_path = current / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")
        current = current.parent
