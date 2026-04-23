"""Deterministic docstring policy for selected high-value Python surfaces."""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocstringPolicyTarget:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class DocstringPolicy:
    require_module_docstrings: bool
    require_public_class_docstrings: bool
    require_public_function_docstrings: bool
    require_public_method_docstrings: bool
    complex_member_min_lines: int
    targets: tuple[DocstringPolicyTarget, ...]


@dataclass(frozen=True, slots=True)
class DocstringIssue:
    kind: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class DocstringPolicyResult:
    issues: tuple[DocstringIssue, ...]

    @property
    def errors(self) -> tuple[DocstringIssue, ...]:
        return self.issues


def load_docstring_policy(policy_path: Path) -> DocstringPolicy:
    payload = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    policy_payload = payload["policy"]
    targets_payload = payload["targets"]
    return DocstringPolicy(
        require_module_docstrings=bool(policy_payload["require_module_docstrings"]),
        require_public_class_docstrings=bool(policy_payload["require_public_class_docstrings"]),
        require_public_function_docstrings=bool(
            policy_payload["require_public_function_docstrings"]
        ),
        require_public_method_docstrings=bool(policy_payload["require_public_method_docstrings"]),
        complex_member_min_lines=max(1, int(policy_payload["complex_member_min_lines"])),
        targets=tuple(
            DocstringPolicyTarget(
                path=str(entry["path"]),
                reason=str(entry["reason"]),
            )
            for entry in targets_payload
        ),
    )


def run_docstring_policy_check(*, repo_root: Path, policy_path: Path) -> DocstringPolicyResult:
    policy = load_docstring_policy(policy_path)
    issues: list[DocstringIssue] = []
    for target in policy.targets:
        issues.extend(_issues_for_target(repo_root=repo_root, policy=policy, target=target))
    return DocstringPolicyResult(issues=tuple(sorted(issues, key=_issue_sort_key)))


def render_docstring_policy_issues(result: DocstringPolicyResult) -> list[str]:
    return [f"ERROR [{issue.kind}] {issue.path}: {issue.message}" for issue in result.issues]


def _issues_for_target(
    *,
    repo_root: Path,
    policy: DocstringPolicy,
    target: DocstringPolicyTarget,
) -> list[DocstringIssue]:
    path = (repo_root / target.path).resolve()
    if not path.exists():
        return [
            DocstringIssue(
                "target-missing", target.path, "configured docstring-policy target does not exist"
            )
        ]

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=target.path)
    except SyntaxError as exc:
        return [
            DocstringIssue("parse-error", target.path, f"unable to parse Python source: {exc.msg}")
        ]

    issues: list[DocstringIssue] = []
    if policy.require_module_docstrings and not ast.get_docstring(tree):
        issues.append(
            DocstringIssue(
                "module-docstring",
                target.path,
                f"module docstring required for selected high-value path ({target.reason})",
            )
        )
    issues.extend(
        _body_issues(policy=policy, target=target, statements=tree.body, prefix=(), in_class=False)
    )
    return issues


def _body_issues(
    *,
    policy: DocstringPolicy,
    target: DocstringPolicyTarget,
    statements: list[ast.stmt],
    prefix: tuple[str, ...],
    in_class: bool,
) -> list[DocstringIssue]:
    issues: list[DocstringIssue] = []
    for statement in statements:
        if isinstance(statement, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if isinstance(statement, ast.ClassDef):
                class_name = _member_name(prefix, statement.name)
                if (
                    policy.require_public_class_docstrings
                    and _is_public_qualified_name(class_name)
                    and not ast.get_docstring(statement)
                ):
                    issues.append(
                        DocstringIssue(
                            "class-docstring",
                            target.path,
                            f"{class_name} is missing a docstring (public class)",
                        )
                    )
            elif issue := _member_issue(
                policy=policy,
                target=target,
                member_name=_member_name(prefix, statement.name),
                node=statement,
                is_method=in_class,
            ):
                issues.append(issue)
            issues.extend(
                _body_issues(
                    policy=policy,
                    target=target,
                    statements=statement.body,
                    prefix=(*prefix, statement.name),
                    in_class=isinstance(statement, ast.ClassDef),
                )
            )
            continue
        for nested_statements in _nested_statement_lists(statement):
            issues.extend(
                _body_issues(
                    policy=policy,
                    target=target,
                    statements=nested_statements,
                    prefix=prefix,
                    in_class=in_class,
                )
            )
    return issues


def _nested_statement_lists(node: ast.AST) -> tuple[list[ast.stmt], ...]:
    return tuple(
        value
        for _, value in ast.iter_fields(node)
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value)
    )


def _member_issue(
    *,
    policy: DocstringPolicy,
    target: DocstringPolicyTarget,
    member_name: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    is_method: bool,
) -> DocstringIssue | None:
    reasons = _member_requirement_reasons(
        policy=policy,
        member_name=member_name,
        node=node,
        is_method=is_method,
    )
    if reasons and not ast.get_docstring(node):
        return DocstringIssue(
            kind="member-docstring",
            path=target.path,
            message=(
                f"{member_name} is missing a docstring "
                f"({_describe_requirement_reasons(reasons, policy.complex_member_min_lines)})"
            ),
        )
    return None


def _member_requirement_reasons(
    *,
    policy: DocstringPolicy,
    member_name: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    is_method: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _is_public_qualified_name(member_name):
        if is_method and policy.require_public_method_docstrings:
            reasons.append("public-method")
        if not is_method and policy.require_public_function_docstrings:
            reasons.append("public-function")
    if _member_line_count(node) >= policy.complex_member_min_lines:
        reasons.append("complex-member")
    return tuple(reasons)


def _describe_requirement_reasons(reasons: tuple[str, ...], complex_member_min_lines: int) -> str:
    reason_labels = {
        "public-function": "public function on selected high-value path",
        "public-method": "public method on selected high-value path",
    }
    return ", ".join(
        reason_labels.get(reason, f"complex member >= {complex_member_min_lines} lines")
        for reason in reasons
    )


def _member_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    start_lineno = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    end_lineno = getattr(node, "end_lineno", node.lineno)
    return end_lineno - start_lineno + 1


def _member_name(prefix: tuple[str, ...], name: str) -> str:
    return ".".join((*prefix, name)) if prefix else name


def _is_public_qualified_name(name: str) -> bool:
    return all(not part.startswith("_") for part in name.split("."))


def _issue_sort_key(issue: DocstringIssue) -> tuple[str, str, str]:
    return (issue.path, issue.kind, issue.message)


__all__ = [
    "DocstringIssue",
    "DocstringPolicy",
    "DocstringPolicyResult",
    "DocstringPolicyTarget",
    "load_docstring_policy",
    "render_docstring_policy_issues",
    "run_docstring_policy_check",
]
