from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.horadus.python.horadus_workflow._docs_freshness_planning as planning_module
import tools.horadus.python.horadus_workflow._docs_freshness_planning_hotspots as hotspots_module
import tools.horadus.python.horadus_workflow.docs_freshness as docs_freshness_module
from tests.workflow.test_docs_freshness import _seed_repo_layout

pytestmark = pytest.mark.unit


def _write_code_shape_policy(repo_root: Path, *legacy_file_blocks: str) -> None:
    (repo_root / "config" / "quality").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "quality" / "code_shape.toml").write_text(
        "\n".join(
            [
                "[budgets]",
                "production_module_lines = 700",
                "test_module_lines = 1200",
                "production_function_lines = 100",
                "test_function_lines = 160",
                "production_member_complexity = 20",
                "test_member_complexity = 25",
                "",
                "[paths]",
                'include_roots = ["src", "tools", "tests", "scripts"]',
                'exclude_globs = ["**/__pycache__/**"]',
                "",
                *legacy_file_blocks,
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_planning_state_requires_artifact_for_allowlisted_production_hotspot(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    _write_code_shape_policy(
        tmp_path,
        "[[legacy_files]]",
        'path = "tools/horadus/python/horadus_workflow/_docs_freshness_planning.py"',
        "[legacy_files.member_max_lines]",
        '"_validate_planning_artifact" = 180',
    )
    backlog_text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-310: Hotspot-only fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "",
            "Body.",
            "",
            "**Files**: `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] planning becomes required",
            "",
            "---",
            "",
        ]
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text(backlog_text, encoding="utf-8")

    state = docs_freshness_module._planning_state_for_task(
        tmp_path,
        task_id="TASK-310",
        backlog_text=backlog_text,
    )

    assert state["required"] is True
    assert state["state"] == "applicable_backlog_only_missing_artifact"
    assert state["hotspot_paths"] == (
        "tools/horadus/python/horadus_workflow/_docs_freshness_planning.py",
    )


def test_validate_planning_artifact_requires_hotspot_outcome_for_allowlisted_production_files(
    tmp_path: Path,
) -> None:
    backlog_text, base_exec_plan = _seed_hotspot_exec_plan_fixture(tmp_path)
    missing_marker_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in missing_marker_issues} == {
        "planning_hotspot_outcome_missing"
    }

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — cleanup later\n",
        encoding="utf-8",
    )
    followup_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in followup_issues} == {
        "planning_hotspot_followup_missing_task"
    }


def test_validate_planning_artifact_requires_distinct_existing_followup_tasks(
    tmp_path: Path,
) -> None:
    backlog_text, base_exec_plan = _seed_hotspot_exec_plan_fixture(tmp_path)

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-999 cleanup later\n",
        encoding="utf-8",
    )
    unknown_followup_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in unknown_followup_issues} == {
        "planning_hotspot_followup_unknown_task"
    }

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-320 cleanup later\n",
        encoding="utf-8",
    )
    same_task_followup_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in same_task_followup_issues} == {
        "planning_hotspot_followup_same_task"
    }

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan
        + "- Hotspot Outcome: follow-up-task-created — TASK-320 and TASK-999 cleanup later\n",
        encoding="utf-8",
    )
    mixed_same_and_unknown_followup_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_text,
    )
    assert {issue.rule_id for issue in mixed_same_and_unknown_followup_issues} == {
        "planning_hotspot_followup_unknown_task"
    }

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan + "- Hotspot Outcome: follow-up-task-created — TASK-999 cleanup later\n",
        encoding="utf-8",
    )
    backlog_with_prose_reference = backlog_text.replace(
        "Body.",
        "Body. Historical note: TASK-999 existed in a draft but was never promoted.",
        1,
    )
    unknown_from_prose_reference_issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text=backlog_with_prose_reference,
    )
    assert {issue.rule_id for issue in unknown_from_prose_reference_issues} == {
        "planning_hotspot_followup_unknown_task"
    }

    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan
        + "- Hotspot Outcome: keep-flat-with-rationale — validator-only change stays inside the existing hotspot.\n",
        encoding="utf-8",
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TASK-320.md",
            backlog_text=backlog_text,
        )
        == ()
    )
    assert (
        docs_freshness_module._validate_planning_artifact(
            repo_root=tmp_path,
            relative_path="tasks/exec_plans/TASK-321.md",
            backlog_text=backlog_text,
        )
        == ()
    )


def _seed_hotspot_exec_plan_fixture(tmp_path: Path) -> tuple[str, str]:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    _write_code_shape_policy(
        tmp_path,
        "[[legacy_files]]",
        'path = "src/core/hotspot.py"',
        "max_lines = 900",
        "",
        "[[legacy_files]]",
        'path = "tests/unit/test_hotspot.py"',
        "max_lines = 1500",
    )
    backlog_text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-320: Production hotspot fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `src/core/hotspot.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] hotspot marker required",
            "",
            "---",
            "",
            "### TASK-321: Test hotspot fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `tests/unit/test_hotspot.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] hotspot marker not required for tests",
            "",
            "---",
            "",
        ]
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text(backlog_text, encoding="utf-8")
    base_exec_plan = "\n".join(
        [
            "# fixture",
            "",
            "## Gate Outcomes / Waivers",
            "",
            "- Accepted design / smallest safe shape: ok",
            "- Rejected simpler alternative: ok",
            "- First integration proof: ok",
            "- Waivers: none",
            "",
        ]
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        base_exec_plan,
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-321.md").write_text(
        base_exec_plan,
        encoding="utf-8",
    )
    return backlog_text, base_exec_plan


def test_planning_hotspot_helpers_cover_empty_paths_and_invalid_markers(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    _write_code_shape_policy(
        tmp_path,
        "[[legacy_files]]",
        'path = "src/core/hotspot.py"',
        "max_lines = 900",
    )

    assert planning_module._task_file_paths_from_block("**Files**:   \n") == ()
    assert planning_module._task_file_paths_from_block(
        "**Files**: src/core/hotspot.py, docs/guide.md\n"
    ) == ("src/core/hotspot.py", "docs/guide.md")
    assert planning_module._task_file_paths_from_block(
        "**Files**: `docs/a.md`, src/core/hotspot.py\n"
    ) == ("docs/a.md", "src/core/hotspot.py")
    assert planning_module._matches_declared_task_path("   ", "src/core/hotspot.py") is False
    assert planning_module._matches_declared_task_path(
        "./src/core/hotspot.py",
        "src/core/hotspot.py",
    )
    assert (
        planning_module._task_hotspot_paths(
            tmp_path,
            task_id="TASK-999",
            backlog_text="# Backlog\n",
        )
        == ()
    )
    assert planning_module._task_hotspot_paths(
        tmp_path,
        task_id="TASK-310",
        backlog_text="\n".join(
            [
                "# Backlog",
                "",
                "### TASK-310: Mixed files fixture",
                "**Files**: `docs/a.md`, src/core/hotspot.py",
                "",
                "---",
                "",
            ]
        ),
    ) == ("src/core/hotspot.py",)
    assert planning_module._parse_hotspot_outcome_marker(None) is None
    assert planning_module._parse_hotspot_outcome_marker("not-a-real-outcome") is None
    assert planning_module._hotspot_outcome_marker_value("no hotspot marker here\n") is None
    assert (
        planning_module._hotspot_outcome_marker_value(
            "- Hotspot Outcome: keep-flat-with-rationale — fixture\n"
        )
        == "keep-flat-with-rationale — fixture"
    )
    assert planning_module.hotspot_outcome_marker_values(
        "\n".join(
            [
                "- Hotspot Outcome: reduce — first",
                "- Hotspot Outcome: follow-up-task-created — TASK-330 next",
            ]
        )
        + "\n"
    ) == ("reduce — first", "follow-up-task-created — TASK-330 next")


def test_allowlisted_hotspot_paths_include_merge_base_policy_entries(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    _write_code_shape_policy(tmp_path)

    merge_base_policy_text = "\n".join(
        [
            "[budgets]",
            "production_module_lines = 700",
            "test_module_lines = 1200",
            "production_function_lines = 100",
            "test_function_lines = 160",
            "production_member_complexity = 20",
            "test_member_complexity = 25",
            "",
            "[paths]",
            'include_roots = ["src", "tools", "tests", "scripts"]',
            'exclude_globs = ["**/__pycache__/**"]',
            "",
            "[[legacy_files]]",
            'path = "src/core/hotspot.py"',
            "max_lines = 900",
            "",
        ]
    )

    def _fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        command = args[0]
        assert isinstance(command, list)
        if command[1:3] == ["merge-base", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n")
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout=merge_base_policy_text)
        raise AssertionError(f"unexpected command: {command}")

    assert planning_module._allowlisted_production_hotspot_paths(
        tmp_path,
        git_which=lambda _name: "git",
        run=_fake_run,
    ) == ("src/core/hotspot.py",)
    assert (
        hotspots_module._merge_base_code_shape_policy_text(
            tmp_path,
            git_which=lambda _name: None,
            run=_fake_run,
        )
        is None
    )

    def _fake_run_without_merge_base(*args: object, **kwargs: object) -> SimpleNamespace:
        command = args[0]
        assert isinstance(command, list)
        if command[1:3] == ["merge-base", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="\n")
        raise AssertionError(f"unexpected command: {command}")

    assert (
        hotspots_module._merge_base_code_shape_policy_text(
            tmp_path,
            git_which=lambda _name: "git",
            run=_fake_run_without_merge_base,
        )
        is None
    )

    def _fake_run_without_show(*args: object, **kwargs: object) -> SimpleNamespace:
        command = args[0]
        assert isinstance(command, list)
        if command[1:3] == ["merge-base", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n")
        if command[1] == "show":
            return SimpleNamespace(returncode=1, stdout="")
        raise AssertionError(f"unexpected command: {command}")

    assert (
        hotspots_module._merge_base_code_shape_policy_text(
            tmp_path,
            git_which=lambda _name: "git",
            run=_fake_run_without_show,
        )
        is None
    )

    def _fake_run_missing_git(*args: object, **kwargs: object) -> SimpleNamespace:
        raise FileNotFoundError

    assert (
        hotspots_module._merge_base_code_shape_policy_text(
            tmp_path,
            git_which=lambda _name: "git",
            run=_fake_run_missing_git,
        )
        is None
    )

    assert (
        hotspots_module._allowlisted_production_hotspot_paths_from_policy_text(
            "\n".join(
                [
                    "[budgets]",
                    "production_module_lines = 700",
                    "test_module_lines = 1200",
                    "production_function_lines = 100",
                    "test_function_lines = 160",
                    "production_member_complexity = 20",
                    "test_member_complexity = 25",
                    "",
                    "[paths]",
                    'include_roots = ["src", "tools", "tests", "scripts"]',
                    'exclude_globs = ["**/__pycache__/**"]',
                    "",
                    "[[legacy_files]]",
                    'path = "src/core/non_hotspot.py"',
                    "",
                    "[[legacy_files]]",
                    'path = "tests/unit/test_hotspot.py"',
                    "max_lines = 1500",
                    "",
                ]
            )
        )
        == ()
    )


def test_planning_state_uses_archived_task_block_after_backlog_removal(tmp_path: Path) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    (tmp_path / "tasks" / "exec_plans").mkdir(parents=True, exist_ok=True)
    (tmp_path / "archive" / "closed_tasks").mkdir(parents=True, exist_ok=True)
    _write_code_shape_policy(
        tmp_path,
        "[[legacy_files]]",
        'path = "src/core/hotspot.py"',
        "max_lines = 900",
    )
    archived_task_block = "\n".join(
        [
            "### TASK-320: Archived hotspot fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "**Exec Plan**: Required (`tasks/exec_plans/README.md`)",
            "",
            "Body.",
            "",
            "**Files**: `src/core/hotspot.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] hotspot marker required",
            "",
            "---",
            "",
        ]
    )
    (tmp_path / "tasks" / "BACKLOG.md").write_text("# Backlog\n", encoding="utf-8")
    (tmp_path / "archive" / "closed_tasks" / "2026-Q2.md").write_text(
        "# Closed Tasks\n\n" + archived_task_block,
        encoding="utf-8",
    )
    (tmp_path / "tasks" / "exec_plans" / "TASK-320.md").write_text(
        "\n".join(
            [
                "# fixture",
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

    issues = docs_freshness_module._validate_planning_artifact(
        repo_root=tmp_path,
        relative_path="tasks/exec_plans/TASK-320.md",
        backlog_text="# Backlog\n",
    )

    assert {issue.rule_id for issue in issues} == {"planning_hotspot_outcome_missing"}


def test_planning_hotspot_issue_helpers_cover_hotspot_notes_and_invalid_outcomes(
    tmp_path: Path,
) -> None:
    marker_date = datetime.now(tz=UTC).date().isoformat()
    _seed_repo_layout(tmp_path, marker_date=marker_date)
    backlog_text = "\n".join(
        [
            "# Backlog",
            "",
            "### TASK-330: Fixture",
            "**Priority**: P2",
            "**Estimate**: 1h",
            "",
            "Body.",
            "",
            "**Files**: `src/core/hotspot.py`",
            "",
            "**Acceptance Criteria**:",
            "- [ ] ok",
            "",
            "---",
            "",
        ]
    )

    backlog_issues = planning_module._backlog_planning_issues(
        repo_root=tmp_path,
        backlog_text=backlog_text,
        planning_state_for_task=lambda *_args, **_kwargs: {
            "state": "applicable_backlog_only_missing_artifact",
            "hotspot_paths": ("src/core/hotspot.py",),
        },
        relative_path="tasks/BACKLOG.md",
    )
    assert "allowlisted production hotspots: src/core/hotspot.py" in backlog_issues[0].message

    assert (
        planning_module._hotspot_outcome_issues(
            relative_path="tasks/specs/330.md",
            content="- Hotspot Outcome: reduce — ok\n",
            planning_state={
                "hotspot_paths": ("src/core/hotspot.py",),
                "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
            },
        )
        == ()
    )

    invalid_outcome = planning_module._hotspot_outcome_issues(
        relative_path="tasks/exec_plans/TASK-330.md",
        content="- Hotspot Outcome: not-real\n",
        planning_state={
            "hotspot_paths": ("src/core/hotspot.py",),
            "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
        },
    )
    assert {issue.rule_id for issue in invalid_outcome} == {"planning_hotspot_outcome_invalid"}

    missing_detail = planning_module._hotspot_outcome_issues(
        relative_path="tasks/exec_plans/TASK-330.md",
        content="- Hotspot Outcome: reduce\n",
        planning_state={
            "hotspot_paths": ("src/core/hotspot.py",),
            "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
        },
    )
    assert {issue.rule_id for issue in missing_detail} == {"planning_hotspot_outcome_invalid"}

    assert (
        planning_module._hotspot_outcome_issues(
            relative_path="tasks/exec_plans/TASK-330.md",
            content="- Hotspot Outcome: follow-up-task-created — TASK-330 cleanup\n",
            planning_state={
                "hotspot_paths": ("src/core/hotspot.py",),
                "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
            },
            known_task_ids={"TASK-330"},
        )
        == ()
    )
    assert (
        planning_module._hotspot_outcome_issues(
            relative_path="tasks/exec_plans/TASK-330.md",
            content="- Hotspot Outcome: follow-up-task-created — TASK-330 cleanup\n",
            planning_state={
                "hotspot_paths": ("src/core/hotspot.py",),
                "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
            },
        )
        == ()
    )

    duplicate_outcomes = planning_module._hotspot_outcome_issues(
        relative_path="tasks/exec_plans/TASK-330.md",
        content="\n".join(
            [
                "- Hotspot Outcome: reduce — ok",
                "- Hotspot Outcome: follow-up-task-created — TASK-330 follow-up",
            ]
        )
        + "\n",
        planning_state={
            "hotspot_paths": ("src/core/hotspot.py",),
            "authoritative_artifact": "tasks/exec_plans/TASK-330.md",
        },
    )
    assert {issue.rule_id for issue in duplicate_outcomes} == {"planning_hotspot_outcome_duplicate"}
