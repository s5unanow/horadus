from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import tools.horadus.python.horadus_workflow.docs_freshness as docs_freshness_module
from tools.horadus.python.horadus_workflow.docs_freshness import (
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
from tools.horadus.python.horadus_workflow.repo_workflow import (
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
    (repo_root / "archive" / "2026-03-10-sprint-3-close").mkdir(parents=True, exist_ok=True)
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
        "\n".join(
            [
                "# Project Status",
                "",
                "**Status**: Archived pointer stub (non-authoritative)",
                "**Archived Detailed Status On**: 2026-03-10",
                "",
                "- `tasks/CURRENT_SPRINT.md`",
                "- `tasks/BACKLOG.md`",
                "- `tasks/COMPLETED.md`",
                "- `archive/2026-03-10-sprint-3-close/PROJECT_STATUS.md`",
                "",
                "Do not read `archive/` during normal implementation flow unless a user explicitly asks for historical context or an archive-aware CLI flag is used.",
                "",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "",
            ]
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
                "## Shared Workflow/Policy Change Guardrails",
                workflow_guardrail_block.strip(),
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
                workflow_guardrail_block.strip(),
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
                workflow_guardrail_block.strip(),
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
                "Use `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`, `tasks/COMPLETED.md`, and `PROJECT_STATUS.md`",
                "as the authoritative current trackers.",
                "Do not read `archive/` by default unless a user explicitly requests historical context.",
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
        issue.rule_id == "workflow_policy_guardrail_statement_missing"
        and issue.path == "tasks/specs/TEMPLATE.md"
        for issue in result.errors
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


def test_docs_freshness_flags_missing_project_status_stub_status(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                "# Project Status",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
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

    assert any(issue.rule_id == "project_status_stub_status_missing" for issue in result.errors)


def test_docs_freshness_flags_missing_project_status_archive_pointer(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                "# Project Status",
                "",
                "**Status**: Archived pointer stub (non-authoritative)",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "- `tasks/CURRENT_SPRINT.md`",
                "- `tasks/BACKLOG.md`",
                "- `tasks/COMPLETED.md`",
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
        issue.rule_id == "project_status_stub_archive_pointer_missing" for issue in result.errors
    )


def test_docs_freshness_flags_missing_project_status_archive_guidance(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                "# Project Status",
                "",
                "**Status**: Archived pointer stub (non-authoritative)",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
                "- `tasks/CURRENT_SPRINT.md`",
                "- `tasks/BACKLOG.md`",
                "- `tasks/COMPLETED.md`",
                "- `archive/2026-03-10-sprint-3-close/PROJECT_STATUS.md`",
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
        issue.rule_id == "project_status_archive_guidance_missing" for issue in result.errors
    )


def test_docs_freshness_accepts_newer_project_status_archive_pointer(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "PROJECT_STATUS.md").write_text(
        "\n".join(
            [
                "# Project Status",
                "",
                "**Status**: Archived pointer stub (non-authoritative)",
                "**Archived Detailed Status On**: 2026-03-24",
                "",
                "- `tasks/CURRENT_SPRINT.md`",
                "- `tasks/BACKLOG.md`",
                "- `tasks/COMPLETED.md`",
                "- `archive/2026-03-24-sprint-4-close/PROJECT_STATUS.md`",
                "",
                "Do not read `archive/` during normal implementation flow unless a user explicitly asks for historical context or an archive-aware CLI flag is used.",
                "",
                "**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`",
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
        issue.rule_id == "project_status_stub_archive_pointer_missing" for issue in result.errors
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


def test_docs_freshness_accepts_project_status_stub_without_freshness_sla(tmp_path: Path) -> None:
    marker_date = (datetime.now(tz=UTC) - timedelta(days=9)).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
        project_status_max_age_days=7,
    )

    assert not any(issue.rule_id == "project_status_freshness_sla" for issue in result.errors)


def test_docs_freshness_skips_current_sprint_rules_when_sprint_file_missing(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").unlink()

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        override_path=tmp_path / "docs" / "DOCS_FRESHNESS_OVERRIDES.json",
    )

    assert not any(issue.rule_id.startswith("human_blocker_metadata_") for issue in result.errors)


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


def test_docs_freshness_warns_for_missing_backlog_only_planning_artifact(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-298: Planning fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — backlog-only fixture",
                "",
                "Planning fixture body.",
                "",
                "**Files**: `tasks/BACKLOG.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] planning warning appears",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        planning_artifact_paths=("tasks/BACKLOG.md",),
    )

    warning_ids = [issue.rule_id for issue in result.warnings]
    assert "planning_artifact_missing" in warning_ids
    assert not any(issue.rule_id == "planning_artifact_missing" for issue in result.errors)


def test_docs_freshness_warns_for_incomplete_planning_spec(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-275: Planning fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — spec fixture",
                "",
                "Planning fixture body.",
                "",
                "**Files**: `tasks/specs/275-planning-fixture.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] planning warning appears",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "specs" / "275-planning-fixture.md").write_text(
        "\n".join(
            [
                "# TASK-275: Planning fixture",
                "",
                "**Planning Gates**: Required — spec fixture",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
                "- `Simplicity Gate`: Extend the fixture.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        planning_artifact_paths=("tasks/specs/275-planning-fixture.md",),
    )

    warning_ids = {issue.rule_id for issue in result.warnings}
    assert "planning_core_gate_missing" in warning_ids
    assert "planning_conditional_gate_missing" in warning_ids
    assert "planning_integration_proof_incomplete" in warning_ids


def test_docs_freshness_accepts_complete_planning_exec_plan(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-298: Planning fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
                "",
                "Planning fixture body.",
                "",
                "**Files**: `tasks/exec_plans/TASK-298.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] planning warning stays quiet",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-298.md").write_text(
        "\n".join(
            [
                "# TASK-298: Planning fixture",
                "",
                "## Status",
                "- Planning Gates: Required — exec-plan fixture",
                "",
                "## Gate Outcomes / Waivers",
                "",
                "- Accepted design / smallest safe shape: keep the fixture small.",
                "- Rejected simpler alternative: omit the section.",
                "- First integration proof: run docs freshness with an explicit planning artifact override.",
                "- Waivers: none.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_docs_freshness_check(
        repo_root=tmp_path,
        planning_artifact_paths=("tasks/exec_plans/TASK-298.md",),
    )

    assert not any(issue.path == "tasks/exec_plans/TASK-298.md" for issue in result.warnings)


def test_planning_helper_functions_cover_marker_state_and_git_diff_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "### TASK-275: Spec-backed fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Planning Gates**: Required — spec fixture",
                "",
                "Body.",
                "",
                "**Files**: `tasks/specs/275-example.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] ok",
                "",
                "---",
                "",
                "### TASK-298: Exec-plan fixture",
                "**Priority**: P2",
                "**Estimate**: 1h",
                "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
                "",
                "Body.",
                "",
                "**Files**: `tasks/exec_plans/TASK-298.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] ok",
                "",
                "---",
                "",
                "### TASK-299: Quiet fixture",
                "**Priority**: P3",
                "**Estimate**: 15m",
                "**Planning Gates**: Not Required — tiny docs-only follow-up",
                "",
                "Body.",
                "",
                "**Files**: `docs/AGENT_RUNBOOK.md`",
                "",
                "**Acceptance Criteria**:",
                "- [ ] ok",
                "",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "specs" / "275-example.md").write_text(
        "**Planning Gates**: Required — spec fixture\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-298.md").write_text(
        "- Planning Gates: Required — exec plan fixture\n",
        encoding="utf-8",
    )
    backlog_text = (tmp_path / "tasks" / "BACKLOG.md").read_text(encoding="utf-8")

    assert docs_freshness_module._planning_marker_value(
        "x\n**Planning Gates**: Required — yes\n"
    ) == ("Required — yes")
    assert docs_freshness_module._planning_marker_value("no marker") is None
    assert docs_freshness_module._planning_required_from_value("Required — yes") is True
    assert docs_freshness_module._planning_required_from_value("`Required` — yes") is True
    assert docs_freshness_module._planning_required_from_value("Not Required — no") is False
    assert docs_freshness_module._planning_required_from_value("`Not Required` — no") is False
    assert docs_freshness_module._planning_required_from_value("unclear") is None
    assert (
        docs_freshness_module._exec_plan_required_from_backlog(
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)"
        )
        is True
    )
    assert docs_freshness_module._exec_plan_required_from_backlog("no") is False
    assert (
        docs_freshness_module._task_id_from_planning_artifact_path("tasks/specs/275-example.md")
        == "TASK-275"
    )
    assert (
        docs_freshness_module._task_id_from_planning_artifact_path("tasks/exec_plans/TASK-298.md")
        == "TASK-298"
    )
    assert (
        docs_freshness_module._task_id_from_planning_artifact_path("tasks/specs/not-a-spec.md")
        is None
    )
    assert (
        docs_freshness_module._task_id_from_planning_artifact_path("tasks/exec_plans/not-a-plan.md")
        is None
    )
    assert docs_freshness_module._task_id_from_planning_artifact_path("README.md") is None
    assert docs_freshness_module._extract_task_block(backlog_text, "TASK-275") is not None
    assert docs_freshness_module._extract_task_block(backlog_text, "TASK-999") is None
    assert docs_freshness_module._task_spec_paths(tmp_path, "TASK-275") == (
        "tasks/specs/275-example.md",
    )
    assert docs_freshness_module._task_exec_plan_paths(tmp_path, "TASK-298") == (
        "tasks/exec_plans/TASK-298.md",
    )
    assert docs_freshness_module._task_exec_plan_paths(tmp_path, "TASK-299") == ()

    spec_state = docs_freshness_module._planning_state_for_task(
        tmp_path,
        task_id="TASK-275",
        backlog_text=backlog_text,
    )
    exec_state = docs_freshness_module._planning_state_for_task(
        tmp_path,
        task_id="TASK-298",
        backlog_text=backlog_text,
    )
    quiet_state = docs_freshness_module._planning_state_for_task(
        tmp_path,
        task_id="TASK-299",
        backlog_text=backlog_text,
    )

    assert spec_state["state"] == "applicable_spec_backed_without_exec_plan"
    assert exec_state["state"] == "applicable_with_authoritative_artifact_present"
    assert quiet_state["state"] == "non_applicable"

    monkeypatch.setattr(docs_freshness_module.shutil, "which", lambda _name: None)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == ()

    monkeypatch.setattr(docs_freshness_module.shutil, "which", lambda _name: "/usr/bin/git")

    class _CompletedProcess:
        def __init__(self, returncode: int, stdout: str) -> None:
            self.returncode = returncode
            self.stdout = stdout

    merge_fail_calls: list[list[str]] = []

    def _merge_fail(cmd: list[str], **_kwargs: object) -> _CompletedProcess:
        merge_fail_calls.append(cmd)
        return _CompletedProcess(1, "")

    monkeypatch.setattr(docs_freshness_module.subprocess, "run", _merge_fail)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == ()
    assert merge_fail_calls

    def _empty_merge_base(cmd: list[str], **_kwargs: object) -> _CompletedProcess:
        if cmd[1] == "merge-base":
            return _CompletedProcess(0, "")
        return _CompletedProcess(0, "")

    monkeypatch.setattr(docs_freshness_module.subprocess, "run", _empty_merge_base)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == ()

    def _diff_failure(cmd: list[str], **_kwargs: object) -> _CompletedProcess:
        if cmd[1] == "merge-base":
            return _CompletedProcess(0, "abc123\n")
        return _CompletedProcess(1, "")

    monkeypatch.setattr(docs_freshness_module.subprocess, "run", _diff_failure)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == ()

    def _raise_file_not_found(_cmd: list[str], **_kwargs: object) -> _CompletedProcess:
        raise FileNotFoundError

    monkeypatch.setattr(docs_freshness_module.subprocess, "run", _raise_file_not_found)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == ()

    def _successful_diff(cmd: list[str], **_kwargs: object) -> _CompletedProcess:
        if cmd[1] == "merge-base":
            return _CompletedProcess(0, "abc123\n")
        return _CompletedProcess(
            0,
            "\n".join(
                [
                    "tasks/specs/TEMPLATE.md",
                    "",
                    "tasks/specs/275-example.md",
                    "tasks/exec_plans/TEMPLATE.md",
                    "tasks/exec_plans/TASK-298.md",
                    "tasks/BACKLOG.md",
                    "README.md",
                    "tasks/specs/275-example.md",
                ]
            ),
        )

    monkeypatch.setattr(docs_freshness_module.subprocess, "run", _successful_diff)
    assert docs_freshness_module._changed_planning_artifact_paths(tmp_path) == (
        "tasks/specs/TEMPLATE.md",
        "tasks/specs/275-example.md",
        "tasks/exec_plans/TEMPLATE.md",
        "tasks/exec_plans/TASK-298.md",
        "tasks/BACKLOG.md",
    )


def test_validate_planning_artifact_covers_template_and_exec_plan_paths(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    backlog_text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-275: Spec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/275-example.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
            "### TASK-298: Exec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `tasks/exec_plans/TASK-298.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text(backlog_text, encoding="utf-8")
    (tmp_path / "tasks" / "specs" / "275-example.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "**Planning Gates**: Required — spec fixture",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
                "- `Simplicity Gate`: ok",
                "- `Anti-Abstraction Gate`: ok",
                "- `Integration-First Gate`:",
                "  - Validation target: ok",
                "  - Exercises: ok",
                "- `Determinism Gate`: Not applicable — fixture",
                "- `LLM Budget/Safety Gate`: Not applicable — fixture",
                "- `Observability Gate`: Not applicable — fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-298.md").write_text(
        "\n".join(
            [
                "# plan",
                "",
                "## Gate Outcomes / Waivers",
                "",
                "- Accepted design / smallest safe shape: ok",
                "- Rejected simpler alternative: ok",
                "- First integration proof: ok",
                "- Waivers: none",
                "",
            ]
        ),
        encoding="utf-8",
    )

    missing_template = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/specs/TEMPLATE.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in missing_template} == {
        "planning_marker_missing",
        "planning_spec_section_missing",
    }

    (tmp_path / "tasks" / "specs" / "TEMPLATE.md").write_text(
        "**Planning Gates**: Required\n## Phase -1 / Pre-Implementation Gates\n",
        encoding="utf-8",
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/specs/TEMPLATE.md",
            backlog_text=backlog_text,
        )
        == ()
    )

    (tmp_path / "tasks" / "exec_plans" / "TEMPLATE.md").write_text("", encoding="utf-8")
    missing_exec_template = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TEMPLATE.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in missing_exec_template} == {
        "planning_marker_missing",
        "planning_gate_outcomes_missing",
    }

    (tmp_path / "tasks" / "exec_plans" / "TEMPLATE.md").write_text(
        "Planning Gates: Required\n## Gate Outcomes / Waivers\n",
        encoding="utf-8",
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TEMPLATE.md",
            backlog_text=backlog_text,
        )
        == ()
    )

    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/specs/275-example.md",
            backlog_text=backlog_text,
        )
        == ()
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TASK-298.md",
            backlog_text=backlog_text,
        )
        == ()
    )
    backlog_issue_set = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/BACKLOG.md",
        backlog_text=backlog_text,
    )
    assert backlog_issue_set == ()
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/specs/missing.md",
            backlog_text=backlog_text,
        )
        == ()
    )

    (tmp_path / "tasks" / "specs" / "276-not-required.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "**Planning Gates**: Not Required — tiny follow-up",
                "",
            ]
        ),
        encoding="utf-8",
    )
    backlog_with_quiet = backlog_text + "\n".join(
        [
            "### TASK-276: Quiet fixture",
            "**Priority**: P3",
            "**Estimate**: 15m",
            "**Planning Gates**: Not Required — tiny follow-up",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/276-not-required.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/specs/276-not-required.md",
            backlog_text=backlog_with_quiet,
        )
        == ()
    )

    (tmp_path / "tasks" / "specs" / "277-incomplete.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "## Phase -1 / Pre-Implementation Gates",
                "",
            ]
        ),
        encoding="utf-8",
    )
    backlog_with_incomplete = backlog_with_quiet + "\n".join(
        [
            "### TASK-277: Incomplete spec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/277-incomplete.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    incomplete_spec_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/specs/277-incomplete.md",
        backlog_text=backlog_with_incomplete,
    )
    assert {issue.rule_id for issue in incomplete_spec_issues} >= {
        "planning_marker_missing",
        "planning_core_gate_missing",
        "planning_conditional_gate_missing",
        "planning_integration_proof_incomplete",
    }

    (tmp_path / "tasks" / "specs" / "278-no-section.md").write_text(
        "\n".join(
            [
                "# spec",
                "",
                "**Planning Gates**: Required — spec fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )
    backlog_with_no_section = backlog_with_incomplete + "\n".join(
        [
            "### TASK-278: Missing section fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Planning Gates**: Required — spec fixture",
            "",
            "Body.",
            "",
            "**Files**: `tasks/specs/278-no-section.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    missing_section_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/specs/278-no-section.md",
        backlog_text=backlog_with_no_section,
    )
    assert {issue.rule_id for issue in missing_section_issues} == {"planning_spec_section_missing"}

    (tmp_path / "tasks" / "exec_plans" / "TASK-299.md").write_text("# plan\n", encoding="utf-8")
    backlog_with_missing_exec = backlog_with_incomplete + "\n".join(
        [
            "### TASK-299: Incomplete exec fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `tasks/exec_plans/TASK-299.md`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )
    incomplete_exec_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-299.md",
        backlog_text=backlog_with_missing_exec,
    )
    assert {issue.rule_id for issue in incomplete_exec_issues} >= {
        "planning_gate_outcomes_missing",
        "planning_gate_outcome_field_missing",
    }

    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="README.md",
            backlog_text=backlog_text,
        )
        == ()
    )
    (tmp_path / "tasks" / "notes.md").write_text("notes\n", encoding="utf-8")
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/notes.md",
            backlog_text=backlog_text,
        )
        == ()
    )


def test_docs_freshness_handles_missing_backlog_file_for_planning_scan(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "BACKLOG.md").unlink()

    result = run_docs_freshness_check(repo_root=tmp_path)

    assert result.errors
