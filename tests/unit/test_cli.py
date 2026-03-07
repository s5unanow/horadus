from __future__ import annotations

import argparse
import asyncio
import json
import os
import runpy
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

import src.cli as cli_module
import src.horadus_cli.app as cli_app_module
import src.horadus_cli.result as result_module
import src.horadus_cli.task_commands as task_commands_module
import src.horadus_cli.task_repo as task_repo_module
from src.cli import _build_parser, _change_arrow, _format_trend_status_lines
from src.core.calibration_dashboard import TrendMovement

pytestmark = pytest.mark.unit


def test_change_arrow_maps_signs() -> None:
    assert _change_arrow(0.1) == "^"
    assert _change_arrow(-0.1) == "v"
    assert _change_arrow(0.0) == "="


def test_format_trend_status_lines_includes_probability_change_and_movers() -> None:
    movement = TrendMovement(
        trend_id=uuid4(),
        trend_name="EU-Russia",
        current_probability=0.123,
        weekly_change=0.021,
        risk_level="guarded",
        top_movers_7d=["military_movement", "diplomatic_breakdown"],
        movement_chart="._-~=+",
    )

    lines = _format_trend_status_lines(movement)

    assert len(lines) == 2
    assert "EU-Russia" in lines[0]
    assert "12.3%" in lines[0]
    assert "^ +2.1% this week" in lines[0]
    assert "[._-~=+]" in lines[0]
    assert "military_movement, diplomatic_breakdown" in lines[1]


def test_build_parser_accepts_dashboard_export_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["dashboard", "export", "--output-dir", "artifacts/dashboard", "--limit", "5"]
    )

    assert args.command == "dashboard"
    assert args.dashboard_command == "export"
    assert args.output_dir == "artifacts/dashboard"
    assert args.limit == 5


def test_build_parser_accepts_task_search_filters() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "search",
            "health",
            "--status",
            "active",
            "--limit",
            "2",
            "--include-raw",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "search"
    assert args.query == ["health"]
    assert args.status == "active"
    assert args.limit == 2
    assert args.include_raw is True


def test_build_parser_accepts_eval_benchmark_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "benchmark",
            "--gold-set",
            "ai/eval/gold_set.jsonl",
            "--output-dir",
            "ai/eval/results",
            "--trend-config-dir",
            "config/trends",
            "--max-items",
            "100",
            "--config",
            "baseline",
            "--require-human-verified",
            "--dispatch-mode",
            "batch",
            "--request-priority",
            "flex",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "benchmark"
    assert args.gold_set == "ai/eval/gold_set.jsonl"
    assert args.output_dir == "ai/eval/results"
    assert args.trend_config_dir == "config/trends"
    assert args.max_items == 100
    assert args.config == ["baseline"]
    assert args.require_human_verified is True
    assert args.dispatch_mode == "batch"
    assert args.request_priority == "flex"


def test_build_parser_accepts_eval_audit_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "audit",
            "--gold-set",
            "ai/eval/gold_set.jsonl",
            "--output-dir",
            "ai/eval/results",
            "--max-items",
            "200",
            "--fail-on-warnings",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "audit"
    assert args.gold_set == "ai/eval/gold_set.jsonl"
    assert args.output_dir == "ai/eval/results"
    assert args.max_items == 200
    assert args.fail_on_warnings is True


def test_build_parser_accepts_eval_validate_taxonomy_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "validate-taxonomy",
            "--trend-config-dir",
            "config/trends",
            "--gold-set",
            "ai/eval/gold_set.jsonl",
            "--output-dir",
            "ai/eval/results",
            "--max-items",
            "120",
            "--tier1-trend-mode",
            "subset",
            "--signal-type-mode",
            "warn",
            "--unknown-trend-mode",
            "warn",
            "--fail-on-warnings",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "validate-taxonomy"
    assert args.trend_config_dir == "config/trends"
    assert args.gold_set == "ai/eval/gold_set.jsonl"
    assert args.output_dir == "ai/eval/results"
    assert args.max_items == 120
    assert args.tier1_trend_mode == "subset"
    assert args.signal_type_mode == "warn"
    assert args.unknown_trend_mode == "warn"
    assert args.fail_on_warnings is True


def test_build_parser_accepts_eval_replay_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "replay",
            "--output-dir",
            "ai/eval/results",
            "--champion-config",
            "stable",
            "--challenger-config",
            "fast_lower_threshold",
            "--trend-id",
            "0f8fad5b-d9cb-469f-a165-70867728950e",
            "--start-date",
            "2026-01-01T00:00:00Z",
            "--end-date",
            "2026-02-01T00:00:00Z",
            "--days",
            "30",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "replay"
    assert args.output_dir == "ai/eval/results"
    assert args.champion_config == "stable"
    assert args.challenger_config == "fast_lower_threshold"
    assert args.trend_id == "0f8fad5b-d9cb-469f-a165-70867728950e"
    assert args.start_date == "2026-01-01T00:00:00Z"
    assert args.end_date == "2026-02-01T00:00:00Z"
    assert args.days == 30


def test_build_parser_accepts_eval_vector_benchmark_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "vector-benchmark",
            "--output-dir",
            "ai/eval/results",
            "--database-url",
            "postgresql+asyncpg://localhost:5432/geoint_test",
            "--dataset-size",
            "2000",
            "--query-count",
            "150",
            "--dimensions",
            "64",
            "--top-k",
            "12",
            "--similarity-threshold",
            "0.9",
            "--seed",
            "7",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "vector-benchmark"
    assert args.output_dir == "ai/eval/results"
    assert args.database_url == "postgresql+asyncpg://localhost:5432/geoint_test"
    assert args.dataset_size == 2000
    assert args.query_count == 150
    assert args.dimensions == 64
    assert args.top_k == 12
    assert args.similarity_threshold == pytest.approx(0.9)
    assert args.seed == 7


def test_build_parser_accepts_eval_embedding_lineage_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "embedding-lineage",
            "--target-model",
            "text-embedding-3-large",
            "--fail-on-mixed",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "embedding-lineage"
    assert args.target_model == "text-embedding-3-large"
    assert args.fail_on_mixed is True


def test_build_parser_accepts_eval_source_freshness_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "eval",
            "source-freshness",
            "--stale-multiplier",
            "1.5",
            "--fail-on-stale",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "source-freshness"
    assert args.stale_multiplier == pytest.approx(1.5)
    assert args.fail_on_stale is True


def test_build_parser_accepts_agent_smoke_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "agent",
            "smoke",
            "--base-url",
            "http://127.0.0.1:8000",
            "--timeout-seconds",
            "2.5",
            "--api-key",
            "test-key",
        ]
    )

    assert args.command == "agent"
    assert args.agent_command == "smoke"
    assert args.base_url == "http://127.0.0.1:8000"
    assert args.timeout_seconds == pytest.approx(2.5)
    assert args.api_key == "test-key"  # pragma: allowlist secret


def test_build_parser_accepts_pipeline_dry_run_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "dry-run",
            "--fixture-path",
            "ai/eval/fixtures/pipeline_dry_run_items.jsonl",
            "--trend-config-dir",
            "config/trends",
            "--output-path",
            "artifacts/agent/pipeline-dry-run-output.json",
        ]
    )

    assert args.command == "pipeline"
    assert args.pipeline_command == "dry-run"
    assert args.fixture_path.endswith("pipeline_dry_run_items.jsonl")
    assert args.trend_config_dir == "config/trends"
    assert args.output_path.endswith("pipeline-dry-run-output.json")


def test_build_parser_accepts_doctor_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["doctor", "--timeout-seconds", "3.5"])

    assert args.command == "doctor"
    assert args.timeout_seconds == pytest.approx(3.5)


def test_build_parser_accepts_tasks_start_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "start",
            "TASK-216",
            "--name",
            "agent-facing-cli",
            "--dry-run",
            "--format",
            "json",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "start"
    assert args.task_id == "TASK-216"
    assert args.name == "agent-facing-cli"
    assert args.dry_run is True
    assert args.output_format == "json"


def test_build_parser_preserves_root_flags_for_tasks_start() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--format",
            "json",
            "--dry-run",
            "tasks",
            "start",
            "TASK-216",
            "--name",
            "agent-facing-cli",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "start"
    assert args.task_id == "TASK-216"
    assert args.name == "agent-facing-cli"
    assert args.dry_run is True
    assert args.output_format == "json"


def test_build_parser_accepts_triage_collect_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "triage",
            "collect",
            "--keyword",
            "agent",
            "--path",
            "src/cli.py",
            "--proposal-id",
            "PROPOSAL-2026-03-02-agents-cross-role-promotion-dedupe",
            "--lookback-days",
            "7",
            "--format",
            "json",
        ]
    )

    assert args.command == "triage"
    assert args.triage_command == "collect"
    assert args.keyword == ["agent"]
    assert args.path == ["src/cli.py"]
    assert args.proposal_id == ["PROPOSAL-2026-03-02-agents-cross-role-promotion-dedupe"]
    assert args.lookback_days == 7
    assert args.output_format == "json"


def test_build_parser_preserves_root_flags_for_legacy_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--format", "json", "--dry-run", "pipeline", "dry-run"])

    assert args.command == "pipeline"
    assert args.pipeline_command == "dry-run"
    assert args.dry_run is True
    assert args.output_format == "json"


def test_run_agent_smoke_passes_when_server_enforces_auth_and_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 401,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        _ = headers
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = timeout_seconds
        _ = headers
        assert url == "http://127.0.0.1:8000/openapi.json"
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(cli_module, "_http_get", fake_http_get)
    monkeypatch.setattr(cli_module, "_http_get_json", fake_http_get_json)

    result = cli_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 0


def test_run_agent_smoke_fails_when_api_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 403,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        assert headers == {"X-API-Key": "invalid-token"} or headers is None
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = timeout_seconds
        _ = headers
        assert url == "http://127.0.0.1:8000/openapi.json"
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(cli_module, "_http_get", fake_http_get)
    monkeypatch.setattr(cli_module, "_http_get_json", fake_http_get_json)

    result = cli_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key="invalid-token",  # pragma: allowlist secret
    )

    assert result == 2


def test_run_agent_smoke_passes_when_auth_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 200,
    }

    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = timeout_seconds
        _ = headers
        return statuses[url]

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = url
        _ = timeout_seconds
        _ = headers
        return (200, {"openapi": "3.1.0"})

    monkeypatch.setattr(cli_module, "_http_get", fake_http_get)
    monkeypatch.setattr(cli_module, "_http_get_json", fake_http_get_json)

    result = cli_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 0


def test_run_agent_smoke_fails_when_server_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_get(url: str, *, timeout_seconds: float, headers=None) -> int:
        _ = url
        _ = timeout_seconds
        _ = headers
        return 0

    def fake_http_get_json(
        url: str,
        *,
        timeout_seconds: float,
        headers=None,
    ) -> tuple[int, dict[str, object] | None]:
        _ = url
        _ = timeout_seconds
        _ = headers
        return (0, None)

    monkeypatch.setattr(cli_module, "_http_get", fake_http_get)
    monkeypatch.setattr(cli_module, "_http_get_json", fake_http_get_json)

    result = cli_module._run_agent_smoke(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=5.0,
        api_key=None,
    )

    assert result == 2


def test_run_doctor_fails_when_required_hooks_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    os.chmod(hooks_dir / "pre-commit", 0o755)

    result = cli_module._run_doctor(timeout_seconds=0.2)

    assert result == 2


def test_run_doctor_passes_when_required_hooks_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_module.settings, "DATABASE_URL", "")
    monkeypatch.setattr(cli_module.settings, "REDIS_URL", "")
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        path = hooks_dir / hook_name
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        os.chmod(path, 0o755)

    result = cli_module._run_doctor(timeout_seconds=0.2)

    assert result == 0


def test_doctor_check_database_skips_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module.settings, "DATABASE_URL", "")
    status, message = asyncio.run(cli_module._doctor_check_database(0.2))
    assert status == "SKIP"
    assert "DATABASE_URL" in message


def test_doctor_check_redis_skips_when_redis_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module.settings, "REDIS_URL", "")
    status, message = asyncio.run(cli_module._doctor_check_redis(0.2))
    assert status == "SKIP"
    assert "REDIS_URL" in message


def test_run_doctor_returns_failure_on_safety_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(cli_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(cli_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(cli_module.settings, "AGENT_ALLOW_NON_LOOPBACK", False)
    monkeypatch.setattr(cli_module.settings, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(cli_module.settings, "API_AUTH_ENABLED", True)

    async def fake_doctor_check_database(_timeout_seconds: float) -> tuple[str, str]:
        return ("PASS", "ok")

    async def fake_doctor_check_redis(_timeout_seconds: float) -> tuple[str, str]:
        return ("PASS", "ok")

    monkeypatch.setattr(cli_module, "_doctor_check_database", fake_doctor_check_database)
    monkeypatch.setattr(cli_module, "_doctor_check_redis", fake_doctor_check_redis)

    result = cli_module._run_doctor(timeout_seconds=0.2)
    assert result == 2


def test_main_tasks_context_pack_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli_module.main(["tasks", "context-pack", "TASK-164", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["task"]["task_id"] == "TASK-164"
    assert "suggested_validation_commands" in payload["data"]


def test_parse_human_blockers_derives_urgency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    blockers = task_repo_module.parse_human_blockers()

    assert blockers
    urgency = blockers[0].urgency
    assert urgency is not None
    assert urgency.as_of == "2026-03-06"
    assert urgency.state == "overdue"
    assert urgency.days_until_next_action == -1
    assert urgency.is_overdue is True
    assert urgency.days_since_last_touched == 3


def test_parse_human_blockers_can_filter_to_active_task_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-189` Active blocker `[REQUIRES_HUMAN]`",
                "",
                "## Human Blocker Metadata",
                "- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7",
                "- TASK-999 | owner=human-operator | last_touched=2026-03-01 | next_action=2026-03-02 | escalate_after_days=7",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path, task_ids={"TASK-189"})

    assert [blocker.task_id for blocker in blockers] == ["TASK-189"]


def test_main_tasks_list_active_json_includes_blocker_urgency(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = cli_module.main(["tasks", "list-active", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    blocker = payload["data"]["human_blockers"][0]
    assert blocker["urgency"]["state"] == "overdue"
    assert blocker["urgency"]["days_until_next_action"] == -1
    assert payload["data"]["overdue_human_blockers"]


def test_main_tasks_list_active_honors_root_format_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = cli_module.main(["--format", "json", "tasks", "list-active"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["tasks"]


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

    result = cli_module.main(["tasks", "list-active", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["task_id"] for item in payload["data"]["human_blockers"]] == ["TASK-189"]
    assert [item["task_id"] for item in payload["data"]["overdue_human_blockers"]] == ["TASK-189"]


def test_main_tasks_list_active_text_highlights_overdue_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = cli_module.main(["tasks", "list-active"])

    assert result == 0
    output = capsys.readouterr().out
    assert "[OVERDUE by 1d]" in output
    assert "overdue_human_blockers=3 (TASK-080, TASK-189, TASK-190)" in output


def test_main_tasks_search_json_output_is_compact_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main(["tasks", "search", "health", "--limit", "1", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["status_filter"] == "all"
    assert payload["data"]["limit"] == 1
    assert payload["data"]["include_raw"] is False
    assert len(payload["data"]["matches"]) == 1
    assert "raw_block" not in payload["data"]["matches"][0]


def test_main_tasks_search_json_output_can_filter_active_and_include_raw(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main(
        [
            "tasks",
            "search",
            "health",
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
    assert "TASK-189" in {match["task_id"] for match in matches}
    assert all(match["status"] == "active" for match in matches)
    assert all("raw_block" in match for match in matches)


def test_main_tasks_search_text_output_remains_compact_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main(["tasks", "search", "health", "--status", "active"])

    assert result == 0
    output = capsys.readouterr().out
    assert "Task search: health" in output
    assert "TASK-189" in output
    assert "## TASK-189" not in output
    assert "Acceptance Criteria" not in output


def test_main_tasks_search_text_output_can_include_raw_blocks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main(
        ["tasks", "search", "health", "--status", "active", "--limit", "1", "--include-raw"]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "## TASK-189" in output
    assert (
        "### TASK-189: Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]"
        in output
    )


def test_main_tasks_search_rejects_non_positive_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main(["tasks", "search", "health", "--limit", "0"])

    assert result == 2
    assert "--limit must be a positive integer" in capsys.readouterr().err


def test_main_tasks_start_honors_root_dry_run_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_start_task_data(
        task_input: str,
        raw_name: str,
        *,
        dry_run: bool,
    ) -> tuple[int, dict[str, object], list[str]]:
        captured["task_input"] = task_input
        captured["raw_name"] = raw_name
        captured["dry_run"] = dry_run
        return (
            0,
            {
                "task_id": task_input,
                "branch_name": "codex/task-216-agent-facing-cli",
                "dry_run": dry_run,
            },
            ["ok"],
        )

    monkeypatch.setattr(task_commands_module, "start_task_data", fake_start_task_data)

    result = cli_module.main(
        [
            "--format",
            "json",
            "--dry-run",
            "tasks",
            "start",
            "TASK-216",
            "--name",
            "agent-facing-cli",
        ]
    )

    assert result == 0
    assert captured == {
        "task_input": "TASK-216",
        "raw_name": "agent-facing-cli",
        "dry_run": True,
    }
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["dry_run"] is True


def _completed(
    args: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_horadus_app_main_returns_1_without_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli_module.main([])

    assert result == 1
    assert "usage:" in capsys.readouterr().out


def test_cli_script_entrypoint_exits_with_main_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app_module, "main", lambda: 7)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(cli_module.__file__)), run_name="__main__")

    assert exc_info.value.code == 7


def test_emit_result_serializes_errors_in_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = task_commands_module.CommandResult(
        exit_code=task_commands_module.ExitCode.VALIDATION_ERROR,
        data={"ok": False},
        error_lines=["bad input"],
    )

    result = result_module.emit_result(payload, "json")

    assert result == task_commands_module.ExitCode.VALIDATION_ERROR
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert output["errors"] == ["bad input"]


def test_json_default_serializes_dates_paths_and_dataclasses(tmp_path: Path) -> None:
    serialized_date = result_module._json_default(task_repo_module.date(2026, 3, 7))
    serialized_path = result_module._json_default(tmp_path / "artifact.json")
    serialized_dataclass = result_module._json_default(
        result_module.CommandResult(lines=["ok"], data={"x": 1})
    )

    assert serialized_date == "2026-03-07"
    assert str(tmp_path / "artifact.json") == serialized_path
    assert serialized_dataclass["lines"] == ["ok"]
    assert serialized_dataclass["data"] == {"x": 1}


def test_json_default_rejects_unknown_types() -> None:
    with pytest.raises(TypeError):
        result_module._json_default(object())


def test_emit_result_returns_plain_int_unchanged() -> None:
    assert result_module.emit_result(7, "json") == 7


def test_emit_result_prints_text_lines_and_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = result_module.CommandResult(
        exit_code=result_module.ExitCode.NOT_FOUND,
        lines=["stdout line"],
        error_lines=["stderr line"],
    )

    exit_code = result_module.emit_result(result, "text")

    captured = capsys.readouterr()
    assert exit_code == result_module.ExitCode.NOT_FOUND
    assert "stdout line" in captured.out
    assert "stderr line" in captured.err


def test_run_command_and_shell_execute_locally() -> None:
    command_result = task_commands_module._run_command(["/bin/echo", "hi"])
    shell_result = task_commands_module._run_shell("printf shell-ok")

    assert command_result.stdout.strip() == "hi"
    assert shell_result.stdout == "shell-ok"


def test_ensure_required_hooks_reports_missing_hooks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text("#!/bin/sh\n", encoding="utf-8")
    pre_commit.chmod(0o755)

    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    hooks_ok, missing = task_commands_module._ensure_required_hooks()

    assert hooks_ok is False
    assert missing == ["pre-push", "commit-msg"]


def test_open_task_prs_filters_non_task_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "list"],
            stdout=json.dumps(
                [
                    {
                        "number": 12,
                        "headRefName": "codex/task-253-coverage-100",
                        "url": "https://x/12",
                    },
                    {"number": 13, "headRefName": "feature/misc", "url": "https://x/13"},
                ]
            ),
        ),
    )

    ok, payload = task_commands_module._open_task_prs()

    assert ok is True
    assert payload == ["#12 codex/task-253-coverage-100 https://x/12"]


def test_open_task_prs_reports_gh_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], returncode=1, stderr="boom"),
    )

    ok, payload = task_commands_module._open_task_prs()

    assert ok is False
    assert payload == "boom"


def test_task_preflight_data_skips_when_env_override_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_TASK_SEQUENCE_GUARD", "1")

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data == {"skipped": True}
    assert "skipped" in lines[0]


def test_task_preflight_data_fails_without_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKIP_TASK_SEQUENCE_GUARD", raising=False)
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: None)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert "GitHub CLI" in lines[-1]


def test_task_preflight_data_fails_when_required_hooks_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_required_hooks",
        lambda: (False, ["pre-commit", "pre-push"]),
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_hooks"] == ["pre-commit", "pre-push"]
    assert "pre-commit, pre-push" in lines[-1]


def test_task_preflight_data_fails_when_not_on_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["git", "rev-parse"], stdout="codex/task-253-coverage-100\n"
        ),
    )

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["current_branch"] == "codex/task-253-coverage-100"
    assert "must start tasks from 'main'" in lines[-1]


def test_task_preflight_data_fails_for_dirty_worktree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=" M tasks/BACKLOG.md\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["working_tree_clean"] is False
    assert "Working tree must be clean" in lines[-1]


def test_task_preflight_data_fails_when_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"], returncode=1, stderr="fetch failed"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["fetch_error"] == "fetch failed"
    assert lines[-1] == "fetch failed"


def test_task_preflight_data_fails_when_main_is_not_synced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="def\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["local_main_sha"] == "abc"
    assert data["remote_main_sha"] == "def"
    assert "not synced to origin/main" in lines[-1]


def test_task_preflight_data_fails_when_open_pr_query_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (False, "gh failed"))
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["open_pr_query_error"] == "gh failed"
    assert "Unable to query open PRs" in lines[-1]


def test_task_preflight_data_reports_open_task_prs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(
        task_commands_module, "_open_task_prs", lambda: (True, ["#12 codex/task-253-x"])
    )

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["open_task_prs"] == ["#12 codex/task-253-x"]
    assert "Open non-merged task PR" in "\n".join(lines)


def test_task_preflight_data_passes_when_open_pr_guard_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_OPEN_TASK_PRS", "1")
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="abc\n"),
            _completed(["git", "rev-parse"], stdout="abc\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.task_preflight_data()

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["working_tree_clean"] is True
    assert "passed" in lines[0]


def test_preflight_result_wraps_preflight_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {"ok": True}, ["passed"]),
    )

    result = task_commands_module._preflight_result()

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"ok": True}
    assert result.lines == ["passed"]


def test_eligibility_data_reports_missing_sprint_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", "/tmp/definitely-missing-sprint.md")

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert "Missing sprint file" in lines[0]
    assert data["sprint_file"].endswith("definitely-missing-sprint.md")


def test_eligibility_data_reports_invalid_active_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text("# Current Sprint\n", encoding="utf-8")
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["sprint_file"] == str(sprint_path)
    assert "Unable to locate Active Tasks section" in lines[0]


def test_eligibility_data_requires_task_to_be_in_active_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-252` Something\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["task_id"] == "TASK-253"
    assert "not listed in Active Tasks" in lines[0]


def test_eligibility_data_reports_requires_human_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-189` Restricted health [REQUIRES_HUMAN]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-189")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["requires_human"] is True
    assert "[REQUIRES_HUMAN]" in lines[0]


def test_eligibility_data_respects_preflight_override_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.setenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", "printf fail && exit 1")

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight_cmd"] == "printf fail && exit 1"
    assert "preflight failed" in lines[0]


def test_eligibility_data_succeeds_for_active_non_human_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.delenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", raising=False)
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {"ok": True}, ["passed"]),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["requires_human"] is False
    assert lines == ["Agent task eligibility passed: TASK-253"]


def test_start_task_data_rejects_existing_local_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=0) if "show-ref" in args else _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert "already exists locally" in lines[0]


def test_start_task_data_rejects_existing_remote_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args:
            return _completed(args, returncode=1)
        if "ls-remote" in args:
            return _completed(args, returncode=0)
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert "already exists on origin" in lines[0]


def test_start_task_data_dry_run_reports_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=1)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=True
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert "would create task branch codex/task-253-coverage-100" in lines[-1]


def test_start_task_data_reports_git_switch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args or "ls-remote" in args:
            return _completed(args, returncode=1)
        if args[:2] == ["git", "switch"]:
            return _completed(args, returncode=1, stderr="switch failed")
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "switch failed"
    assert lines == ["switch failed"]


def test_start_task_data_switches_to_new_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (task_commands_module.ExitCode.OK, {}, ["ok"]),
    )

    def fake_run_command(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "show-ref" in args or "ls-remote" in args:
            return _completed(args, returncode=1)
        if args[:2] == ["git", "switch"]:
            return _completed(args)
        return _completed(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert "Created task branch: codex/task-253-coverage-100" in lines[-1]


def test_handle_show_returns_not_found_for_unknown_task() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-999"))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == ["TASK-999 not found in tasks/BACKLOG.md"]


def test_handle_show_returns_task_details() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-253"))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert result.lines[0].startswith("# TASK-253:")
    assert "Acceptance Criteria:" in result.lines


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


def test_handle_context_pack_uses_placeholder_when_task_not_in_sprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = task_repo_module.task_record("TASK-253")
    assert record is not None
    monkeypatch.setattr(task_commands_module, "task_record", lambda _task_id: record)

    result = task_commands_module.handle_context_pack(argparse.Namespace(task_id="TASK-253"))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert "(not listed in current sprint)" not in result.lines
    assert "## Suggested Validation Commands" in result.lines


def test_handle_preflight_returns_wrapped_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_preflight_result",
        lambda: task_commands_module.CommandResult(lines=["preflight ok"]),
    )

    result = task_commands_module.handle_preflight(argparse.Namespace())

    assert result.lines == ["preflight ok"]


def test_handle_eligibility_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_eligibility(argparse.Namespace(task_id="bad-task"))

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_eligibility_wraps_eligibility_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (task_commands_module.ExitCode.OK, {"task_id": "TASK-253"}, ["eligible"]),
    )

    result = task_commands_module.handle_eligibility(argparse.Namespace(task_id="TASK-253"))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {"task_id": "TASK-253"}
    assert result.lines == ["eligible"]


def test_handle_start_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_start(
        argparse.Namespace(task_id="bad-task", name="coverage")
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


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


def test_main_triage_collect_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli_module.main(
        [
            "triage",
            "collect",
            "--keyword",
            "agent",
            "--lookback-days",
            "14",
            "--format",
            "json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["data"]["lookback_days"] == 14
    assert "current_sprint" in payload["data"]
    assert "keyword_hits" in payload["data"]["searches"]


def test_main_triage_collect_includes_overdue_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = cli_module.main(["triage", "collect", "--lookback-days", "14", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    overdue = payload["data"]["current_sprint"]["overdue_human_blockers"]
    assert {item["task_id"] for item in overdue} == {"TASK-080", "TASK-189", "TASK-190"}
    assert overdue[0]["urgency"]["state"] == "overdue"


def test_main_triage_collect_ignores_stale_metadata_rows(
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

    result = cli_module.main(["triage", "collect", "--lookback-days", "14", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    blockers = payload["data"]["current_sprint"]["human_blockers"]
    overdue = payload["data"]["current_sprint"]["overdue_human_blockers"]
    assert [item["task_id"] for item in blockers] == ["TASK-189"]
    assert [item["task_id"] for item in overdue] == ["TASK-189"]


def test_main_triage_collect_text_highlights_overdue_blockers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_repo_module,
        "current_date",
        lambda: task_repo_module.date(2026, 3, 6),
    )

    result = cli_module.main(["triage", "collect", "--lookback-days", "14"])

    assert result == 0
    output = capsys.readouterr().out
    assert "- overdue_human_blockers=3" in output
    assert "- overdue_tasks=TASK-080, TASK-189, TASK-190" in output
