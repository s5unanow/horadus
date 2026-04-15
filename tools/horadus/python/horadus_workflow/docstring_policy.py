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
                kind="target-missing",
                path=target.path,
                message="configured docstring-policy target does not exist",
            )
        ]

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=target.path)
    except SyntaxError as exc:
        return [
            DocstringIssue(
                kind="parse-error",
                path=target.path,
                message=f"unable to parse Python source: {exc.msg}",
            )
        ]

    issues: list[DocstringIssue] = []
    if policy.require_module_docstrings and not ast.get_docstring(tree):
        issues.append(
            DocstringIssue(
                kind="module-docstring",
                path=target.path,
                message=(
                    f"module docstring required for selected high-value path ({target.reason})"
                ),
            )
        )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            issues.extend(_class_issues(policy=policy, target=target, node=node, prefix=()))
            continue
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            issue = _member_issue(
                policy=policy,
                target=target,
                member_name=node.name,
                node=node,
                is_method=False,
            )
            if issue is not None:
                issues.append(issue)
    return issues


def _class_issues(
    *,
    policy: DocstringPolicy,
    target: DocstringPolicyTarget,
    node: ast.ClassDef,
    prefix: tuple[str, ...],
) -> list[DocstringIssue]:
    class_name = _member_name(prefix, node.name)
    issues: list[DocstringIssue] = []
    if (
        policy.require_public_class_docstrings
        and _is_public_qualified_name(class_name)
        and not ast.get_docstring(node)
    ):
        issues.append(
            DocstringIssue(
                kind="class-docstring",
                path=target.path,
                message=f"{class_name} is missing a docstring (public class)",
            )
        )

    for child in node.body:
        if isinstance(child, ast.ClassDef):
            issues.extend(
                _class_issues(policy=policy, target=target, node=child, prefix=(*prefix, node.name))
            )
            continue
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            issue = _member_issue(
                policy=policy,
                target=target,
                member_name=_member_name((*prefix, node.name), child.name),
                node=child,
                is_method=True,
            )
            if issue is not None:
                issues.append(issue)
    return issues


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
    if not reasons or ast.get_docstring(node):
        return None
    return DocstringIssue(
        kind="member-docstring",
        path=target.path,
        message=(
            f"{member_name} is missing a docstring "
            f"({_describe_requirement_reasons(reasons, policy.complex_member_min_lines)})"
        ),
    )


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
    labels: list[str] = []
    for reason in reasons:
        if reason == "public-function":
            labels.append("public function on selected high-value path")
            continue
        if reason == "public-method":
            labels.append("public method on selected high-value path")
            continue
        labels.append(f"complex member >= {complex_member_min_lines} lines")
    return ", ".join(labels)


def _member_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    start_lineno = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    end_lineno = getattr(node, "end_lineno", node.lineno)
    return end_lineno - start_lineno + 1


def _member_name(prefix: tuple[str, ...], name: str) -> str:
    return ".".join((*prefix, name)) if prefix else name


def _is_public_name(name: str) -> bool:
    return not name.startswith("_")


def _is_public_qualified_name(name: str) -> bool:
    return all(_is_public_name(part) for part in name.split("."))


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
