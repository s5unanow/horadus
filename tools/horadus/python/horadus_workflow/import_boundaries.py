from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_SRC_ALLOWED_LAYER_TARGETS: dict[str, frozenset[str]] = {
    "api": frozenset({"core", "processing", "storage"}),
    "core": frozenset({"storage"}),
    "eval": frozenset({"core", "processing", "storage"}),
    "ingestion": frozenset({"core", "processing", "storage"}),
    "processing": frozenset({"core", "storage"}),
    "storage": frozenset(),
    "workers": frozenset({"core", "ingestion", "processing", "storage"}),
}

_TOOLS_ALLOWED_GROUP_TARGETS: dict[str, frozenset[str]] = {
    "horadus_cli": frozenset({"horadus_workflow"}),
    "horadus_workflow": frozenset(),
    "horadus_app_cli_runtime": frozenset(),
}


@dataclass(frozen=True, slots=True)
class TrackedModule:
    name: str
    path: Path
    is_package: bool


@dataclass(frozen=True, slots=True)
class ImportEdge:
    importer: str
    imported: str
    path: Path
    line_number: int


@dataclass(frozen=True, slots=True)
class AllowedImportException:
    importer_prefix: str
    imported_prefix: str
    rationale: str

    def matches(self, importer: str, imported: str) -> bool:
        return _matches_module_pattern(importer, self.importer_prefix) and _matches_module_pattern(
            imported, self.imported_prefix
        )


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    kind: str
    message: str
    path: Path
    line_number: int | None = None


_SRC_ALLOWED_IMPORT_EXCEPTIONS: tuple[AllowedImportException, ...] = (
    AllowedImportException(
        importer_prefix="src.core.report_generator",
        imported_prefix="src.processing.",
        rationale="core reporting keeps using shared processing LLM adapters without a new wrapper",
    ),
    AllowedImportException(
        importer_prefix="src.core.retrospective_analyzer",
        imported_prefix="src.processing.",
        rationale="retrospective analysis shares the same processing LLM adapter surface",
    ),
    AllowedImportException(
        importer_prefix="src.processing.tier2_canary",
        imported_prefix="src.eval.benchmark",
        rationale="the canary reuses gold-set fixture loading from eval instead of duplicating it",
    ),
    AllowedImportException(
        importer_prefix="src.storage.database",
        imported_prefix="src.core.config",
        rationale="storage database bootstrap still reads runtime settings from core config",
    ),
)

_TOOLS_TO_SRC_ALLOWED_IMPORT_EXCEPTIONS: tuple[AllowedImportException, ...] = (
    AllowedImportException(
        importer_prefix="tools.horadus.python.horadus_app_cli_runtime",
        imported_prefix="src.core.",
        rationale="runtime bridge may call selected core app entry points",
    ),
    AllowedImportException(
        importer_prefix="tools.horadus.python.horadus_app_cli_runtime",
        imported_prefix="src.eval.",
        rationale="runtime bridge may run selected app-backed eval commands",
    ),
    AllowedImportException(
        importer_prefix="tools.horadus.python.horadus_app_cli_runtime",
        imported_prefix="src.processing.dry_run_pipeline",
        rationale="runtime bridge may run the deterministic pipeline dry-run surface",
    ),
    AllowedImportException(
        importer_prefix="tools.horadus.python.horadus_app_cli_runtime",
        imported_prefix="src.storage.database",
        rationale="runtime bridge may open app database sessions via the documented seam",
    ),
)


def analyze_repo_import_boundaries(repo_root: Path) -> tuple[BoundaryViolation, ...]:
    tracked_modules = _tracked_modules(repo_root)
    import_edges = _collect_import_edges(tracked_modules)
    violations = [
        *_dependency_direction_violations(import_edges),
        *_cycle_violations(tracked_modules, import_edges),
    ]
    return tuple(sorted(violations, key=_violation_sort_key))


def format_boundary_violations(violations: tuple[BoundaryViolation, ...]) -> list[str]:
    return [
        _format_violation(violation) for violation in sorted(violations, key=_violation_sort_key)
    ]


def _violation_sort_key(violation: BoundaryViolation) -> tuple[str, int, str]:
    return (violation.path.as_posix(), violation.line_number or 0, violation.message)


def _tracked_modules(repo_root: Path) -> dict[str, TrackedModule]:
    tracked: dict[str, TrackedModule] = {}
    for root in (repo_root / "src", repo_root / "tools" / "horadus" / "python"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(repo_root)
            if path.name == "__init__.py":
                module_name = ".".join(relative_path.parent.parts)
            else:
                module_name = ".".join(relative_path.with_suffix("").parts)
            tracked[module_name] = TrackedModule(
                name=module_name,
                path=path.resolve(),
                is_package=path.name == "__init__.py",
            )
    return tracked


def _collect_import_edges(tracked_modules: dict[str, TrackedModule]) -> tuple[ImportEdge, ...]:
    edges: list[ImportEdge] = []
    for tracked_module in tracked_modules.values():
        tree = ast.parse(
            tracked_module.path.read_text(encoding="utf-8"),
            filename=tracked_module.path.as_posix(),
        )
        visitor = _ImportEdgeCollector(
            current_module=tracked_module,
            tracked_modules=tracked_modules,
            edges=edges,
        )
        visitor.visit(tree)
    return tuple(edges)


class _ImportEdgeCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        current_module: TrackedModule,
        tracked_modules: dict[str, TrackedModule],
        edges: list[ImportEdge],
    ) -> None:
        self._current_module = current_module
        self._tracked_modules = tracked_modules
        self._edges = edges
        self._type_checking_depth = 0

    def visit_If(self, node: ast.If) -> None:
        is_type_checking_guard = _is_type_checking_test(node.test)
        if is_type_checking_guard:
            self._type_checking_depth += 1
        for child in node.body:
            self.visit(child)
        if is_type_checking_guard:
            self._type_checking_depth -= 1
        for child in node.orelse:
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        if self._type_checking_depth:
            return
        for alias in node.names:
            imported = _resolve_deepest_tracked_module(alias.name, self._tracked_modules)
            if imported is None or imported == self._current_module.name:
                continue
            self._edges.append(
                ImportEdge(
                    importer=self._current_module.name,
                    imported=imported,
                    path=self._current_module.path,
                    line_number=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._type_checking_depth:
            return
        for imported in _resolve_from_import_targets(
            current_module=self._current_module,
            node=node,
            tracked_modules=self._tracked_modules,
        ):
            if imported == self._current_module.name:
                continue
            self._edges.append(
                ImportEdge(
                    importer=self._current_module.name,
                    imported=imported,
                    path=self._current_module.path,
                    line_number=node.lineno,
                )
            )


def _is_type_checking_test(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
    )


def _resolve_from_import_targets(
    *,
    current_module: TrackedModule,
    node: ast.ImportFrom,
    tracked_modules: dict[str, TrackedModule],
) -> tuple[str, ...]:
    base_module = _resolve_import_from_base(current_module=current_module, node=node)
    if base_module is None:
        return ()
    resolved: list[str] = []
    if node.module == "__future__":
        return ()
    for alias in node.names:
        if alias.name == "*":
            imported = _resolve_deepest_tracked_module(base_module, tracked_modules)
            if imported is not None:
                resolved.append(imported)
            continue
        candidate = f"{base_module}.{alias.name}"
        imported = _resolve_deepest_tracked_module(candidate, tracked_modules)
        if imported is None:
            imported = _resolve_deepest_tracked_module(base_module, tracked_modules)
        if imported is not None:
            resolved.append(imported)
    return tuple(dict.fromkeys(resolved))


def _resolve_import_from_base(*, current_module: TrackedModule, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package_parts = current_module.name.split(".")
    if not current_module.is_package:
        package_parts = package_parts[:-1]
    ascent = node.level - 1
    if ascent > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - ascent]
    if node.module:
        base_parts.extend(node.module.split("."))
    if not base_parts:
        return None
    return ".".join(base_parts)


def _resolve_deepest_tracked_module(
    module_name: str,
    tracked_modules: dict[str, TrackedModule],
) -> str | None:
    parts = module_name.split(".")
    for index in range(len(parts), 0, -1):
        candidate = ".".join(parts[:index])
        if candidate in tracked_modules:
            return candidate
    return None


def _dependency_direction_violations(
    import_edges: tuple[ImportEdge, ...],
) -> tuple[BoundaryViolation, ...]:
    violations: list[BoundaryViolation] = []
    for edge in import_edges:
        importer_kind = _module_kind(edge.importer)
        imported_kind = _module_kind(edge.imported)
        if importer_kind == "src" and imported_kind == "src":
            violation = _src_violation(edge)
        elif importer_kind == "tools" and imported_kind == "tools":
            violation = _tools_violation(edge)
        elif importer_kind == "tools" and imported_kind == "src":
            violation = _tools_to_src_violation(edge)
        elif importer_kind == "src" and imported_kind == "tools":
            violation = BoundaryViolation(
                kind="src-imports-tools",
                message=(
                    f"{edge.importer} imports tooling module {edge.imported}; "
                    "application runtime code must not depend on repo workflow tooling"
                ),
                path=edge.path,
                line_number=edge.line_number,
            )
        else:
            violation = None
        if violation is not None:
            violations.append(violation)
    return tuple(violations)


def _src_violation(edge: ImportEdge) -> BoundaryViolation | None:
    importer_layer = _src_layer(edge.importer)
    imported_layer = _src_layer(edge.imported)
    if importer_layer is None or imported_layer is None or importer_layer == imported_layer:
        return None
    allowed_targets = _SRC_ALLOWED_LAYER_TARGETS.get(importer_layer, frozenset())
    if imported_layer in allowed_targets:
        return None
    if _matches_any_exception(edge, _SRC_ALLOWED_IMPORT_EXCEPTIONS):
        return None
    return BoundaryViolation(
        kind="forbidden-src-layer-edge",
        message=(
            f"{edge.importer} imports {edge.imported} "
            f"({importer_layer} -> {imported_layer}), which is outside the repo-owned "
            "dependency-direction contract"
        ),
        path=edge.path,
        line_number=edge.line_number,
    )


def _tools_violation(edge: ImportEdge) -> BoundaryViolation | None:
    importer_group = _tool_group(edge.importer)
    imported_group = _tool_group(edge.imported)
    if importer_group is None or imported_group is None or importer_group == imported_group:
        return None
    allowed_targets = _TOOLS_ALLOWED_GROUP_TARGETS.get(importer_group, frozenset())
    if imported_group in allowed_targets:
        return None
    return BoundaryViolation(
        kind="forbidden-tools-edge",
        message=(
            f"{edge.importer} imports {edge.imported} "
            f"({importer_group} -> {imported_group}), which bypasses the tooling package contract"
        ),
        path=edge.path,
        line_number=edge.line_number,
    )


def _tools_to_src_violation(edge: ImportEdge) -> BoundaryViolation | None:
    if _matches_any_exception(edge, _TOOLS_TO_SRC_ALLOWED_IMPORT_EXCEPTIONS):
        return None
    return BoundaryViolation(
        kind="forbidden-tools-to-src-edge",
        message=(
            f"{edge.importer} imports app module {edge.imported}; only the documented "
            "runtime bridge may cross from tooling into the app, and only through its "
            "allowlisted seams"
        ),
        path=edge.path,
        line_number=edge.line_number,
    )


def _matches_any_exception(
    edge: ImportEdge,
    exceptions: tuple[AllowedImportException, ...],
) -> bool:
    return any(exception.matches(edge.importer, edge.imported) for exception in exceptions)


def _matches_module_pattern(module_name: str, pattern: str) -> bool:
    if pattern.endswith("."):
        base_pattern = pattern[:-1]
        return module_name == base_pattern or module_name.startswith(f"{base_pattern}.")
    return module_name == pattern


def _cycle_violations(
    tracked_modules: dict[str, TrackedModule],
    import_edges: tuple[ImportEdge, ...],
) -> tuple[BoundaryViolation, ...]:
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in import_edges:
        graph[edge.importer].add(edge.imported)
    components = _strongly_connected_components(set(tracked_modules), graph)
    violations: list[BoundaryViolation] = []
    for component in components:
        if len(component) == 1:
            continue
        cycle_path = _cycle_path_for_component(component, graph)
        display_cycle = " -> ".join(cycle_path)
        tracked_module = tracked_modules[cycle_path[0]]
        violations.append(
            BoundaryViolation(
                kind="import-cycle",
                message=f"import cycle detected: {display_cycle}",
                path=tracked_module.path,
            )
        )
    return tuple(violations)


def _strongly_connected_components(
    modules: set[str],
    graph: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(module_name: str) -> None:
        nonlocal index
        indices[module_name] = index
        low_links[module_name] = index
        index += 1
        stack.append(module_name)
        on_stack.add(module_name)
        for imported in sorted(graph.get(module_name, ())):
            if imported not in indices:
                visit(imported)
                low_links[module_name] = min(low_links[module_name], low_links[imported])
            elif imported in on_stack:
                low_links[module_name] = min(low_links[module_name], indices[imported])
        if low_links[module_name] != indices[module_name]:
            return
        component: list[str] = []
        while True:
            imported = stack.pop()
            on_stack.remove(imported)
            component.append(imported)
            if imported == module_name:
                break
        components.append(tuple(sorted(component)))

    for module_name in sorted(modules):
        if module_name not in indices:
            visit(module_name)
    return tuple(sorted(components))


def _cycle_path_for_component(
    component: tuple[str, ...],
    graph: dict[str, set[str]],
) -> tuple[str, ...]:
    component_nodes = set(component)
    visited: set[str] = set()
    path: list[str] = []
    path_index: dict[str, int] = {}

    def visit(module_name: str) -> tuple[str, ...] | None:
        visited.add(module_name)
        path_index[module_name] = len(path)
        path.append(module_name)
        for imported in sorted(graph.get(module_name, ())):
            if imported not in component_nodes:
                continue
            if imported in path_index:
                cycle_start = path_index[imported]
                return (*path[cycle_start:], imported)
            if imported not in visited:
                cycle = visit(imported)
                if cycle is not None:
                    return cycle
        path.pop()
        path_index.pop(module_name)
        return None

    for module_name in sorted(component):
        if module_name in visited:
            continue
        cycle = visit(module_name)
        if cycle is not None:
            return cycle
    return (*component, component[0])


def _module_kind(module_name: str) -> str | None:
    if module_name.startswith("src."):
        return "src"
    if module_name.startswith("tools.horadus.python."):
        return "tools"
    return None


def _src_layer(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) < 2 or parts[0] != "src":
        return None
    return parts[1]


def _tool_group(module_name: str) -> str | None:
    parts = module_name.split(".")
    if parts[:3] != ["tools", "horadus", "python"] or len(parts) < 4:
        return None
    return parts[3]


def _format_violation(violation: BoundaryViolation) -> str:
    location = violation.path.as_posix()
    if violation.line_number is not None:
        location = f"{location}:{violation.line_number}"
    return f"{location}: {violation.message}"


__all__ = [
    "BoundaryViolation",
    "analyze_repo_import_boundaries",
    "format_boundary_violations",
]
