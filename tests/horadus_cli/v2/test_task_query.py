from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.result as result_module
import tools.horadus.python.horadus_cli.task_repo as task_repo_module
import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import (
    ARCHIVED_TASK_ID,
    BACKLOG_ONLY_TASK_ID,
    EXEC_PLAN_NO_MARKER_TASK_ID,
    EXEC_PLAN_TASK_ID,
    HIGH_RISK_TASK_ID,
    LIVE_TASK_ID,
    NON_APPLICABLE_TASK_ID,
)
from tools.horadus.python.horadus_cli.app import main

pytestmark = pytest.mark.unit


def test_main_tasks_context_pack_json_output(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(["tasks", "context-pack", LIVE_TASK_ID, "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["task"]["task_id"] == LIVE_TASK_ID
    assert "suggested_validation_commands" in payload["data"]
    assert "completion_contract" in payload["data"]


def test_main_tasks_list_active_json_excludes_non_active_human_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )

    result = main(["tasks", "list-active", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["task_id"] for item in payload["data"]["human_blockers"]] == [
        "TASK-190",
        "TASK-288",
    ]
    assert [item["task_id"] for item in payload["data"]["overdue_human_blockers"]] == [
        "TASK-190",
        "TASK-288",
    ]


def test_main_tasks_list_active_honors_root_format_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )

    result = main(["--format", "json", "tasks", "list-active"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert isinstance(payload["data"]["tasks"], list)


def test_main_tasks_list_active_ignores_stale_metadata_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-189` Restrict `/health` `[REQUIRES_HUMAN]`",
                "",
                "## Human Blocker Metadata",
                "- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
                "- TASK-999 | owner=human-operator | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(task_repo_module, "current_sprint_path", lambda: sprint_path)
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )
    monkeypatch.setattr(task_repo_module, "current_sprint_path", lambda: sprint_path)
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = main(["tasks", "list-active", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["task_id"] for item in payload["data"]["human_blockers"]] == ["TASK-189"]
    assert [item["task_id"] for item in payload["data"]["overdue_human_blockers"]] == ["TASK-189"]


def test_main_tasks_list_active_text_omits_non_active_human_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 4, 8),
    )

    result = main(["tasks", "list-active"])

    assert result == 0
    output = capsys.readouterr().out
    assert "TASK-080" not in output
    assert "overdue_human_blockers=2" in output


def test_main_tasks_search_json_output_is_compact_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(["tasks", "search", "health", "--limit", "1", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["status_filter"] == "all"
    assert payload["data"]["limit"] == 1
    assert payload["data"]["include_raw"] is False
    assert len(payload["data"]["matches"]) == 1
    assert "raw_block" not in payload["data"]["matches"][0]


def test_main_tasks_search_json_output_can_filter_active_and_include_raw(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "tasks",
            "search",
            LIVE_TASK_ID,
            "--status",
            "active",
            "--include-raw",
            "--format",
            "json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    matches = payload["data"]["matches"]
    assert payload["data"]["status_filter"] == "active"
    assert payload["data"]["include_raw"] is True
    assert matches
    assert all(match["status"] == "active" for match in matches)
    assert all("raw_block" in match for match in matches)


def test_main_tasks_search_text_output_remains_compact_by_default(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(["tasks", "search", LIVE_TASK_ID, "--status", "active"])

    assert result == 0
    output = capsys.readouterr().out
    assert f"Task search: {LIVE_TASK_ID}" in output
    assert "TASK-" in output
    assert "## TASK-" not in output
    assert "Acceptance Criteria" not in output


def test_main_tasks_search_text_output_can_include_raw_blocks(
    synthetic_task_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "tasks",
            "search",
            LIVE_TASK_ID,
            "--status",
            "active",
            "--limit",
            "1",
            "--include-raw",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "## TASK-" in output
    assert "### TASK-" in output


def test_main_tasks_search_rejects_non_positive_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(["tasks", "search", "health", "--limit", "0"])

    assert result == 2
    assert "--limit must be a positive integer" in capsys.readouterr().err


def test_handle_show_returns_not_found_for_unknown_task() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-999"))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == ["TASK-999 not found in tasks/BACKLOG.md"]


def test_handle_show_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="bad-task"))

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_show_returns_task_details(synthetic_task_repo: Path) -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id=LIVE_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert result.lines[0].startswith(f"# {LIVE_TASK_ID}:")
    assert "Acceptance Criteria:" in result.lines


def test_handle_show_includes_spec_paths_when_present(synthetic_task_repo: Path) -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id=LIVE_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "Specs:" in result.lines
    assert "- tasks/specs/901-stable-live-fixture.md" in result.lines


def test_handle_show_skips_empty_optional_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-304",
        title="Coverage",
        priority="P0",
        estimate="2d",
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="active",
        sprint_lines=["- `TASK-304` Coverage"],
        spec_paths=[],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_record",
        lambda _task_id, **_kwargs: record,
    )

    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-304"))

    assert result.lines is not None
    assert "Description:" not in result.lines
    assert "Files:" not in result.lines
    assert "Acceptance Criteria:" not in result.lines
    assert "Specs:" not in result.lines


def test_handle_search_reports_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module, "search_task_records", lambda *_args, **_kwargs: [])

    result = task_commands_module.handle_search(
        argparse.Namespace(query=["missing"], status="all", limit=None, include_raw=False)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "(no matches)" in result.lines
    assert result.data is not None
    assert result.data["matches"] == []


def test_handle_context_pack_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id="bad-task"))

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_context_pack_returns_not_found_for_unknown_task() -> None:
    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id="TASK-999"))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == ["TASK-999 not found in tasks/BACKLOG.md"]


def test_handle_context_pack_requires_explicit_archive_flag_for_archived_task(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id=ARCHIVED_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == [
        f"{ARCHIVED_TASK_ID} is archived; re-run with --include-archive to inspect its history"
    ]


def test_handle_context_pack_uses_placeholder_when_task_not_in_sprint(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=BACKLOG_ONLY_TASK_ID)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "(not listed in current sprint)" in result.lines
    assert "## Spec Contract Template" in result.lines
    assert "tasks/specs/TEMPLATE.md" in result.lines
    assert "## Suggested Workflow Commands" in result.lines
    assert f"uv run --no-sync horadus tasks context-pack {BACKLOG_ONLY_TASK_ID}" in result.lines
    assert f"uv run --no-sync horadus tasks finish {BACKLOG_ONLY_TASK_ID}" in result.lines
    assert "## Suggested Validation Commands" in result.lines
    assert result.data is not None
    assert result.data["spec_template_path"] == "tasks/specs/TEMPLATE.md"
    assert (
        result.data["suggested_workflow_commands"][0] == "uv run --no-sync horadus tasks preflight"
    )


def test_handle_context_pack_surfaces_missing_planning_artifact_notice(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=BACKLOG_ONLY_TASK_ID)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "## Planning Gates" in result.lines
    assert "Applicability: required" in result.lines
    assert "State: applicable_backlog_only_missing_artifact" in result.lines
    assert any(line.startswith("Missing artifact notice:") for line in result.lines)
    assert result.data is not None
    planning = result.data["planning_gates"]
    assert planning["required"] is True
    assert planning["state"] == "applicable_backlog_only_missing_artifact"
    assert planning["authoritative_artifact_path"] is None
    assert planning["canonical_example_path"] == "tasks/specs/275-finish-review-gate-timeout.md"
    assert result.data["pre_push_review_guidance"]["recommended"] is False


def test_handle_context_pack_stays_quiet_for_non_applicable_task(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=NON_APPLICABLE_TASK_ID)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "## Planning Gates" not in result.lines
    assert result.data is not None
    assert result.data["planning_gates"]["state"] == "non_applicable"
    assert result.data["planning_gates"]["required"] is False


def test_handle_context_pack_surfaces_exec_plan_planning_homes(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id=EXEC_PLAN_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "State: applicable_with_authoritative_artifact_present" in result.lines
    assert "Authoritative planning artifact: tasks/exec_plans/TASK-905.md" in result.lines
    assert "Phase -1 gates home: tasks/exec_plans/TASK-905.md" in result.lines
    assert "Gate Outcomes / Waivers home: tasks/exec_plans/TASK-905.md" in result.lines
    assert result.data is not None
    planning = result.data["planning_gates"]
    assert planning["authoritative_artifact_path"] == "tasks/exec_plans/TASK-905.md"
    assert planning["marker_source"] == "tasks/exec_plans/TASK-905.md"
    assert planning["waiver_home_path"] == "tasks/exec_plans/TASK-905.md"


def test_handle_context_pack_omits_marker_line_when_exec_plan_requires_gates_without_marker(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=EXEC_PLAN_NO_MARKER_TASK_ID)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "## Planning Gates" in result.lines
    assert "State: applicable_with_authoritative_artifact_present" in result.lines
    assert not any(line.startswith("Marker: ") for line in result.lines)
    assert "Authoritative planning artifact: tasks/exec_plans/TASK-906.md" in result.lines
    assert result.data is not None
    planning = result.data["planning_gates"]
    assert planning["required"] is True
    assert planning["marker_value"] is None
    assert planning["authoritative_artifact_path"] == "tasks/exec_plans/TASK-906.md"


def test_handle_context_pack_propagates_archive_flag_to_suggested_commands(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=ARCHIVED_TASK_ID, include_archive=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    expected = f"uv run --no-sync horadus tasks context-pack {ARCHIVED_TASK_ID} --include-archive"
    assert expected in result.lines
    assert f"uv run --no-sync horadus tasks context-pack {ARCHIVED_TASK_ID}" not in (
        "\n".join(result.lines).replace(expected, "")
    )
    assert result.data is not None
    assert expected in result.data["suggested_workflow_commands"]


def test_handle_context_pack_keeps_archived_tasks_quiet_for_pre_push_guidance(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(
        argparse.Namespace(task_id=ARCHIVED_TASK_ID, include_archive=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "## Pre-Push Review Guidance" not in result.lines
    assert result.data is not None
    guidance = result.data["pre_push_review_guidance"]
    assert guidance["recommended"] is False
    assert guidance["commands"] == []
    assert guidance["fallback_notes"] == []
    assert guidance["batching_notes"] == []


def test_handle_context_pack_surfaces_pre_push_review_guidance_for_high_risk_task(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id=HIGH_RISK_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "## Pre-Push Review Guidance" in result.lines
    assert "Applicability: recommended" in result.lines
    assert "uv run --no-sync horadus tasks local-review --format json" in result.lines
    assert result.data is not None
    guidance = result.data["pre_push_review_guidance"]
    assert guidance["recommended"] is True
    assert guidance["commands"] == ["uv run --no-sync horadus tasks local-review --format json"]
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]
    assert "task changes canonical workflow or policy guidance" in guidance["risk_reasons"]
    assert guidance["fallback_notes"]
    assert any("timeout" in note for note in guidance["fallback_notes"])
    assert guidance["batching_notes"]


def test_pre_push_review_guidance_detects_migration_and_multi_surface_runtime_paths() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-999",
        title="Migration repair fixture",
        priority="P1",
        estimate="2h",
        description=["Exercise migration and multi-surface mutation guidance."],
        files=[
            "`alembic/versions/20260321_add_table.py`",
            "`src/api/routes/events.py`",
            "`src/storage/models.py`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task touches migration surfaces" in guidance["risk_reasons"]
    assert (
        "task spans multiple runtime surfaces: api, migrations, storage" in guidance["risk_reasons"]
    )


def test_pre_push_review_guidance_can_recommend_review_without_planning_gates() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-998",
        title="Workflow compatibility fixture",
        priority="P2",
        estimate="1h",
        description=["Exercise shared workflow tooling guidance without planning gates."],
        files=[
            "`tools/horadus/python/horadus_workflow/task_repo.py`",
            "`docs/AGENT_RUNBOOK.md`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_keeps_single_runtime_storage_work_quiet() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-993",
        title="Storage fixture",
        priority="P3",
        estimate="1h",
        description=["Exercise an ordinary single-surface runtime path without risk markers."],
        files=["`src/storage/models.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is False
    assert guidance["risk_reasons"] == []


def test_pre_push_review_guidance_treats_triage_helpers_as_shared_workflow_tooling() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-988",
        title="Triage helper fixture",
        priority="P3",
        estimate="1h",
        description=["Exercise repo-owned triage workflow guidance."],
        files=[
            "`tools/horadus/python/horadus_workflow/triage.py`",
            "`tools/horadus/python/horadus_cli/triage_commands.py`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_workflow_package_directory_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-992",
        title="Workflow package fixture",
        priority="P2",
        estimate="1h",
        description=["Exercise directory-level workflow package guidance."],
        files=["`tools/horadus/python/horadus_workflow/`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_pr_review_gate_family_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-991",
        title="Review gate fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise review-gate workflow guidance."],
        files=["`tools/horadus/python/horadus_workflow/pr_review_gate.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_repo_workflow_helpers_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-990",
        title="Workflow helper fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise repo-owned workflow helper guidance."],
        files=[
            "`tools/horadus/python/horadus_workflow/repo_workflow.py`",
            "`tools/horadus/python/horadus_workflow/docs_freshness.py`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_workflow_core_modules_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-986",
        title="Workflow core fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise workflow core module guidance."],
        files=[
            "`tools/horadus/python/horadus_workflow/review_defaults.py`",
            "`tools/horadus/python/horadus_workflow/result.py`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_cli_app_as_shared_workflow_tooling() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-981",
        title="CLI app fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise top-level CLI workflow dispatch guidance."],
        files=["`tools/horadus/python/horadus_cli/app.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_gate_helpers_as_shared_workflow_tooling() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-979",
        title="Gate helper fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise repo-owned gate helper guidance."],
        files=[
            "`tools/horadus/python/horadus_workflow/import_boundaries.py`",
            "`tools/horadus/python/horadus_workflow/code_shape.py`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow tooling" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_repo_owned_automation_surfaces_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-989",
        title="Automation surface fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise repo-owned automation workflow guidance."],
        files=["`agents/automation/`", "`ops/automations/specs/`", "`codex/rules/default.rules`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow config" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_makefile_backed_workflow_scripts_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-985",
        title="Workflow script fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise Makefile-backed workflow script guidance."],
        files=["`scripts/sync_automations.py`", "`scripts/agent_smoke_run.sh`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow config" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_integration_gate_script_as_shared_workflow_config() -> (
    None
):
    record = task_repo_module.TaskRecord(
        task_id="TASK-978",
        title="Integration gate fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise canonical integration gate guidance."],
        files=["`scripts/test_integration_docker.sh`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow config" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_spec_template_as_policy_surface() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-997",
        title="Spec template fixture",
        priority="P2",
        estimate="1h",
        description=["Exercise shared workflow policy guidance for the spec template."],
        files=["`tasks/specs/TEMPLATE.md`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes canonical workflow or policy guidance" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_skill_docs_as_policy_surface() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-984",
        title="Skill docs fixture",
        priority="P2",
        estimate="1h",
        description=["Exercise authoritative skill-doc workflow guidance."],
        files=[
            "`ops/skills/horadus-cli/SKILL.md`",
            "`ops/skills/horadus-cli/references/commands.md`",
        ],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes canonical workflow or policy guidance" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_releasing_doc_as_policy_surface() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-983",
        title="Release doc fixture",
        priority="P2",
        estimate="1h",
        description=["Exercise authoritative release/workflow guidance."],
        files=["`docs/RELEASING.md`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes canonical workflow or policy guidance" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_ingestion_as_runtime_surface() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-996",
        title="Ingestion/storage fixture",
        priority="P1",
        estimate="2h",
        description=["Exercise multi-surface runtime guidance for ingestion plus storage."],
        files=["`src/ingestion/rss_collector.py`", "`src/storage/models.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task spans multiple runtime surfaces: ingestion, storage" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_api_and_cli_as_multi_surface_runtime() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-980",
        title="API/CLI fixture",
        priority="P1",
        estimate="2h",
        description=["Exercise multi-surface runtime guidance for API plus CLI."],
        files=["`src/api/main.py`", "`src/cli.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task spans multiple runtime surfaces: api, cli" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_eval_as_runtime_surface() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-987",
        title="Processing/eval fixture",
        priority="P1",
        estimate="2h",
        description=["Exercise multi-surface runtime guidance for processing plus eval."],
        files=["`src/processing/pipeline.py`", "`src/eval/benchmark.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task spans multiple runtime surfaces: eval, processing" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_shared_workflow_config_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-995",
        title="Workflow config fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise shared workflow config guidance."],
        files=["`.github/workflows/ci.yml`", "`Makefile`", "`.pre-commit-config.yaml`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow config" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_code_shape_policy_as_shared_workflow_config() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-982",
        title="Code shape policy fixture",
        priority="P1",
        estimate="1h",
        description=["Exercise canonical code-shape workflow policy guidance."],
        files=["`config/quality/code_shape.toml`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared workflow config" in guidance["risk_reasons"]


def test_pre_push_review_guidance_treats_single_surface_math_as_high_risk() -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-994",
        title="Trend engine fixture",
        priority="P1",
        estimate="2h",
        description=["Exercise shared math guidance without multi-surface paths."],
        files=["`src/core/trend_engine.py`"],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )

    guidance = task_commands_module._pre_push_review_guidance(record)

    assert guidance["recommended"] is True
    assert "task changes shared math modules" in guidance["risk_reasons"]


def test_handle_show_requires_explicit_archive_flag_for_archived_task(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id=ARCHIVED_TASK_ID))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == [
        f"{ARCHIVED_TASK_ID} is archived; re-run with --include-archive to inspect its history"
    ]


def test_handle_show_can_resolve_archived_task_with_include_archive(
    synthetic_task_repo: Path,
) -> None:
    result = task_commands_module.handle_show(
        argparse.Namespace(task_id=ARCHIVED_TASK_ID, include_archive=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert result.lines[0].startswith(f"# {ARCHIVED_TASK_ID}:")


def test_handle_list_active_marks_due_today_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_tasks = [
        task_repo_module.ActiveTask(
            task_id="TASK-253",
            title="Coverage",
            requires_human=False,
            note=None,
            raw_line="- `TASK-253` Coverage",
        )
    ]
    blocker = task_repo_module.BlockerMetadata(
        task_id="TASK-253",
        owner="human-operator",
        last_touched="2026-03-06",
        next_action="2026-03-07",
        escalate_after_days=7,
        raw_line="- TASK-253 | owner=human-operator | last_touched=2026-03-06 | next_action=2026-03-07 | escalate_after_days=7",
        urgency=task_repo_module.BlockerUrgency(
            state="due_today",
            as_of="2026-03-07",
            days_until_next_action=0,
            is_overdue=False,
            is_due_today=True,
            days_since_last_touched=1,
            escalation_due_date="2026-03-13",
            days_until_escalation=6,
            is_escalated=False,
        ),
    )
    monkeypatch.setattr(task_commands_module, "parse_active_tasks", lambda: active_tasks)
    monkeypatch.setattr(task_commands_module, "parse_human_blockers", lambda **_kwargs: [blocker])

    result = task_commands_module.handle_list_active(argparse.Namespace())

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "[DUE TODAY]" in result.lines[1]


def test_handle_list_active_marks_overdue_blockers(monkeypatch: pytest.MonkeyPatch) -> None:
    active_tasks = [
        task_repo_module.ActiveTask(
            task_id="TASK-253",
            title="Coverage",
            requires_human=False,
            note=None,
            raw_line="- `TASK-253` Coverage",
        )
    ]
    blocker = task_repo_module.BlockerMetadata(
        task_id="TASK-253",
        owner="human-operator",
        last_touched="2026-03-01",
        next_action="2026-03-05",
        escalate_after_days=7,
        raw_line="- TASK-253 | owner=human-operator | last_touched=2026-03-01 | next_action=2026-03-05 | escalate_after_days=7",
        urgency=task_repo_module.BlockerUrgency(
            state="overdue",
            as_of="2026-03-07",
            days_until_next_action=-2,
            is_overdue=True,
            is_due_today=False,
            days_since_last_touched=6,
            escalation_due_date="2026-03-08",
            days_until_escalation=1,
            is_escalated=False,
        ),
    )
    monkeypatch.setattr(task_commands_module, "parse_active_tasks", lambda: active_tasks)
    monkeypatch.setattr(task_commands_module, "parse_human_blockers", lambda **_kwargs: [blocker])

    result = task_commands_module.handle_list_active(argparse.Namespace())

    assert result.lines is not None
    assert "[OVERDUE by 2d]" in result.lines[1]


def test_handle_list_active_omits_urgency_note_for_pending_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_tasks = [
        task_repo_module.ActiveTask(
            task_id="TASK-253",
            title="Coverage",
            requires_human=False,
            note=None,
            raw_line="- `TASK-253` Coverage",
        )
    ]
    blocker = task_repo_module.BlockerMetadata(
        task_id="TASK-253",
        owner="human-operator",
        last_touched="2026-03-06",
        next_action="2026-03-09",
        escalate_after_days=7,
        raw_line="- TASK-253 | owner=human-operator | last_touched=2026-03-06 | next_action=2026-03-09 | escalate_after_days=7",
        urgency=task_repo_module.BlockerUrgency(
            state="pending",
            as_of="2026-03-07",
            days_until_next_action=2,
            is_overdue=False,
            is_due_today=False,
            days_since_last_touched=1,
            escalation_due_date="2026-03-13",
            days_until_escalation=6,
            is_escalated=False,
        ),
    )
    monkeypatch.setattr(task_commands_module, "parse_active_tasks", lambda: active_tasks)
    monkeypatch.setattr(task_commands_module, "parse_human_blockers", lambda **_kwargs: [blocker])

    result = task_commands_module.handle_list_active(argparse.Namespace())

    assert result.lines is not None
    assert "[DUE TODAY]" not in result.lines[1]
    assert "[OVERDUE" not in result.lines[1]


def test_handle_search_covers_validation_and_raw_output_branches(
    synthetic_task_repo: Path,
) -> None:
    invalid = task_commands_module.handle_search(
        argparse.Namespace(
            query=["health"],
            status="all",
            limit=0,
            include_raw=False,
            include_archive=False,
        )
    )
    raw = task_commands_module.handle_search(
        argparse.Namespace(
            query=[LIVE_TASK_ID],
            status="active",
            limit=1,
            include_raw=True,
            include_archive=False,
        )
    )

    assert invalid.exit_code == result_module.ExitCode.VALIDATION_ERROR
    assert invalid.error_lines == ["--limit must be a positive integer"]
    assert any(line.startswith("## TASK-") for line in raw.lines or [])
