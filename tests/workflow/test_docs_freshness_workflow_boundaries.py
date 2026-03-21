from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.workflow.test_docs_freshness import _seed_repo_layout
from tools.horadus.python.horadus_workflow.docs_freshness import run_docs_freshness_check
from tools.horadus.python.horadus_workflow.repo_workflow import (
    completion_guidance_statements,
    dependency_aware_guidance_statements,
    fallback_guidance_statements,
    workflow_policy_guardrail_statements,
)

pytestmark = pytest.mark.unit


def test_docs_freshness_does_not_require_command_index_in_agents(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "AGENTS.md").write_text(
        "\n".join(
            [
                "## Canonical Source-of-Truth Hierarchy",
                "",
                "## Completion Policy",
                "\n".join(completion_guidance_statements()),
                "",
                "## Dependency-Aware Workflow",
                "\n".join(dependency_aware_guidance_statements()),
                "",
                "## Fallback Workflow",
                "\n".join(fallback_guidance_statements()),
                "",
                "## Shared Workflow/Policy Change Guardrails",
                "\n".join(workflow_policy_guardrail_statements()),
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert not any(
        issue.rule_id == "workflow_command_reference_missing" and issue.path == "AGENTS.md"
        for issue in result.errors
    )


def test_docs_freshness_flags_finish_dedupe_policy_duplication_outside_agents(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "ops" / "skills" / "horadus-cli" / "SKILL.md").write_text(
        "\n".join(
            [
                "Thin helper only.",
                completion_guidance_statements()[5],
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(
        issue.rule_id == "workflow_policy_statement_duplicated_outside_agents"
        and issue.path == "ops/skills/horadus-cli/SKILL.md"
        for issue in result.errors
    )


def test_docs_freshness_flags_missing_high_risk_review_statement_in_skill_docs(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "ops" / "skills" / "horadus-cli" / "SKILL.md").write_text(
        "Thin helper only.\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(
        issue.rule_id == "high_risk_pre_push_review_statement_missing"
        and issue.path == "ops/skills/horadus-cli/SKILL.md"
        for issue in result.errors
    )
