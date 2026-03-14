from __future__ import annotations

import ast
import fnmatch
import subprocess  # nosec B404
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CodeShapeBudgets:
    production_module_lines: int
    test_module_lines: int
    production_function_lines: int
    test_function_lines: int


@dataclass(frozen=True, slots=True)
class LegacyFilePolicy:
    path: str
    max_lines: int | None
    member_max_lines: dict[str, int]


@dataclass(frozen=True, slots=True)
class CodeShapePolicy:
    budgets: CodeShapeBudgets
    include_roots: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    legacy_files: dict[str, LegacyFilePolicy]


@dataclass(frozen=True, slots=True)
class FileMeasurement:
    path: str
    module_lines: int
    member_lines: dict[str, int]
    is_test: bool


@dataclass(frozen=True, slots=True)
class CodeShapeIssue:
    kind: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class CodeShapeResult:
    issues: tuple[CodeShapeIssue, ...]

    @property
    def errors(self) -> tuple[CodeShapeIssue, ...]:
        return self.issues


def load_code_shape_policy(policy_path: Path) -> CodeShapePolicy:
    payload = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    budgets_payload = payload["budgets"]
    paths_payload = payload["paths"]

    legacy_files: dict[str, LegacyFilePolicy] = {}
    for entry in payload.get("legacy_files", []):
        path = str(entry["path"])
        legacy_files[path] = LegacyFilePolicy(
            path=path,
            max_lines=entry.get("max_lines"),
            member_max_lines={
                str(name): int(value)
                for name, value in (entry.get("member_max_lines") or {}).items()
            },
        )

    return CodeShapePolicy(
        budgets=CodeShapeBudgets(
            production_module_lines=int(budgets_payload["production_module_lines"]),
            test_module_lines=int(budgets_payload["test_module_lines"]),
            production_function_lines=int(budgets_payload["production_function_lines"]),
            test_function_lines=int(budgets_payload["test_function_lines"]),
        ),
        include_roots=tuple(str(item) for item in paths_payload["include_roots"]),
        exclude_globs=tuple(str(item) for item in paths_payload.get("exclude_globs", [])),
        legacy_files=legacy_files,
    )


def _matches_any_glob(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _iter_python_paths(repo_root: Path, policy: CodeShapePolicy) -> list[Path]:
    completed = subprocess.run(  # nosec
        ["git", "-C", str(repo_root), "ls-files", "--", *policy.include_roots],
        check=True,
        capture_output=True,
        text=True,
    )

    paths: list[Path] = []
    for line in completed.stdout.splitlines():
        relative = line.strip()
        if not relative or not relative.endswith(".py"):
            continue
        if _matches_any_glob(relative, policy.exclude_globs):
            continue
        path = repo_root / relative
        if "__pycache__" in path.parts or not path.exists():
            continue
        paths.append(path)
    return sorted(paths)


def _member_name(prefix: tuple[str, ...], name: str) -> str:
    return ".".join((*prefix, name)) if prefix else name


def _collect_member_lines(tree: ast.AST) -> dict[str, int]:
    member_lines: dict[str, int] = {}

    def visit(node: ast.AST, prefix: tuple[str, ...]) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                visit(child, (*prefix, child.name))
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                start_lineno = (
                    child.decorator_list[0].lineno if child.decorator_list else child.lineno
                )
                end_lineno = getattr(child, "end_lineno", child.lineno)
                member_name = _member_name(prefix, child.name)
                member_lines[member_name] = max(
                    member_lines.get(member_name, 0),
                    end_lineno - start_lineno + 1,
                )

    visit(tree, ())
    return member_lines


def measure_python_file(repo_root: Path, path: Path) -> FileMeasurement:
    relative_path = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=relative_path)
    return FileMeasurement(
        path=relative_path,
        module_lines=len(text.splitlines()),
        member_lines=_collect_member_lines(tree),
        is_test=relative_path.startswith("tests/"),
    )


def _module_budget(measurement: FileMeasurement, budgets: CodeShapeBudgets) -> int:
    return budgets.test_module_lines if measurement.is_test else budgets.production_module_lines


def _member_budget(measurement: FileMeasurement, budgets: CodeShapeBudgets) -> int:
    return budgets.test_function_lines if measurement.is_test else budgets.production_function_lines


def _module_issues(
    *,
    measurement: FileMeasurement,
    budgets: CodeShapeBudgets,
    legacy_policy: LegacyFilePolicy | None,
) -> list[CodeShapeIssue]:
    issues: list[CodeShapeIssue] = []
    module_budget = _module_budget(measurement, budgets)
    module_limit = (
        legacy_policy.max_lines if legacy_policy and legacy_policy.max_lines else module_budget
    )
    if measurement.module_lines > module_limit:
        budget_label = (
            "allowlisted maximum" if legacy_policy and legacy_policy.max_lines else "budget"
        )
        issues.append(
            CodeShapeIssue(
                kind="module-lines",
                path=measurement.path,
                message=f"module has {measurement.module_lines} lines; {budget_label} is {module_limit}",
            )
        )
    if (
        legacy_policy
        and legacy_policy.max_lines is not None
        and measurement.module_lines <= module_budget
    ):
        issues.append(
            CodeShapeIssue(
                kind="stale-module-override",
                path=measurement.path,
                message=(
                    f"module override is stale: file now fits the default module budget "
                    f"({measurement.module_lines} <= {module_budget})"
                ),
            )
        )
    return issues


def _member_issues(
    *,
    measurement: FileMeasurement,
    budgets: CodeShapeBudgets,
    legacy_policy: LegacyFilePolicy | None,
) -> list[CodeShapeIssue]:
    issues: list[CodeShapeIssue] = []
    member_budget = _member_budget(measurement, budgets)
    for member_name, member_lines in sorted(measurement.member_lines.items()):
        override_limit = legacy_policy.member_max_lines.get(member_name) if legacy_policy else None
        member_limit = override_limit if override_limit is not None else member_budget
        if member_lines > member_limit:
            budget_label = "allowlisted maximum" if override_limit is not None else "budget"
            issues.append(
                CodeShapeIssue(
                    kind="member-lines",
                    path=measurement.path,
                    message=f"{member_name} spans {member_lines} lines; {budget_label} is {member_limit}",
                )
            )
    return issues


def _stale_member_override_issues(
    *,
    measurement: FileMeasurement,
    budgets: CodeShapeBudgets,
    legacy_policy: LegacyFilePolicy | None,
) -> list[CodeShapeIssue]:
    if legacy_policy is None:
        return []

    issues: list[CodeShapeIssue] = []
    member_budget = _member_budget(measurement, budgets)
    for member_name, _override_limit in sorted(legacy_policy.member_max_lines.items()):
        actual_lines = measurement.member_lines.get(member_name)
        if actual_lines is None:
            issues.append(
                CodeShapeIssue(
                    kind="stale-member-override",
                    path=measurement.path,
                    message=f"member override is stale: {member_name} no longer exists",
                )
            )
            continue
        if actual_lines <= member_budget:
            issues.append(
                CodeShapeIssue(
                    kind="stale-member-override",
                    path=measurement.path,
                    message=(
                        f"member override is stale: {member_name} now fits the default member "
                        f"budget ({actual_lines} <= {member_budget})"
                    ),
                )
            )
            continue
    return issues


def _issues_for_measurement(
    *,
    measurement: FileMeasurement,
    budgets: CodeShapeBudgets,
    legacy_policy: LegacyFilePolicy | None,
) -> list[CodeShapeIssue]:
    return [
        *_module_issues(measurement=measurement, budgets=budgets, legacy_policy=legacy_policy),
        *_member_issues(measurement=measurement, budgets=budgets, legacy_policy=legacy_policy),
        *_stale_member_override_issues(
            measurement=measurement,
            budgets=budgets,
            legacy_policy=legacy_policy,
        ),
    ]


def run_code_shape_check(*, repo_root: Path, policy_path: Path) -> CodeShapeResult:
    policy = load_code_shape_policy(policy_path)
    issues: list[CodeShapeIssue] = []
    seen_paths: set[str] = set()

    for path in _iter_python_paths(repo_root, policy):
        measurement = measure_python_file(repo_root, path)
        seen_paths.add(measurement.path)
        legacy_policy = policy.legacy_files.get(measurement.path)
        issues.extend(
            _issues_for_measurement(
                measurement=measurement,
                budgets=policy.budgets,
                legacy_policy=legacy_policy,
            )
        )

    for legacy_path, _legacy_policy in sorted(policy.legacy_files.items()):
        if legacy_path in seen_paths:
            continue
        issues.append(
            CodeShapeIssue(
                kind="stale-file-override",
                path=legacy_path,
                message="legacy override is stale: file no longer exists under the tracked roots",
            )
        )

    return CodeShapeResult(issues=tuple(sorted(issues, key=lambda issue: (issue.path, issue.kind))))


def render_code_shape_issues(result: CodeShapeResult) -> tuple[str, ...]:
    if not result.issues:
        return ()
    return tuple(f"ERROR [{issue.kind}] {issue.path}: {issue.message}" for issue in result.issues)


__all__ = [
    "CodeShapeBudgets",
    "CodeShapeIssue",
    "CodeShapePolicy",
    "CodeShapeResult",
    "FileMeasurement",
    "LegacyFilePolicy",
    "load_code_shape_policy",
    "measure_python_file",
    "render_code_shape_issues",
    "run_code_shape_check",
]
