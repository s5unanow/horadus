from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import src.core.docs_freshness as docs_freshness_module
from src.core.docs_freshness import (
    DocsFreshnessIssue,
    DocsFreshnessResult,
    _extract_completed_task_ids,
    _extract_current_sprint_active_tasks,
    _extract_h2_section,
    _extract_human_blocker_metadata,
    _extract_section_task_ids,
    _extract_task_ids,
    _extract_telegram_launch_scope,
    _load_overrides,
    _Override,
    _parse_marker_date,
    _record_issue,
    run_docs_freshness_check,
)
from src.core.repo_workflow import (
    WORKFLOW_ESCAPE_HATCH_TEXT,
    canonical_task_workflow_command_templates,
    completion_guidance_statements,
    dependency_aware_guidance_statements,
    fallback_guidance_statements,
    workflow_policy_guardrail_statements,
)

pytestmark = pytest.mark.unit


def _seed_repo_layout(repo_root: Path, *, marker_date: str) -> None:
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (repo_root / "ops" / "skills" / "horadus-cli" / "references").mkdir(
        parents=True,
        exist_ok=True,
    )
    (repo_root / "src" / "api").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "core").mkdir(parents=True, exist_ok=True)
    (repo_root / "tasks").mkdir(parents=True, exist_ok=True)
    (repo_root / "tasks" / "specs").mkdir(parents=True, exist_ok=True)

    workflow_commands = canonical_task_workflow_command_templates()
    workflow_reference_block = "\n".join([*workflow_commands, WORKFLOW_ESCAPE_HATCH_TEXT, ""])
    completion_guidance_block = "\n".join([*completion_guidance_statements(), ""])
    dependency_guidance_block = "\n".join([*dependency_aware_guidance_statements(), ""])
    fallback_guidance_block = "\n".join([*fallback_guidance_statements(), ""])
    workflow_guardrail_block = "\n".join([*workflow_policy_guardrail_statements(), ""])

    (repo_root / "PROJECT_STATUS.md").write_text(
        (
            f"**Last Updated**: {marker_date}\n"
            "**Source-of-truth policy**: "
            "See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`\n"
        ),
        encoding="utf-8",
    )
    (repo_root / "tasks" / "CURRENT_SPRINT.md").write_text(
        "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`\n",
        encoding="utf-8",
    )
    (repo_root / "tasks" / "COMPLETED.md").write_text(
        "# Completed Tasks\n",
        encoding="utf-8",
    )
    (repo_root / "tasks" / "BACKLOG.md").write_text(
        completion_guidance_block,
        encoding="utf-8",
    )
    (repo_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "## Canonical Source-of-Truth Hierarchy",
                "",
                "## Development Commands",
                workflow_reference_block.strip(),
                "",
                "## Completion Policy",
                completion_guidance_block.strip(),
                "",
                "## Dependency-Aware Workflow",
                dependency_guidance_block.strip(),
                "",
                "## Fallback Workflow",
                fallback_guidance_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                workflow_reference_block.strip(),
                "",
                completion_guidance_block.strip(),
                "",
                dependency_guidance_block.strip(),
                "",
                fallback_guidance_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "AGENT_RUNBOOK.md").write_text(
        "\n".join(
            [
                workflow_reference_block.strip(),
                "",
                completion_guidance_block.strip(),
                "",
                dependency_guidance_block.strip(),
                "",
                fallback_guidance_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "ops" / "skills" / "horadus-cli" / "SKILL.md").write_text(
        "\n".join(
            [
                workflow_reference_block.strip(),
                "",
                completion_guidance_block.strip(),
                "",
                dependency_guidance_block.strip(),
                "",
                fallback_guidance_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "ops" / "skills" / "horadus-cli" / "references" / "commands.md").write_text(
        "\n".join(
            [
                workflow_reference_block.strip(),
                "",
                dependency_guidance_block.strip(),
                "",
                fallback_guidance_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "tasks" / "specs" / "TEMPLATE.md").write_text(
        "\n".join(
            [
                "# TASK-XXX: <Title>",
                "",
                "## Shared Workflow/Policy Change Checklist (Only If Applicable)",
                workflow_guardrail_block.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "ARCHITECTURE.md").write_text(
        f"**Last Verified**: {marker_date}\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "DATA_MODEL.md").write_text(
        "\n".join(
            [
                "### reports",
                "### api_usage",
                "### trend_outcomes",
                "### human_feedback",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "POTENTIAL_ISSUES.md").write_text(
        "\n".join(
            [
                "**Status**: Archived historical snapshot (superseded)",
                "Use `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`, and `PROJECT_STATUS.md`",
                "as the authoritative current trackers.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "DEPLOYMENT.md").write_text(
        f"**Last Verified**: {marker_date}\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "ENVIRONMENT.md").write_text(
        f"**Last Verified**: {marker_date}\nAPI_RATE_LIMIT_PER_MINUTE\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "RELEASING.md").write_text(
        f"**Last Verified**: {marker_date}\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "API.md").write_text(
        "X-API-Key\nAPI_AUTH_ENABLED\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "api" / "main.py").write_text(
        "app.add_middleware(APIKeyAuthMiddleware)\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "core" / "api_key_manager.py").write_text(
        "API_RATE_LIMIT_PER_MINUTE = 120\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "adr" / "001-example.md").write_text(
        "# ADR-001: Example\n",
        encoding="utf-8",
    )


def test_docs_freshness_detects_unoverridden_conflict_rule(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "POTENTIAL_ISSUES.md").write_text(
        "\n".join(
            [
                "**Status**: Archived historical snapshot (superseded)",
                "Use `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`, and `PROJECT_STATUS.md`",
                "as the authoritative current trackers.",
                "All API endpoints have no authentication checks.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "stale_auth_unenforced_claim" for issue in result.errors)


def test_docs_freshness_applies_override_with_rationale(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "POTENTIAL_ISSUES.md").write_text(
        "\n".join(
            [
                "**Status**: Archived historical snapshot (superseded)",
                "Use `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`, and `PROJECT_STATUS.md`",
                "as the authoritative current trackers.",
                "All API endpoints have no authentication checks.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    overrides = {
        "overrides": [
            {
                "rule_id": "stale_auth_unenforced_claim",
                "path": "docs/POTENTIAL_ISSUES.md",
                "reason": "Archived historical snapshot.",
                "expires_on": "2099-12-31",
            }
        ]
    }
    override_path = tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json"
    override_path.write_text(json.dumps(overrides), encoding="utf-8")

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=override_path,
    )

    assert not any(issue.rule_id == "stale_auth_unenforced_claim" for issue in result.errors)
    assert any(issue.rule_id == "docs_freshness_override_applied" for issue in result.warnings)


def test_docs_freshness_flags_stale_last_verified_marker(tmp_path: Path) -> None:
    stale_date = (datetime.now(tz=UTC) - timedelta(days=120)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=stale_date)

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
        max_age_days=30,
    )

    assert any(issue.rule_id == "required_marker_stale" for issue in result.errors)


def test_docs_freshness_flags_missing_hierarchy_heading(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "AGENTS.md").write_text("# Agent Instructions\n", encoding="utf-8")

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "hierarchy_policy_heading_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_workflow_command_reference(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "README.md").write_text(
        WORKFLOW_ESCAPE_HATCH_TEXT + "\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "workflow_command_reference_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_workflow_escape_hatch_guidance(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "AGENT_RUNBOOK.md").write_text(
        "\n".join([*canonical_task_workflow_command_templates(), ""]),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "workflow_escape_hatch_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_completion_guidance_statement(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(completion_guidance_statements()[1:]) + "\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "completion_guidance_statement_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_dependency_guidance_statement(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "ops" / "skills" / "horadus-cli" / "references" / "commands.md").write_text(
        "\n".join(dependency_aware_guidance_statements()[1:]) + "\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "dependency_guidance_statement_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_fallback_guidance_statement(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "ops" / "skills" / "horadus-cli" / "SKILL.md").write_text(
        "\n".join(fallback_guidance_statements()[1:]) + "\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "fallback_guidance_statement_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_workflow_policy_guardrail_statement(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "specs" / "TEMPLATE.md").write_text(
        "\n".join(workflow_policy_guardrail_statements()[1:]) + "\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(
        issue.rule_id == "workflow_policy_guardrail_statement_missing" for issue in result.errors
    )


def test_docs_freshness_keeps_dependency_and_fallback_path_sets_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)

    dependency_only_path = "docs/dependency-only.md"
    fallback_only_path = "docs/fallback-only.md"
    (tmp_path / dependency_only_path).write_text(
        "\n".join(dependency_aware_guidance_statements()[1:]) + "\n",
        encoding="utf-8",
    )
    (tmp_path / fallback_only_path).write_text(
        "\n".join(fallback_guidance_statements()) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        docs_freshness_module,
        "DEPENDENCY_AWARE_GUIDANCE_REFERENCE_PATHS",
        (dependency_only_path,),
    )
    monkeypatch.setattr(
        docs_freshness_module,
        "FALLBACK_GUIDANCE_REFERENCE_PATHS",
        (fallback_only_path,),
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "dependency_guidance_statement_missing" for issue in result.errors)
    assert not any(
        issue.path == fallback_only_path
        and issue.rule_id == "dependency_guidance_statement_missing"
        for issue in result.errors
    )


def test_docs_freshness_flags_missing_hierarchy_reference_link(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "This sprint file has no hierarchy link.\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "hierarchy_policy_reference_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_adr_target(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text(
        f"**Last Verified**: {marker_date}\nSee ADR-999 for details.\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "adr_reference_target_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_data_model_required_table(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "DATA_MODEL.md").write_text(
        "### reports\n### api_usage\n### trend_outcomes\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "data_model_table_coverage_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_archived_doc_pointer(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "POTENTIAL_ISSUES.md").write_text(
        "**Status**: Archived historical snapshot (superseded)\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(
        issue.rule_id == "archived_doc_authoritative_pointer_missing" for issue in result.errors
    )


def test_docs_freshness_allows_override_for_new_rules(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text(
        f"**Last Verified**: {marker_date}\nSee ADR-999 for details.\n",
        encoding="utf-8",
    )
    overrides = {
        "overrides": [
            {
                "rule_id": "adr_reference_target_missing",
                "path": "docs/ARCHITECTURE.md",
                "reason": "ADR draft queued for same sprint.",
                "expires_on": "2099-12-31",
            }
        ]
    }
    override_path = tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json"
    override_path.write_text(json.dumps(overrides), encoding="utf-8")

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=override_path,
    )

    assert not any(issue.rule_id == "adr_reference_target_missing" for issue in result.errors)
    assert any(issue.rule_id == "docs_freshness_override_applied" for issue in result.warnings)


def test_docs_freshness_flags_dual_listed_in_progress_and_completed_task(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-113` Recovery follow-up",
                "## Completed This Sprint",
                "- `TASK-112` Prior work",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-113` Recovery follow-up",
                "## Blocked",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "COMPLETED.md").write_text(
        "- TASK-113: Complete Deferred Eval Mode and Vector Revalidation Recovery ✅\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "task_status_dual_listing" for issue in result.errors)


def test_docs_freshness_flags_active_sprint_task_missing_from_project_status_in_progress(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-126` Taxonomy Drift Guardrails",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
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
        issue.rule_id == "project_status_missing_active_sprint_task" for issue in result.errors
    )


def test_docs_freshness_flags_human_gated_sprint_task_missing_from_project_status_blocked(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- none",
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
        issue.rule_id == "project_status_missing_blocked_human_task" for issue in result.errors
    )


def test_docs_freshness_no_human_blockers_does_not_require_blocker_metadata(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-164` Agent smoke run",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-164` Agent smoke run",
                "## Blocked",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert not any(issue.rule_id.startswith("human_blocker_metadata_") for issue in result.errors)
    assert not any(issue.rule_id == "telegram_launch_scope_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_human_blocker_metadata(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert any(issue.rule_id == "human_blocker_metadata_missing" for issue in result.errors)
    assert any(issue.rule_id == "telegram_launch_scope_missing" for issue in result.errors)


def test_docs_freshness_accepts_present_human_blocker_metadata(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- TASK-080 | owner=ops-lead | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert not any(issue.rule_id.startswith("human_blocker_metadata_") for issue in result.errors)
    assert not any(issue.rule_id == "telegram_launch_scope_missing" for issue in result.errors)


def test_docs_freshness_flags_stale_project_status_during_active_sprint(tmp_path: Path) -> None:
    marker_date = (datetime.now(tz=UTC) - timedelta(days=9)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-164` Agent smoke run",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-164` Agent smoke run",
                "## Blocked",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
        project_status_max_age_days=7,
    )

    assert any(issue.rule_id == "project_status_freshness_sla" for issue in result.errors)


def test_docs_freshness_allows_project_status_at_sla_boundary(tmp_path: Path) -> None:
    marker_date = (datetime.now(tz=UTC) - timedelta(days=7)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-164` Agent smoke run",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-164` Agent smoke run",
                "## Blocked",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
        project_status_max_age_days=7,
    )

    assert not any(issue.rule_id == "project_status_freshness_sla" for issue in result.errors)


def test_docs_freshness_result_is_ok_tracks_error_presence() -> None:
    assert DocsFreshnessResult(errors=(), warnings=()).is_ok is True
    assert (
        DocsFreshnessResult(
            errors=(DocsFreshnessIssue(level="error", rule_id="x", message="y"),),
            warnings=(),
        ).is_ok
        is False
    )


def test_load_overrides_validates_shape_and_required_fields(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.json"
    assert _load_overrides(missing_file) == ()

    override_path = tmp_path / "overrides.json"
    override_path.write_text(json.dumps({"overrides": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an 'overrides' list"):
        _load_overrides(override_path)

    override_path.write_text(json.dumps({"overrides": ["bad"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="is not an object"):
        _load_overrides(override_path)

    override_path.write_text(json.dumps({"overrides": [{"rule_id": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        _load_overrides(override_path)

    override_path.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "rule_id": "rule",
                        "path": "docs/file.md",
                        "reason": "temporary",
                        "expires_on": "2099-12-31",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_overrides(override_path)
    assert loaded[0] == _Override(
        rule_id="rule",
        path="docs/file.md",
        reason="temporary",
        expires_on=datetime(2099, 12, 31, tzinfo=UTC).date(),
    )


def test_helper_extractors_cover_missing_and_present_sections() -> None:
    content = "\n".join(
        [
            "**Last Updated**: 2026-03-08",
            "## Active Tasks",
            "- TASK-001 alpha",
            "- TASK-002 beta [REQUIRES_HUMAN]",
            "## Human Blocker Metadata",
            "- TASK-002 | owner=ops | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
            "## Telegram Launch Scope",
            "- launch_scope: excluded",
            "## Completed This Sprint",
            "- TASK-003 gamma",
            "",
        ]
    )

    assert _parse_marker_date(content, "Last Updated") == datetime(2026, 3, 8, tzinfo=UTC).date()
    assert _parse_marker_date(content, "Missing") is None
    assert _extract_h2_section(content, "Active Tasks") is not None
    assert _extract_h2_section(content, "Missing") is None
    assert _extract_task_ids(content) == {"TASK-001", "TASK-002", "TASK-003"}
    assert _extract_section_task_ids(content, "Completed This Sprint") == {"TASK-003"}
    assert _extract_current_sprint_active_tasks(content) == (
        {"TASK-001", "TASK-002"},
        {"TASK-002"},
    )
    assert _extract_human_blocker_metadata(content)["TASK-002"]["owner"] == "ops"
    assert _extract_telegram_launch_scope(content) == "excluded"
    assert _extract_completed_task_ids(content) == {"TASK-001", "TASK-002", "TASK-003"}


def test_helper_extractors_handle_missing_or_partial_metadata() -> None:
    content = "\n".join(
        [
            "## Human Blocker Metadata",
            "not-a-bullet",
            "- no task id here | owner=ops",
            "- TASK-010 | owner=ops | malformed | =blank",
            "## Telegram Launch Scope",
            "- launch_scope:",
            "",
        ]
    )

    assert _extract_human_blocker_metadata(content) == {"TASK-010": {"owner": "ops"}}
    assert _extract_telegram_launch_scope(content) is None
    assert _extract_section_task_ids(content, "Missing") == set()


def test_record_issue_adds_error_or_override_warning() -> None:
    errors: list[DocsFreshnessIssue] = []
    warnings: list[DocsFreshnessIssue] = []
    override = _Override(
        rule_id="rule",
        path="docs/file.md",
        reason="temporary",
        expires_on=datetime(2099, 12, 31, tzinfo=UTC).date(),
    )

    _record_issue(
        errors=errors,
        warnings=warnings,
        active_override_map={},
        rule_id="rule",
        message="broken",
        path="docs/file.md",
    )
    assert errors[0].rule_id == "rule"

    _record_issue(
        errors=errors,
        warnings=warnings,
        active_override_map={("rule", "docs/file.md"): override},
        rule_id="rule",
        message="broken",
        path="docs/file.md",
    )
    assert warnings[-1].rule_id == "docs_freshness_override_applied"


def test_docs_freshness_flags_missing_required_marker_file(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "DEPLOYMENT.md").unlink()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "required_marker_file_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_and_future_markers(tmp_path: Path) -> None:
    marker_date = (datetime.now(tz=UTC) + timedelta(days=3)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "RELEASING.md").write_text("no marker here\n", encoding="utf-8")

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "required_marker_missing" for issue in result.errors)
    assert any(issue.rule_id == "required_marker_future_date" for issue in result.errors)


def test_docs_freshness_flags_missing_hierarchy_files_and_references(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "AGENTS.md").unlink()
    (tmp_path / "PROJECT_STATUS.md").unlink()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "hierarchy_policy_file_missing" for issue in result.errors)
    assert any(
        issue.rule_id == "hierarchy_policy_reference_file_missing" for issue in result.errors
    )


def test_docs_freshness_flags_human_blocker_metadata_variants(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- TASK-080 | owner=ops | last_touched=bad-date | next_action=2026-02-28 | escalate_after_days=0",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "human_blocker_metadata_invalid_date" for issue in result.errors)
    assert any(
        issue.rule_id == "human_blocker_metadata_invalid_escalation_threshold"
        for issue in result.errors
    )


def test_docs_freshness_flags_missing_fields_and_non_integer_escalation(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- TASK-080 | owner=ops | next_action=2026-03-01 | escalate_after_days=soon",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "human_blocker_metadata_missing_fields" for issue in result.errors)
    assert any(
        issue.rule_id == "human_blocker_metadata_invalid_escalation_threshold"
        for issue in result.errors
    )


def test_docs_freshness_allows_blank_optional_metadata_fields_to_skip_date_checks(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- TASK-080 | owner=ops | last_touched= | next_action= | escalate_after_days=",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "human_blocker_metadata_missing_fields" for issue in result.errors)
    assert not any(
        issue.rule_id == "human_blocker_metadata_invalid_date" for issue in result.errors
    )


def test_docs_freshness_flags_human_blocker_date_order_and_future_date(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    future_day = (datetime.now(tz=UTC) + timedelta(days=1)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                f"- TASK-080 | owner=ops | last_touched={future_day} | next_action=2026-03-01 | escalate_after_days=7",
                "",
                "## Telegram Launch Scope",
                "- launch_scope: excluded_until_task_080_done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-080` Telegram Collector Task Wiring [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "human_blocker_metadata_future_date" for issue in result.errors)
    assert any(
        issue.rule_id == "human_blocker_metadata_invalid_date_order" for issue in result.errors
    )


def test_docs_freshness_flags_missing_archived_and_data_model_docs(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "POTENTIAL_ISSUES.md").unlink()
    (tmp_path / "docs" / "DATA_MODEL.md").unlink()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "archived_doc_missing" for issue in result.errors)
    assert any(issue.rule_id == "data_model_doc_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_archived_status_banner(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "POTENTIAL_ISSUES.md").write_text(
        "tasks/CURRENT_SPRINT.md\nPROJECT_STATUS.md\ntasks/BACKLOG.md\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "archived_doc_status_banner_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_runtime_doc_markers(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "API.md").write_text("plain docs\n", encoding="utf-8")
    (tmp_path / "docs" / "ENVIRONMENT.md").write_text(
        f"**Last Verified**: {marker_date}\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert any(issue.rule_id == "runtime_marker_auth_header_doc_missing" for issue in result.errors)
    assert any(issue.rule_id == "runtime_marker_auth_toggle_doc_missing" for issue in result.errors)
    assert any(issue.rule_id == "runtime_marker_rate_limit_doc_missing" for issue in result.errors)


def test_docs_freshness_skips_runtime_marker_checks_when_runtime_or_docs_missing(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "docs" / "API.md").unlink()
    (tmp_path / "docs" / "ENVIRONMENT.md").unlink()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert not any(issue.rule_id.startswith("runtime_marker_") for issue in result.errors)


def test_docs_freshness_handles_missing_completed_ledger_and_last_updated_marker(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "COMPLETED.md").unlink()
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-164` Agent smoke run",
                "## Blocked",
                "- none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-164` Agent smoke run",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path, project_status_max_age_days=1)

    assert not any(issue.rule_id == "project_status_freshness_sla" for issue in result.errors)


def test_docs_freshness_handles_missing_adr_directory_and_duplicate_references(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    for adr_file in (tmp_path / "docs" / "adr").glob("*.md"):
        adr_file.unlink()
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text(
        f"**Last Verified**: {marker_date}\nADR-999 and ADR-999 appear twice.\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    missing_adr_errors = [
        issue for issue in result.errors if issue.rule_id == "adr_reference_target_missing"
    ]
    assert len(missing_adr_errors) == 1


def test_docs_freshness_does_not_require_telegram_scope_for_other_human_tasks(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## Active Tasks",
                "- `TASK-081` Other Human Task [REQUIRES_HUMAN]",
                "",
                "## Human Blocker Metadata",
                "- TASK-081 | owner=ops | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                f"**Last Updated**: {marker_date}",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "## In Progress",
                "- `TASK-081` Other Human Task [REQUIRES_HUMAN]",
                "## Blocked",
                "- `TASK-081` Other Human Task [REQUIRES_HUMAN]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert not any(issue.rule_id == "telegram_launch_scope_missing" for issue in result.errors)


def test_docs_freshness_handles_missing_adr_dir_without_references(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    for adr_file in (tmp_path / "docs" / "adr").glob("*.md"):
        adr_file.unlink()
    (tmp_path / "docs" / "adr").rmdir()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert not any(issue.rule_id == "adr_reference_target_missing" for issue in result.errors)
