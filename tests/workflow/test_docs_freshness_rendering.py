from __future__ import annotations

import pytest

from tools.horadus.python.horadus_workflow.docs_freshness import (
    DocsFreshnessIssue,
    DocsFreshnessResult,
    render_docs_freshness_issues,
)

pytestmark = pytest.mark.unit


def test_render_docs_freshness_issues_formats_warning_and_error_blocks() -> None:
    result = DocsFreshnessResult(
        warnings=(
            DocsFreshnessIssue(
                level="warning",
                rule_id="warning-rule",
                message="warning body",
                path="docs/example.md",
            ),
        ),
        errors=(
            DocsFreshnessIssue(
                level="error",
                rule_id="error-rule",
                message="error body",
            ),
        ),
    )

    assert render_docs_freshness_issues(result) == (
        "Docs freshness warnings:",
        "- [warning-rule] warning body (docs/example.md)",
        "Docs freshness errors:",
        "- [error-rule] error body",
    )


def test_render_docs_freshness_issues_returns_empty_tuple_for_clean_result() -> None:
    assert render_docs_freshness_issues(DocsFreshnessResult(errors=(), warnings=())) == ()
