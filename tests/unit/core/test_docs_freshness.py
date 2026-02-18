from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.docs_freshness import run_docs_freshness_check

pytestmark = pytest.mark.unit


def _seed_repo_layout(repo_root: Path, *, marker_date: str) -> None:
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "api").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "core").mkdir(parents=True, exist_ok=True)
    (repo_root / "tasks").mkdir(parents=True, exist_ok=True)

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
    (repo_root / "AGENTS.md").write_text(
        "## Canonical Source-of-Truth Hierarchy\n",
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
