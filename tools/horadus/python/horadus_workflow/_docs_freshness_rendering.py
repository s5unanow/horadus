from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._docs_freshness_models import DocsFreshnessResult


def render_docs_freshness_issues(result: DocsFreshnessResult) -> tuple[str, ...]:
    lines: list[str] = []
    if result.warnings:
        lines.append("Docs freshness warnings:")
        for issue in result.warnings:
            path_fragment = f" ({issue.path})" if issue.path else ""
            lines.append(f"- [{issue.rule_id}] {issue.message}{path_fragment}")
    if result.errors:
        lines.append("Docs freshness errors:")
        for issue in result.errors:
            path_fragment = f" ({issue.path})" if issue.path else ""
            lines.append(f"- [{issue.rule_id}] {issue.message}{path_fragment}")
    return tuple(lines)
