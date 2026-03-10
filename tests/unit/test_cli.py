from __future__ import annotations

import argparse
import asyncio
import json
import os
import runpy
import shutil
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import src.cli as cli_module
import src.horadus_cli.app as cli_app_module
import src.horadus_cli.result as result_module
import src.horadus_cli.task_commands as task_commands_module
import src.horadus_cli.task_repo as task_repo_module
import src.horadus_cli.triage_commands as triage_commands_module
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


def test_build_parser_accepts_task_finish_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["tasks", "finish", "TASK-258"])

    assert args.command == "tasks"
    assert args.tasks_command == "finish"
    assert args.task_id == "TASK-258"


def test_build_parser_accepts_task_lifecycle_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["tasks", "lifecycle", "TASK-259", "--strict"])

    assert args.command == "tasks"
    assert args.tasks_command == "lifecycle"
    assert args.task_id == "TASK-259"
    assert args.strict is True


def test_build_parser_accepts_task_local_gate_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["tasks", "local-gate", "--full"])

    assert args.command == "tasks"
    assert args.tasks_command == "local-gate"
    assert args.full is True


def test_build_parser_accepts_task_safe_start_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["tasks", "safe-start", "TASK-117", "--name", "short-name", "--dry-run"]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "safe-start"
    assert args.task_id == "TASK-117"
    assert args.name == "short-name"
    assert args.dry_run is True


def test_build_parser_accepts_task_record_friction_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "record-friction",
            "TASK-117",
            "--command-attempted",
            "uv run --no-sync horadus tasks finish TASK-117",
            "--fallback-used",
            "gh pr merge 123 --squash",
            "--friction-type",
            "forced_fallback",
            "--note",
            "Needed manual merge path.",
            "--suggested-improvement",
            "Teach finish about this blocker.",
            "--dry-run",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "record-friction"
    assert args.task_id == "TASK-117"
    assert args.friction_type == "forced_fallback"
    assert args.dry_run is True


def test_build_parser_accepts_task_summarize_friction_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "summarize-friction",
            "--date",
            "2026-03-08",
            "--output",
            "artifacts/agent/horadus-cli-feedback/daily/2026-03-08.md",
            "--dry-run",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "summarize-friction"
    assert args.date == "2026-03-08"
    assert args.output == "artifacts/agent/horadus-cli-feedback/daily/2026-03-08.md"
    assert args.dry_run is True


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


def test_task_repo_helper_functions_cover_validation_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text("# Current Sprint\n", encoding="utf-8")

    assert task_repo_module.normalize_task_id("253") == "TASK-253"
    assert task_repo_module.slugify_name(" Coverage Plan ") == "coverage-plan"
    with pytest.raises(ValueError, match="Invalid branch suffix"):
        task_repo_module.slugify_name("   ")
    with pytest.raises(ValueError, match="Unable to locate Active Tasks"):
        task_repo_module.active_section_text(sprint_path)
    assert task_repo_module.human_blocker_section_text(sprint_path) == ""

    urgency = task_repo_module.blocker_urgency(
        last_touched="bad-date",
        next_action="2026-03-06",
        escalate_after_days=0,
        as_of=task_repo_module.date(2026, 3, 6),
    )
    assert urgency.state == "due_today"
    assert urgency.days_since_last_touched is None


def test_parse_human_blockers_skips_malformed_rows(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "## Active Tasks",
                "- `TASK-253` Coverage task",
                "",
                "## Human Blocker Metadata",
                "- malformed",
                "- TASK-253 | owner=human | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=bad",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert len(blockers) == 1
    assert blockers[0].task_id == "TASK-253"
    assert blockers[0].escalate_after_days == 0


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


def _task_snapshot(
    *,
    current_branch: str = "codex/task-259-done-state-verifier",
    branch_name: str | None = "codex/task-259-done-state-verifier",
    remote_branch_exists: bool = False,
    pr: task_commands_module.TaskPullRequest | None = None,
    working_tree_clean: bool = True,
    local_main_synced: bool | None = None,
    merge_commit_on_main: bool | None = None,
) -> task_commands_module.TaskLifecycleSnapshot:
    local_main_sha = None
    remote_main_sha = None
    if local_main_synced is not None:
        local_main_sha = "main-sha"
        remote_main_sha = "main-sha" if local_main_synced else "remote-sha"

    merge_commit_available_locally = None
    if pr is not None and pr.merge_commit_oid is not None:
        merge_commit_available_locally = merge_commit_on_main

    return task_commands_module.TaskLifecycleSnapshot(
        task_id="TASK-259",
        current_branch=current_branch,
        branch_name=branch_name,
        local_branch_names=[branch_name] if branch_name else [],
        remote_branch_names=[branch_name] if remote_branch_exists and branch_name else [],
        remote_branch_exists=remote_branch_exists,
        working_tree_clean=working_tree_clean,
        pr=pr,
        local_main_sha=local_main_sha,
        remote_main_sha=remote_main_sha,
        local_main_synced=local_main_synced,
        merge_commit_available_locally=merge_commit_available_locally,
        merge_commit_on_main=merge_commit_on_main,
        lifecycle_state="",
        strict_complete=False,
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


def test_emit_result_json_omits_optional_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = result_module.emit_result(result_module.CommandResult(), "json")

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"exit_code": 0, "status": "ok"}


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


def test_run_command_raises_wrapped_timeout_error_with_captured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            ["git", "status"],
            5,
            output="partial-out",
            stderr="partial-err",
        )

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout)

    with pytest.raises(task_commands_module.CommandTimeoutError) as excinfo:
        task_commands_module._run_command(["git", "status"], timeout_seconds=5)

    assert excinfo.value.stdout == "partial-out"
    assert excinfo.value.stderr == "partial-err"
    assert excinfo.value.output_lines() == ["partial-out", "partial-err"]


def test_run_command_requires_explicit_timeout_value_when_subprocess_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["git", "status"], 5)

    monkeypatch.setattr(task_commands_module.subprocess, "run", raise_timeout)

    with pytest.raises(
        RuntimeError,
        match="subprocess timed out without an explicit timeout value",
    ):
        task_commands_module._run_command(["git", "status"])


def test_task_command_helper_parsers_cover_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    assert task_commands_module._result_message(_completed(["x"]), "fallback") == "fallback"
    assert task_commands_module._output_lines(
        _completed(["x"], stdout=" one \n", stderr=" two ")
    ) == ["one", "two"]
    assert task_commands_module._parse_report_date(None) == datetime.now(tz=UTC).date()
    assert task_commands_module._parse_recorded_at("2026-03-08T10:00:00").tzinfo == UTC
    assert task_commands_module._parse_recorded_at("2026-03-08T10:00:00Z").tzinfo == UTC

    outside = tmp_path.parent / "outside.txt"
    assert task_commands_module._relative_display_path(outside) == str(outside)


def test_task_command_branch_and_rollup_helpers_cover_edge_cases() -> None:
    assert task_commands_module._parse_git_branch_lines("  main\n\n* codex/task-257-x\n") == [
        "main",
        "codex/task-257-x",
    ]
    assert task_commands_module._parse_remote_branch_lines(
        "bad-line\nabc refs/heads/codex/task-257-x\nabc refs/tags/v1\n"
    ) == ["codex/task-257-x"]
    assert task_commands_module._check_rollup_state(None) == "none"
    assert task_commands_module._check_rollup_state([{"status": "IN_PROGRESS"}]) == "pending"
    assert (
        task_commands_module._check_rollup_state([{"status": "COMPLETED", "conclusion": "FAILURE"}])
        == "fail"
    )
    assert (
        task_commands_module._check_rollup_state(
            ["not-a-dict", {"status": "COMPLETED", "conclusion": ""}]
        )
        == "pending"
    )
    assert (
        task_commands_module._check_rollup_state(
            [
                {"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "COMPLETED", "conclusion": "SKIPPED"},
            ]
        )
        == "pass"
    )
    assert task_commands_module._task_id_from_branch_name("codex/task-257-coverage-hard-fail") == (
        "TASK-257"
    )
    assert task_commands_module._task_id_from_branch_name("main") is None


def test_task_command_env_and_output_helpers_cover_validation_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TASK_COMMAND_TEST_INT", raising=False)
    monkeypatch.setenv("REVIEW_TIMEOUT_POLICY", " allow ")
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert task_commands_module._read_int_env("TASK_COMMAND_TEST_INT", 7) == 7
    assert task_commands_module._read_review_timeout_policy_env() == "allow"
    assert task_commands_module._summarize_output_lines(["one", "two"], max_lines=5) == [
        "one",
        "two",
    ]
    assert task_commands_module._ensure_command_available("git") == "/usr/bin/git"

    monkeypatch.setenv("TASK_COMMAND_TEST_INT", "-1")
    with pytest.raises(ValueError, match="must be non-negative"):
        task_commands_module._read_int_env("TASK_COMMAND_TEST_INT", 7)


def test_run_pr_scope_guard_and_review_gate_use_expected_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_subprocess_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return _completed(args)

    monkeypatch.setattr(task_commands_module.subprocess, "run", fake_subprocess_run)

    scope_result = task_commands_module._run_pr_scope_guard(
        branch_name="codex/task-257-coverage-hard-fail",
        pr_title="TASK-257: coverage hard fail",
        pr_body="Primary-Task: TASK-257\n",
    )

    assert scope_result.returncode == 0
    assert captured["args"] == ["./scripts/check_pr_task_scope.sh"]
    assert captured["env"]["PR_BRANCH"] == "codex/task-257-coverage-hard-fail"

    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=30,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=2,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    gate_calls: dict[str, object] = {}
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **kwargs: (
            gate_calls.update({"args": args, "kwargs": kwargs}) or _completed(args)
        ),
    )

    gate_result = task_commands_module._run_review_gate(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert gate_result.returncode == 0
    assert gate_calls["args"][:2] == ["python3", "./scripts/check_pr_review_gate.py"]
    assert gate_calls["kwargs"]["timeout_seconds"] == 37


def test_wait_helpers_cover_timeout_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=0,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh"], returncode=1, stderr="still pending"),
    )

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is False
    assert check_lines == ["still pending"]
    assert check_reason == "timeout"
    assert state_ok is False
    assert state_lines == ["still pending"]


def test_wait_helpers_retry_until_checks_and_state_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=2,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    check_results = iter(
        [
            _completed(["gh", "pr", "checks"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "checks"]),
        ]
    )
    state_results = iter(
        [
            _completed(["gh", "pr", "view"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "view"], stdout="MERGED\n"),
        ]
    )
    sleep_calls: list[int] = []

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "checks"]:
            return next(check_results)
        if args[:3] == ["gh", "pr", "view"]:
            return next(state_results)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(task_commands_module.time, "sleep", sleep_calls.append)

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is True
    assert check_lines == []
    assert check_reason == "pass"
    assert state_ok is True
    assert state_lines == []
    assert sleep_calls == [2, 2]


def test_wait_helpers_retry_without_sleep_when_polling_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=0,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    check_results = iter(
        [
            _completed(["gh", "pr", "checks"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "checks"]),
        ]
    )
    state_results = iter(
        [
            _completed(["gh", "pr", "view"], returncode=1, stderr="still pending"),
            _completed(["gh", "pr", "view"], stdout="MERGED\n"),
        ]
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "checks"]:
            return next(check_results)
        if args[:3] == ["gh", "pr", "view"]:
            return next(state_results)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    state_ok, state_lines = task_commands_module._wait_for_pr_state(
        pr_url="https://example.invalid/pr/257",
        expected_state="MERGED",
        config=config,
    )

    assert checks_ok is True
    assert check_lines == []
    assert check_reason == "pass"
    assert state_ok is True
    assert state_lines == []


def test_required_checks_state_reports_failed_required_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    {
                        "bucket": "fail",
                        "name": "Test",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/test",
                    },
                    {"bucket": "pending", "name": "Build", "workflow": "CI", "link": ""},
                ]
            ),
        ),
    )

    state, lines = task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )
    checks_ok, check_lines, check_reason = task_commands_module._wait_for_required_checks(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert state == "fail"
    assert lines == ["CI / Test: fail (https://example.invalid/checks/test)"]
    assert checks_ok is False
    assert check_lines == lines
    assert check_reason == "fail"


def test_required_checks_state_handles_unexpected_json_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            stdout="{not-json",
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pass", [])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout="still pending",
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pending", ["still pending"])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            stdout='"pass"',
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pass", [])

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout='"pending"',
        ),
    )
    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("pending", ['"pending"'])


def test_required_checks_state_reports_pending_required_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    "ignore-me",
                    {
                        "bucket": "pending",
                        "name": "Build",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/build",
                    },
                    {"bucket": "pass", "name": "Lint", "workflow": "CI", "link": ""},
                ]
            ),
        ),
    )

    state, lines = task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    )

    assert state == "pending"
    assert lines == ["CI / Build: pending (https://example.invalid/checks/build)"]


def test_required_checks_state_does_not_treat_unknown_nonzero_status_as_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(
            ["gh", "pr", "checks"],
            returncode=1,
            stdout=json.dumps(
                [
                    {
                        "bucket": "neutral",
                        "name": "Build",
                        "workflow": "CI",
                        "link": "https://example.invalid/checks/build",
                    }
                ]
            ),
        ),
    )

    assert task_commands_module._required_checks_state(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == (
        "pending",
        [
            (
                '[{"bucket": "neutral", "name": "Build", "workflow": "CI", "link": '
                '"https://example.invalid/checks/build"}]'
            )
        ],
    )


def test_current_required_checks_blocker_maps_check_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("fail", ["CI / Test: fail"]),
    )
    assert task_commands_module._current_required_checks_blocker(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("required PR checks are failing on the current head.", ["CI / Test: fail"])

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("pending", ["CI / Build: pending"]),
    )
    assert task_commands_module._current_required_checks_blocker(
        pr_url="https://example.invalid/pr/257",
        config=config,
    ) == ("required PR checks are still pending on the current head.", ["CI / Build: pending"])

    monkeypatch.setattr(
        task_commands_module,
        "_required_checks_state",
        lambda **_kwargs: ("pass", []),
    )
    assert (
        task_commands_module._current_required_checks_blocker(
            pr_url="https://example.invalid/pr/257",
            config=config,
        )
        is None
    )


def test_unresolved_review_thread_lines_reports_unresolved_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "nodes": [
                                                        {
                                                            "author": {
                                                                "login": "chatgpt-codex-connector[bot]"
                                                            },
                                                            "body": "Please resolve this thread.",
                                                            "path": "src/horadus_cli/task_commands.py",
                                                            "line": 2201,
                                                            "originalLine": 2201,
                                                            "url": "https://example.invalid/comment/290",
                                                        }
                                                    ]
                                                },
                                            },
                                            {
                                                "isResolved": True,
                                                "comments": {
                                                    "nodes": [
                                                        {
                                                            "author": {"login": "reviewer"},
                                                            "body": "Already resolved.",
                                                            "path": "README.md",
                                                            "line": 10,
                                                            "originalLine": 10,
                                                            "url": "https://example.invalid/comment/resolved",
                                                        }
                                                    ]
                                                },
                                            },
                                        ]
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._unresolved_review_thread_lines(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == [
        "- src/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
        "  Please resolve this thread.",
    ]


def test_unresolved_review_thread_lines_handles_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: (
            _completed(args, stdout="invalid\n")
            if args[:4] == ["gh", "repo", "view", "--json"]
            else _completed(args)
        ),
    )
    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )

    def fake_invalid_pr(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="not-a-number\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_invalid_pr)
    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )

    def fake_bad_graphql(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, returncode=1, stderr="graphql failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_graphql)
    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )

    def fake_bad_json(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(args, stdout="{bad")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_json)
    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )

    def fake_bad_nodes(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {"reviewThreads": {"nodes": "not-a-list"}}
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_bad_nodes)
    assert (
        task_commands_module._unresolved_review_thread_lines(
            pr_url="https://example.invalid/pr/290",
            config=config,
        )
        == []
    )


def test_unresolved_review_thread_lines_handles_sparse_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["gh", "repo", "view", "--json"]:
            return _completed(args, stdout="s5unanow/horadus\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            return _completed(args, stdout="290\n")
        if args[:3] == ["gh", "api", "graphql"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [
                                            {"isResolved": False, "comments": {"nodes": "bad"}},
                                            {"isResolved": False, "comments": {"nodes": ["bad"]}},
                                            {
                                                "isResolved": False,
                                                "comments": {
                                                    "nodes": [
                                                        {
                                                            "author": None,
                                                            "body": "",
                                                            "path": "README.md",
                                                            "line": None,
                                                            "originalLine": None,
                                                            "url": "",
                                                        }
                                                    ]
                                                },
                                            },
                                        ]
                                    }
                                }
                            }
                        }
                    }
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._unresolved_review_thread_lines(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["- README.md:?"]


def test_maybe_request_fresh_review_posts_codex_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )
    called: dict[str, object] = {}

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        called["args"] = args
        return _completed(args, stdout="https://example.invalid/comment/trigger\n")

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=config,
    ) == ["Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review`."]
    assert called["args"] == [
        "gh",
        "pr",
        "comment",
        "https://example.invalid/pr/290",
        "--body",
        "@codex review",
    ]


def test_maybe_request_fresh_review_handles_non_codex_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    non_codex_config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="other-reviewer",
        review_timeout_policy="allow",
    )
    assert (
        task_commands_module._maybe_request_fresh_review(
            pr_url="https://example.invalid/pr/290",
            config=non_codex_config,
        )
        == []
    )

    codex_config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=5,
        checks_poll_seconds=1,
        review_timeout_seconds=5,
        review_poll_seconds=1,
        review_bot_login="chatgpt-codex-connector[bot]",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="comment failed"),
    )
    assert task_commands_module._maybe_request_fresh_review(
        pr_url="https://example.invalid/pr/290",
        config=codex_config,
    ) == [
        "Failed to request a fresh review from `chatgpt-codex-connector[bot]` automatically.",
        "comment failed",
    ]


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


def test_task_preflight_data_passes_when_open_pr_query_returns_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_OPEN_TASK_PRS", raising=False)
    monkeypatch.setattr(task_commands_module.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(task_commands_module, "_ensure_required_hooks", lambda: (True, []))
    monkeypatch.setattr(task_commands_module, "_open_task_prs", lambda: (True, []))

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
    assert data["local_main_sha"] == "abc"
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


def test_eligibility_data_accepts_successful_preflight_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Active Tasks\n- `TASK-253` Coverage\n", encoding="utf-8"
    )
    monkeypatch.setenv("TASK_ELIGIBILITY_SPRINT_FILE", str(sprint_path))
    monkeypatch.setenv("TASK_ELIGIBILITY_PREFLIGHT_CMD", "printf ok")
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda _command: _completed(["sh"], stdout="ok"),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["task_id"] == "TASK-253"
    assert lines == ["Agent task eligibility passed: TASK-253"]


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


def test_eligibility_data_propagates_preflight_failures(
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
        lambda: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"reason": "dirty"},
            ["preflight failed"],
        ),
    )

    exit_code, data, lines = task_commands_module.eligibility_data("TASK-253")

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight"] == {"reason": "dirty"}
    assert lines[-1] == "Task sequencing preflight failed for TASK-253."


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


def test_start_task_data_returns_preflight_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "task_preflight_data",
        lambda: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"reason": "dirty"},
            ["preflight failed"],
        ),
    )

    exit_code, data, lines = task_commands_module.start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["preflight"] == {"reason": "dirty"}
    assert lines == ["preflight failed"]


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


def test_safe_start_task_data_propagates_eligibility_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"task_id": "TASK-253", "requires_human": True},
            ["TASK-253 is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"],
        ),
    )

    exit_code, data, lines = task_commands_module.safe_start_task_data(
        "TASK-253", "coverage-100", dry_run=False
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["requires_human"] is True
    assert lines == ["TASK-253 is marked [REQUIRES_HUMAN] and is not eligible for autonomous start"]


def test_safe_start_task_data_runs_guarded_start_after_eligibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "eligibility_data",
        lambda _task_id: (
            task_commands_module.ExitCode.OK,
            {"task_id": "TASK-253"},
            ["Agent task eligibility passed: TASK-253"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "start_task_data",
        lambda _task_id, name, *, dry_run: (
            task_commands_module.ExitCode.OK,
            {
                "task_id": "TASK-253",
                "branch_name": "codex/task-253-coverage-100",
                "dry_run": dry_run,
            },
            [
                "Task sequencing guard passed: main is clean/synced and no open task PRs.",
                f"Dry run: would create task branch codex/task-253-{name}",
            ],
        ),
    )

    exit_code, data, lines = task_commands_module.safe_start_task_data(
        "TASK-253", "coverage-100", dry_run=True
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] == "codex/task-253-coverage-100"
    assert lines == [
        "Agent task eligibility passed: TASK-253",
        "Task sequencing guard passed: main is clean/synced and no open task PRs.",
        "Dry run: would create task branch codex/task-253-coverage-100",
    ]


def test_record_friction_data_dry_run_reports_entry_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 197 --squash",
        friction_type="forced_fallback",
        note="Needed a manual merge fallback.",
        suggested_improvement="Teach finish to surface the blocker better.",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert any(
        "Dry run: would append structured workflow friction entry." in line for line in lines
    )
    assert not (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    ).exists()


def test_record_friction_data_appends_structured_jsonl_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks start TASK-265 --name friction-log",
        fallback_used="git switch -c codex/task-265-friction-log",
        friction_type="missing_cli_surface",
        note="Needed lower-level git fallback.",
        suggested_improvement="Expose the missing workflow surface in horadus.",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is False
    assert lines[-1] == "Recorded structured workflow friction entry."

    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    payload = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert payload == [
        {
            "command_attempted": "uv run --no-sync horadus tasks start TASK-265 --name friction-log",
            "fallback_used": "git switch -c codex/task-265-friction-log",
            "friction_type": "missing_cli_surface",
            "note": "Needed lower-level git fallback.",
            "recorded_at": payload[0]["recorded_at"],
            "suggested_improvement": "Expose the missing workflow surface in horadus.",
            "task_id": "TASK-265",
        }
    ]
    assert payload[0]["recorded_at"].endswith("Z")


def test_record_friction_data_reports_filesystem_write_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    def fail_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 199 --squash",
        friction_type="forced_fallback",
        note="Needed manual recovery.",
        suggested_improvement="Surface write failures cleanly.",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["dry_run"] is False
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert data["error"] == "permission denied"
    assert lines[-2:] == [
        "Workflow friction logging failed while writing the gitignored artifact.",
        "Filesystem error: permission denied",
    ]
    assert not (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    ).exists()


def test_record_friction_data_rejects_invalid_friction_type() -> None:
    exit_code, data, lines = task_commands_module.record_friction_data(
        task_input="TASK-265",
        command_attempted="uv run --no-sync horadus tasks finish TASK-265",
        fallback_used="gh pr merge 199 --squash",
        friction_type="not-valid",
        note="Needed manual recovery.",
        suggested_improvement="Validate friction types.",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["friction_type"] == "not-valid"
    assert lines[0] == "Workflow friction logging failed."


def test_load_workflow_friction_entries_rejects_invalid_json_and_missing_fields(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "entries.jsonl"
    log_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid workflow friction JSON"):
        task_commands_module._load_workflow_friction_entries(log_path)

    log_path.write_text(json.dumps({"task_id": "TASK-265"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing fields"):
        task_commands_module._load_workflow_friction_entries(log_path)

    log_path.write_text('["not-an-object"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object"):
        task_commands_module._load_workflow_friction_entries(log_path)


def test_load_workflow_friction_entries_skip_blank_lines_and_empty_day_reports_no_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n"
        + json.dumps(
            {
                "recorded_at": "2026-03-07T09:00:00Z",
                "task_id": "TASK-265",
                "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                "fallback_used": "gh pr merge 199 --squash",
                "friction_type": "forced_fallback",
                "note": "Older entry outside the report window.",
                "suggested_improvement": "Surface GitHub review blockers more clearly.",
            },
            sort_keys=True,
        )
        + "\n\n",
        encoding="utf-8",
    )

    entries = task_commands_module._load_workflow_friction_entries(log_path)
    assert len(entries) == 1

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 0
    assert lines[-1] == "Wrote grouped workflow friction summary."
    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    assert (
        "- No workflow friction entries were recorded for this UTC day."
        in report_path.read_text(encoding="utf-8")
    )


def test_summarize_workflow_friction_deduplicates_nonblank_notes() -> None:
    entries = [
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T08:00:00Z",
            task_id="TASK-265",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="Repeated note",
            suggested_improvement="Improve merge recovery",
        ),
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T09:00:00Z",
            task_id="TASK-266",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="Repeated note",
            suggested_improvement="Improve merge recovery",
        ),
        task_commands_module.WorkflowFrictionEntry(
            recorded_at="2026-03-08T10:00:00Z",
            task_id="TASK-267",
            command_attempted="finish",
            fallback_used="merge",
            friction_type="forced_fallback",
            note="",
            suggested_improvement="Improve merge recovery",
        ),
    ]

    patterns, _improvements, counts = task_commands_module._summarize_workflow_friction(entries)

    assert counts["forced_fallback"] == 3
    assert len(patterns) == 1
    assert patterns[0].notes == ["Repeated note"]


def test_summarize_friction_data_writes_grouped_daily_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "recorded_at": "2026-03-08T08:00:00Z",
                        "task_id": "TASK-265",
                        "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                        "fallback_used": "gh pr merge 199 --squash",
                        "friction_type": "forced_fallback",
                        "note": "Needed a manual merge fallback.",
                        "suggested_improvement": "Surface GitHub review blockers more clearly.",
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "recorded_at": "2026-03-08T09:00:00Z",
                        "task_id": "TASK-266",
                        "command_attempted": "uv run --no-sync horadus tasks finish TASK-265",
                        "fallback_used": "gh pr merge 199 --squash",
                        "friction_type": "forced_fallback",
                        "note": "The old review thread still blocked merge readiness.",
                        "suggested_improvement": "Surface GitHub review blockers more clearly.",
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "recorded_at": "2026-03-07T23:30:00Z",
                        "task_id": "TASK-264",
                        "command_attempted": "uv run --no-sync horadus tasks safe-start TASK-264 --name workflow-drift-check",
                        "fallback_used": "git switch -c codex/task-264-workflow-drift-check",
                        "friction_type": "missing_cli_surface",
                        "note": "Older entry outside the report window.",
                        "suggested_improvement": "Add a missing safe-start flow.",
                    },
                    sort_keys=True,
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 2
    assert data["pattern_count"] == 1
    assert data["improvement_count"] == 1
    assert lines[-1] == "Wrote grouped workflow friction summary."

    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    report = report_path.read_text(encoding="utf-8")
    assert "# Horadus Workflow Friction Summary - 2026-03-08" in report
    assert "### 1. `forced_fallback` x2" in report
    assert "Surface GitHub review blockers more clearly." in report
    assert "`TASK-265`, `TASK-266`" in report
    assert "Do not auto-create backlog tasks from this report" in report
    assert (
        "Investigate Horadus workflow friction around Surface GitHub review blockers more clearly."
        in report
    )


def test_summarize_friction_data_rejects_invalid_report_date() -> None:
    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-99-99",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {}
    assert lines == ["Invalid report date '2026-99-99'. Expected YYYY-MM-DD."]


def test_summarize_friction_data_reports_invalid_log_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("{bad json}\n", encoding="utf-8")

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert lines == [
        "Workflow friction summary failed: Invalid workflow friction JSON at line 1: Expecting property name enclosed in double quotes."
    ]


def test_summarize_friction_data_creates_empty_daily_checkpoint_when_log_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["entry_count"] == 0
    assert data["missing_log"] is True
    assert lines[-1] == "Wrote grouped workflow friction summary."

    report_path = (
        tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "daily" / "2026-03-08.md"
    )
    report = report_path.read_text(encoding="utf-8")
    assert (
        "No workflow friction log exists yet; this report is an empty daily checkpoint." in report
    )
    assert "- None for this report window." in report


def test_summarize_friction_data_reports_filesystem_read_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    log_path = tmp_path / "artifacts" / "agent" / "horadus-cli-feedback" / "entries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("[]\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == log_path:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input=None,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["log_path"] == "artifacts/agent/horadus-cli-feedback/entries.jsonl"
    assert data["error"] == "permission denied"
    assert lines == [
        "Workflow friction summary failed while reading the friction log artifact.",
        "Filesystem error: permission denied",
    ]


def test_summarize_friction_data_dry_run_skips_writing_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input="artifacts/custom-report.md",
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert lines[-1] == "Dry run: would write grouped workflow friction summary."
    assert not (tmp_path / "artifacts" / "custom-report.md").exists()


def test_summarize_friction_data_reports_filesystem_write_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(task_commands_module, "repo_root", lambda: tmp_path)
    original_mkdir = Path.mkdir

    def fail_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == tmp_path / "artifacts":
            raise OSError("disk full")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    exit_code, data, lines = task_commands_module.summarize_friction_data(
        report_date_input="2026-03-08",
        output_path_input="artifacts/report.md",
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["error"] == "disk full"
    assert lines[-2:] == [
        "Workflow friction summary failed while writing the report artifact.",
        "Filesystem error: disk full",
    ]


def test_handle_record_friction_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_record_friction(
        argparse.Namespace(
            task_id="bad-task",
            command_attempted="cmd",
            fallback_used="fallback",
            friction_type="forced_fallback",
            note="note",
            suggested_improvement="improve",
        )
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_command_handlers_wrap_data_functions_and_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_finish_task_data(
        task_input: str | None, *, dry_run: bool
    ) -> tuple[int, dict[str, object], list[str]]:
        return (
            task_commands_module.ExitCode.OK,
            {"task_id": task_input, "dry_run": dry_run},
            ["finish"],
        )

    monkeypatch.setattr(
        task_commands_module,
        "finish_task_data",
        fake_finish_task_data,
    )
    monkeypatch.setattr(
        task_commands_module,
        "record_friction_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["record"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "summarize_friction_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["summary"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["lifecycle"]),
    )
    monkeypatch.setattr(
        task_commands_module,
        "local_gate_data",
        lambda **_kwargs: (task_commands_module.ExitCode.OK, {"ok": True}, ["gate"]),
    )

    assert task_commands_module.handle_finish(
        argparse.Namespace(task_id="257", dry_run=False)
    ).lines == ["finish"]
    assert task_commands_module.handle_record_friction(
        argparse.Namespace(
            task_id="257",
            command_attempted="cmd",
            fallback_used="fallback",
            friction_type="forced_fallback",
            note="note",
            suggested_improvement="improve",
            dry_run=False,
        )
    ).lines == ["record"]
    assert task_commands_module.handle_summarize_friction(
        argparse.Namespace(date="2026-03-08", output=None, dry_run=False)
    ).lines == ["summary"]
    assert task_commands_module.handle_lifecycle(
        argparse.Namespace(task_id="257", strict=False, dry_run=False)
    ).lines == ["lifecycle"]
    assert task_commands_module.handle_local_gate(
        argparse.Namespace(full=True, dry_run=False)
    ).lines == ["gate"]

    assert task_commands_module.handle_finish(
        argparse.Namespace(task_id="bad-task", dry_run=False)
    ).error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]
    assert task_commands_module.handle_lifecycle(
        argparse.Namespace(task_id="bad-task", strict=False, dry_run=False)
    ).error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_full_local_gate_steps_match_expected_ci_parity_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UV_BIN", raising=False)

    steps = task_commands_module.full_local_gate_steps()

    assert [step.name for step in steps] == [
        "check-tracked-artifacts",
        "docs-freshness",
        "ruff-format-check",
        "ruff-check",
        "mypy",
        "validate-taxonomy",
        "pytest-unit-cov",
        "bandit",
        "lockfile-check",
        "integration-docker",
        "build-package",
    ]
    assert steps[0].command == "./scripts/check_no_tracked_artifacts.sh"
    assert steps[1].command == "uv run --no-sync python scripts/check_docs_freshness.py"
    assert steps[2].command == "uv run --no-sync ruff format src/ tests/ --check"
    assert steps[5].command.startswith("uv run --no-sync horadus eval validate-taxonomy ")
    assert steps[6].command == "./scripts/run_unit_coverage_gate.sh"
    assert steps[9].command == "./scripts/test_integration_docker.sh"
    assert steps[10].command == (
        "rm -rf dist build *.egg-info && "
        "uv run --no-sync --with build python -m build && "
        "uv run --no-sync --with twine twine check dist/*"
    )


def test_repo_workflow_configs_enforce_hard_unit_coverage_threshold() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    precommit = (repo_root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert "./scripts/run_unit_coverage_gate.sh" in precommit
    assert "stages: [pre-push]" in precommit
    assert "./scripts/run_unit_coverage_gate.sh" in ci_workflow
    assert "--cov-fail-under=100" in ci_workflow
    assert "test-unit-cov: deps-dev" in makefile
    assert "./scripts/run_unit_coverage_gate.sh" in makefile


def test_local_gate_data_dry_run_reports_custom_absolute_uv_bin_for_build_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_uv = "/tmp/custom-tools/uv"
    monkeypatch.setenv("UV_BIN", custom_uv)
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: name if name == custom_uv else None,
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    build_step = next(step for step in data["steps"] if step["name"] == "build-package")
    assert build_step["command"] == (
        "rm -rf dist build *.egg-info && "
        f"{custom_uv} run --no-sync --with build python -m build && "
        f"{custom_uv} run --no-sync --with twine twine check dist/*"
    )
    assert f"- build-package: {build_step['command']}" in lines


def test_local_gate_data_requires_full_mode() -> None:
    exit_code, data, lines = task_commands_module.local_gate_data(full=False, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {"full": False}
    assert lines[-1] == (
        "Use `horadus tasks local-gate --full` for the canonical post-task local gate."
    )


def test_local_gate_data_reports_missing_uv_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "_ensure_command_available", lambda _name: None)

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "uv"
    assert lines == ["Local gate failed: uv is required to run the canonical full local gate."]


def test_ensure_docker_ready_returns_immediately_when_daemon_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], stdout="Server Version: test\n"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is True
    assert result.attempted_start is False
    assert result.lines == ["Docker is ready for integration gate."]


def test_ensure_docker_ready_attempts_auto_start_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], stdout="Server Version: test\n"),
        ]
    )
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    start_calls: list[str] = []
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: (
            start_calls.append(command) or _completed(["bash", "-lc", command], stdout="started\n")
        ),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert start_calls == ["echo starting-docker"]
    assert result.ready is True
    assert result.attempted_start is True
    assert result.lines[-1] == "Docker became ready after auto-start."


def test_ensure_docker_ready_reports_unsupported_auto_start_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.sys, "platform", "linux")

    def fake_which(name: str) -> str | None:
        if name == "docker":
            return "/bin/docker"
        return None

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.supported_auto_start is False
    assert result.lines[-1] == (
        "Auto-start is unsupported on this environment; start Docker manually and retry."
    )


def test_ensure_docker_ready_reports_invalid_env_override_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "not-an-int")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is False
    assert result.lines == [
        "Docker readiness failed: DOCKER_READY_TIMEOUT_SECONDS must be an integer."
    ]


def test_ensure_docker_ready_reports_missing_docker_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "docker":
            return None
        return original_which(name)

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.lines == ["Docker readiness failed: docker CLI is required for integration gate."]


def test_ensure_docker_ready_reports_auto_start_command_failure_via_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.sys, "platform", "linux")

    def fake_which(name: str) -> str | None:
        if name in {"docker", "docker-desktop"}:
            return f"/bin/{name}"
        return None

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="start failed"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is True
    assert result.lines[-2:] == ["Docker auto-start command failed.", "start failed"]


def test_docker_helper_functions_cover_macos_auto_start_and_timeout_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HORADUS_DOCKER_START_CMD", raising=False)
    monkeypatch.setattr(task_commands_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: "/usr/bin/open" if name in {"docker", "open"} else None,
    )

    plan = task_commands_module._docker_start_plan()
    assert plan is not None
    assert plan.argv == ["open", "-a", "Docker"]

    run_calls: list[list[str]] = []
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: run_calls.append(args) or _completed(args, stdout="docker ok\n"),
    )
    info_result = task_commands_module._docker_info_result()
    assert info_result.stdout == "docker ok\n"
    assert run_calls == [["docker", "info"]]

    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOCKER_READY_POLL_SECONDS", "2")
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
        ]
    )
    time_values = iter([0.0, 0.5, 1.5])
    sleep_calls: list[int] = []
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout="started\n"),
    )
    monkeypatch.setattr(task_commands_module.time, "time", lambda: next(time_values))
    monkeypatch.setattr(task_commands_module.time, "sleep", sleep_calls.append)

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is True
    assert result.lines[-2:] == [
        "Docker auto-start did not make the daemon ready before timeout.",
        "still down",
    ]
    assert sleep_calls == [2]


def test_ensure_docker_ready_retries_without_sleep_when_polling_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOCKER_READY_POLL_SECONDS", "0")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
            _completed(["docker", "info"], stdout="Server Version: test\n"),
        ]
    )
    time_values = iter([0.0, 0.5, 0.6])
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout="started\n"),
    )
    monkeypatch.setattr(task_commands_module.time, "time", lambda: next(time_values))

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is True
    assert result.attempted_start is True
    assert result.lines[-1] == "Docker became ready after auto-start."


def test_local_gate_data_dry_run_reports_canonical_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="uv run docs"),
            task_commands_module.LocalGateStep(name="ruff-check", command="uv run ruff"),
        ],
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["mode"] == "full"
    assert data["dry_run"] is True
    assert lines == [
        "Running canonical full local gate:",
        "- docs-freshness: uv run docs",
        "- ruff-check: uv run ruff",
        "Dry run: validated the canonical step list without executing it.",
    ]


def test_local_gate_data_runs_all_steps_and_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="step-1"),
            task_commands_module.LocalGateStep(name="ruff-check", command="step-2"),
        ],
    )
    calls: list[str] = []

    def fake_run_shell(command: str) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(["bash", "-lc", command], stdout=f"ok:{command}\n")

    monkeypatch.setattr(task_commands_module, "_run_shell", fake_run_shell)

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert calls == ["step-1", "step-2"]
    assert data["mode"] == "full"
    assert lines == [
        "Running canonical full local gate:",
        "[1/2] RUN docs-freshness",
        "[1/2] PASS docs-freshness",
        "[2/2] RUN ruff-check",
        "[2/2] PASS ruff-check",
        "Full local gate passed.",
    ]


def test_local_gate_data_checks_docker_readiness_before_integration_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="step-1"),
            task_commands_module.LocalGateStep(
                name="integration-docker", command="./scripts/test_integration_docker.sh"
            ),
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker became ready after auto-start."],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout=f"ok:{command}\n"),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["mode"] == "full"
    assert "Docker became ready after auto-start." in lines
    assert "[2/2] PASS integration-docker" in lines


def test_local_gate_data_blocks_when_docker_cannot_be_made_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(
                name="integration-docker", command="./scripts/test_integration_docker.sh"
            )
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=False,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker auto-start did not make the daemon ready before timeout."],
        ),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["failed_step"] == "integration-docker"
    assert data["docker_ready"] is False
    assert lines[-1] == "Local gate failed because Docker is not ready for the integration step."


def test_local_gate_data_reports_failed_step_with_condensed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [task_commands_module.LocalGateStep(name="pytest-unit-cov", command="step-fail")],
    )
    noisy_output = "\n".join(f"line-{index}" for index in range(100))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda _command: _completed(
            ["bash", "-lc", "step-fail"], returncode=1, stdout=noisy_output
        ),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["failed_step"] == "pytest-unit-cov"
    assert lines[2] == "Local gate failed at step `pytest-unit-cov`."
    assert lines[3] == "Command: step-fail"
    assert "... (" in "\n".join(lines)


@pytest.mark.parametrize(
    ("snapshot", "expected_state"),
    [
        (_task_snapshot(), "local-only"),
        (_task_snapshot(remote_branch_exists=True), "pushed"),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="OPEN",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid=None,
                    check_state="pending",
                )
            ),
            "pr-open",
        ),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="OPEN",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid=None,
                    check_state="pass",
                )
            ),
            "ci-green",
        ),
        (
            _task_snapshot(
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="MERGED",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid="merge-sha",
                    check_state="pass",
                ),
                local_main_synced=False,
                merge_commit_on_main=False,
            ),
            "merged",
        ),
        (
            _task_snapshot(
                current_branch="main",
                branch_name="codex/task-259-done-state-verifier",
                pr=task_commands_module.TaskPullRequest(
                    number=259,
                    url="https://example.invalid/pr/259",
                    state="MERGED",
                    is_draft=False,
                    head_ref_name="codex/task-259-done-state-verifier",
                    head_ref_oid="head-sha",
                    merge_commit_oid="merge-sha",
                    check_state="pass",
                ),
                local_main_synced=True,
                merge_commit_on_main=True,
            ),
            "local-main-synced",
        ),
    ],
)
def test_task_lifecycle_state_distinguishes_required_states(
    snapshot: task_commands_module.TaskLifecycleSnapshot,
    expected_state: str,
) -> None:
    assert task_commands_module.task_lifecycle_state(snapshot) == expected_state


def test_task_lifecycle_data_strict_mode_fails_before_local_main_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            pr=task_commands_module.TaskPullRequest(
                number=259,
                url="https://example.invalid/pr/259",
                state="MERGED",
                is_draft=False,
                head_ref_name="codex/task-259-done-state-verifier",
                head_ref_oid="head-sha",
                merge_commit_oid="merge-sha",
                check_state="pass",
            ),
            local_main_synced=False,
            merge_commit_on_main=False,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=True,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["lifecycle_state"] == "merged"
    assert data["strict_complete"] is False
    assert lines[-1] == (
        "Strict verification failed: repo-policy completion requires state `local-main-synced`."
    )


def test_task_lifecycle_data_strict_mode_passes_when_repo_policy_is_fully_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            pr=task_commands_module.TaskPullRequest(
                number=259,
                url="https://example.invalid/pr/259",
                state="MERGED",
                is_draft=False,
                head_ref_name="codex/task-259-done-state-verifier",
                head_ref_oid="head-sha",
                merge_commit_oid="merge-sha",
                check_state="pass",
            ),
            local_main_synced=True,
            merge_commit_on_main=True,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=True,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["lifecycle_state"] == "local-main-synced"
    assert data["strict_complete"] is True
    assert lines[-1] == "- strict complete: yes"


def test_task_lifecycle_data_reports_missing_required_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "_ensure_command_available", lambda _name: None)

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert lines == ["Task lifecycle failed: missing required command 'gh'."]


def test_task_lifecycle_data_dry_run_reports_live_state_without_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(pr=None),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=True,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["lifecycle_state"] == "local-only"
    assert "- PR: none" in lines
    assert lines[-1] == "Dry run: lifecycle inspection is read-only; returned live state."


def test_task_lifecycle_state_allows_detached_head_when_main_is_synced() -> None:
    snapshot = _task_snapshot(
        current_branch="HEAD",
        pr=task_commands_module.TaskPullRequest(
            number=268,
            url="https://example.invalid/pr/268",
            state="MERGED",
            is_draft=False,
            head_ref_name="codex/task-268-detached-head-lifecycle",
            head_ref_oid="head-sha",
            merge_commit_oid="merge-sha",
            check_state="pass",
        ),
        local_main_synced=True,
        merge_commit_on_main=True,
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "local-main-synced"


def test_task_lifecycle_state_keeps_open_prs_without_green_checks_in_pr_open() -> None:
    snapshot = _task_snapshot(
        pr=task_commands_module.TaskPullRequest(
            number=259,
            url="https://example.invalid/pr/259",
            state="OPEN",
            is_draft=True,
            head_ref_name="codex/task-259-done-state-verifier",
            head_ref_oid="head-sha",
            merge_commit_oid=None,
            check_state="pass",
        )
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "pr-open"


def test_task_lifecycle_state_treats_closed_prs_as_pushed_when_remote_branch_exists() -> None:
    snapshot = _task_snapshot(
        remote_branch_exists=True,
        pr=task_commands_module.TaskPullRequest(
            number=259,
            url="https://example.invalid/pr/259",
            state="CLOSED",
            is_draft=False,
            head_ref_name="codex/task-259-done-state-verifier",
            head_ref_oid="head-sha",
            merge_commit_oid=None,
            check_state="fail",
        ),
    )

    assert task_commands_module.task_lifecycle_state(snapshot) == "pushed"


def test_resolve_task_lifecycle_allows_explicit_task_id_from_detached_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="HEAD\n"),
            _completed(
                ["git", "branch", "--list"], stdout="  codex/task-268-detached-head-lifecycle\n"
            ),
            _completed(["git", "ls-remote", "--heads"], stdout=""),
            _completed(["git", "status", "--porcelain"], stdout=""),
            _completed(["git", "fetch", "origin", "main", "--quiet"]),
            _completed(["git", "rev-parse", "main"], stdout="main-sha\n"),
            _completed(["git", "rev-parse", "origin/main"], stdout="main-sha\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: None,
    )

    snapshot = task_commands_module.resolve_task_lifecycle("TASK-268", config=config)

    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.task_id == "TASK-268"
    assert snapshot.current_branch == "HEAD"
    assert snapshot.branch_name == "codex/task-268-detached-head-lifecycle"
    assert snapshot.local_main_synced is True


def test_resolve_task_lifecycle_reports_environment_and_lookup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], returncode=1),
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to determine current branch."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )
    result = task_commands_module.resolve_task_lifecycle("bad-task", config=config)
    assert isinstance(result, tuple)
    assert "Invalid task id" in result[2][0]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(
        task_commands_module,
        "_find_task_pull_request",
        lambda **_kwargs: (
            task_commands_module.ExitCode.ENVIRONMENT_ERROR,
            {"task_id": "TASK-257"},
            ["Task lifecycle failed.", "Unable to query GitHub pull requests."],
        ),
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to query GitHub pull requests."]


def test_resolve_task_lifecycle_covers_branch_lookup_and_git_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect local task branches."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect remote task branches."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(["git", "ls-remote"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["No local, remote, or PR lifecycle state found for TASK-257."]

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="feature/misc\n"),
    )
    result = task_commands_module.resolve_task_lifecycle(None, config=config)
    assert isinstance(result, tuple)
    assert result[2] == [
        "Task lifecycle failed.",
        "A task id is required when the current branch is not a canonical task branch.",
    ]


def test_resolve_task_lifecycle_covers_status_fetch_and_merge_commit_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    pr = task_commands_module.TaskPullRequest(
        number=257,
        url="https://example.invalid/pr/257",
        state="MERGED",
        is_draft=False,
        head_ref_name="codex/task-257-coverage-hard-fail",
        head_ref_oid="head-sha",
        merge_commit_oid="merge-sha",
        check_state="pass",
    )

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: pr)
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to inspect working tree state."]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(result, tuple)
    assert result[2] == [
        "Task lifecycle failed.",
        "Unable to refresh origin/main before verification.",
    ]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"], stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n"
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "cat-file"], stdout=""),
            _completed(["git", "merge-base"], returncode=0),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    snapshot = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"
    assert snapshot.merge_commit_available_locally is True
    assert snapshot.merge_commit_on_main is True

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(
                ["git", "branch"],
                stdout="* codex/task-257-coverage-hard-fail\n  codex/task-257-other\n",
            ),
            _completed(["git", "ls-remote"], stdout=""),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], returncode=1),
            _completed(["git", "rev-parse"], stdout="remote-main-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(task_commands_module, "_find_task_pull_request", lambda **_kwargs: None)
    snapshot = task_commands_module.resolve_task_lifecycle(None, config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"
    assert snapshot.local_main_synced is None

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="main\n"),
            _completed(["git", "branch"], stdout=""),
            _completed(
                ["git", "ls-remote"],
                stdout="abc\trefs/heads/codex/task-257-coverage-hard-fail\n",
            ),
            _completed(["git", "status"], stdout=""),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout="main-sha\n"),
            _completed(["git", "rev-parse"], stdout="remote-main-sha\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    snapshot = task_commands_module.resolve_task_lifecycle("TASK-257", config=config)
    assert isinstance(snapshot, task_commands_module.TaskLifecycleSnapshot)
    assert snapshot.branch_name == "codex/task-257-coverage-hard-fail"


def test_resolve_task_lifecycle_requires_explicit_task_id_from_detached_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="HEAD\n"),
    )

    result = task_commands_module.resolve_task_lifecycle(None, config=config)

    assert isinstance(result, tuple)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {"current_branch": "HEAD"}
    assert lines == [
        "Task lifecycle failed.",
        "A task id is required when running from detached HEAD.",
    ]


def test_resolve_finish_context_rejects_task_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-258-canonical-finish\n"),
        ]
    )

    def fake_run_command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return next(responses)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    result = task_commands_module._resolve_finish_context("TASK-259", config)

    assert not isinstance(result, task_commands_module.FinishContext)
    exit_code, data, lines = result
    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_task_id"] == "TASK-258"
    assert data["task_id"] == "TASK-259"
    assert "maps to TASK-258, not TASK-259" in lines[0]


def test_resolve_finish_context_blocks_for_branch_query_error_and_detached_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], returncode=1, stderr="boom"),
    )

    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: boom"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="HEAD\n"),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: detached HEAD is not allowed."


def test_resolve_finish_context_blocks_for_main_recovery_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )

    result = task_commands_module._resolve_finish_context(None, config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: refusing to run on 'main'."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.NOT_FOUND,
            {"task_id": "TASK-257"},
            ["not found"],
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: unable to recover task context from 'main'."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            branch_name=None,
            working_tree_clean=False,
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: working tree must be clean."

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(
            current_branch="main",
            branch_name=None,
            working_tree_clean=True,
        ),
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert "unable to resolve a task branch for TASK-257 from 'main'" in result[2][0]


def test_resolve_finish_context_allows_explicit_task_id_from_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="fail",
    )
    snapshot = _task_snapshot(
        current_branch="main",
        branch_name="codex/task-289-finish-branch-context-recovery",
        pr=task_commands_module.TaskPullRequest(
            number=289,
            url="https://example.invalid/pr/289",
            state="OPEN",
            is_draft=False,
            head_ref_name="codex/task-289-finish-branch-context-recovery",
            head_ref_oid="head-sha-289",
            merge_commit_oid=None,
            check_state="pass",
        ),
    )
    snapshot.task_id = "TASK-289"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="main\n"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: snapshot,
    )

    result = task_commands_module._resolve_finish_context("TASK-289", config)

    assert isinstance(result, task_commands_module.FinishContext)
    assert result.branch_name == "codex/task-289-finish-branch-context-recovery"
    assert result.branch_task_id == "TASK-289"
    assert result.task_id == "TASK-289"
    assert result.current_branch == "main"


def test_resolve_finish_context_blocks_for_noncanonical_or_dirty_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["git", "rev-parse"], stdout="feature/misc\n"),
    )

    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert "branch does not match the required task pattern" in result[2][0]

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], returncode=1, stderr="status failed"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: status failed"

    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], stdout=" M file.py\n"),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )
    result = task_commands_module._resolve_finish_context("TASK-257", config)
    assert isinstance(result, tuple)
    assert result[2][0] == "Task finish blocked: working tree must be clean."


def test_resolve_finish_context_accepts_canonical_branch_without_explicit_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["git", "rev-parse"], stdout="codex/task-257-coverage-hard-fail\n"),
            _completed(["git", "status"], stdout=""),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._resolve_finish_context(None, config)

    assert isinstance(result, task_commands_module.FinishContext)
    assert result.branch_name == "codex/task-257-coverage-hard-fail"
    assert result.branch_task_id == "TASK-257"
    assert result.task_id == "TASK-257"


def test_find_task_pull_request_handles_search_and_view_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], returncode=1),
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to query GitHub pull requests."]

    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(["gh", "pr", "view"], returncode=1),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, tuple)
    assert result[2] == ["Task lifecycle failed.", "Unable to read GitHub PR #259."]


def test_find_task_pull_request_parses_rollup_and_optional_merge_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259},{"number":258}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": {},
                        "statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": ""}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.number == 259
    assert result.merge_commit_oid is None
    assert result.check_state == "pending"


def test_find_task_pull_request_handles_empty_results_and_merge_commit_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda *_args, **_kwargs: _completed(["gh", "pr", "list"], stdout="[]"),
    )
    assert task_commands_module._find_task_pull_request(task_id="TASK-259", config=config) is None

    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": {"oid": "merge-sha"},
                        "statusCheckRollup": ["ignored", {"status": "COMPLETED", "conclusion": ""}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.merge_commit_oid == "merge-sha"
    assert result.check_state == "pending"


def test_find_task_pull_request_ignores_non_dict_merge_commit_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = task_commands_module.FinishConfig(
        gh_bin="gh",
        git_bin="git",
        python_bin="python3",
        checks_timeout_seconds=1,
        checks_poll_seconds=0,
        review_timeout_seconds=1,
        review_poll_seconds=0,
        review_bot_login="bot",
        review_timeout_policy="allow",
    )
    responses = iter(
        [
            _completed(["gh", "pr", "list"], stdout='[{"number":259}]'),
            _completed(
                ["gh", "pr", "view"],
                stdout=json.dumps(
                    {
                        "number": 259,
                        "url": "https://example.invalid/pr/259",
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefName": "codex/task-259-done-state-verifier",
                        "headRefOid": "head-sha",
                        "mergeCommit": "merge-sha",
                        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                    }
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        task_commands_module, "_run_command", lambda *_args, **_kwargs: next(responses)
    )

    result = task_commands_module._find_task_pull_request(task_id="TASK-259", config=config)

    assert isinstance(result, task_commands_module.TaskPullRequest)
    assert result.merge_commit_oid is None


def test_finish_task_data_blocks_for_missing_required_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: None if name == "gh" else "/bin/fake",
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "gh"
    assert lines[0] == "Task finish blocked: missing required command 'gh'."


def test_finish_task_data_propagates_finish_context_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    expected = task_commands_module._task_blocked(
        "working tree must be clean.",
        next_action="Commit or stash local changes, then re-run `horadus tasks finish TASK-257`.",
    )
    monkeypatch.setattr(
        task_commands_module, "_resolve_finish_context", lambda *_args, **_kwargs: expected
    )

    assert task_commands_module.finish_task_data("TASK-257", dry_run=False) == expected


def test_finish_task_data_blocks_when_branch_not_pushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=False,
            supported_auto_start=True,
            lines=["Docker is ready for the next required `git push` pre-push integration gate."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["branch_name"] == "codex/task-258-canonical-finish"
    assert "unable to locate a PR" in lines[0]
    assert "git push -u origin codex/task-258-canonical-finish" in lines[1]


def test_finish_task_data_blocks_when_push_gate_docker_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-261-docker-readiness",
            branch_task_id="TASK-261",
            task_id="TASK-261",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=False,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker auto-start did not make the daemon ready before timeout."],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-261", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["docker_ready"] is False
    assert "Docker is not ready for the next required push gate." in lines[0]
    assert "git push -u origin codex/task-261-docker-readiness" in lines[1]
    assert lines[-1] == "Docker auto-start did not make the daemon ready before timeout."


def test_finish_task_data_dry_run_does_not_attempt_docker_auto_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-261-docker-readiness",
            branch_task_id="TASK-261",
            task_id="TASK-261",
        ),
    )
    docker_calls: list[str] = []
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: (
            docker_calls.append("called")
            or task_commands_module.DockerReadiness(
                ready=True,
                attempted_start=False,
                supported_auto_start=True,
                lines=["Docker is ready."],
            )
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, returncode=1, stderr="no pull requests found")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-261", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert docker_calls == []
    assert data["branch_name"] == "codex/task-261-docker-readiness"
    assert "git push -u origin codex/task-261-docker-readiness" in lines[1]


def test_finish_task_data_blocks_when_required_checks_do_not_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (False, ["required-check failure details"], "timeout"),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert "required PR checks did not pass before timeout" in lines[0]
    assert "Inspect the failing required checks" in lines[1]
    assert lines[-1] == "required-check failure details"


def test_finish_task_data_blocks_immediately_when_required_checks_are_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (False, ["CI / Test: fail"], "fail"),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: required PR checks are failing on the current head."
    assert lines[-1] == "CI / Test: fail"


def test_finish_task_data_blocks_when_checks_turn_red_after_review_gate_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-275-enforce-finish-review-timeout",
            branch_task_id="TASK-275",
            task_id="TASK-275",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-275 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-275 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: (
            "required PR checks are failing on the current head.",
            ["CI / Test: fail"],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/275\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/275"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-275: enforce finish timeout","body":"Primary-Task: TASK-275\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/275"
    assert lines[0] == "Task finish blocked: required PR checks are failing on the current head."
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "CI / Test: fail"


def test_finish_task_data_blocks_on_unresolved_review_threads_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-290-finish-ci-failure-reporting",
            branch_task_id="TASK-290",
            task_id="TASK-290",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-290 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-290 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- src/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
            "  Please resolve this thread.",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: [
            "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review`."
        ],
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/290\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-290: finish CI failure reporting","body":"Primary-Task: TASK-290\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-290", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/290"
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert any("review gate timeout:" in line for line in lines)
    assert any("Please resolve this thread." in line for line in lines)
    assert lines[-1] == (
        "Requested a fresh review from `chatgpt-codex-connector[bot]` with `@codex review`."
    )


def test_finish_task_data_blocks_on_unresolved_review_threads_after_clean_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-290-finish-ci-failure-reporting",
            branch_task_id="TASK-290",
            task_id="TASK-290",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-290 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, [], "pass"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate passed: chatgpt-codex-connector[bot] reviewed current head "
                "head-sha-290 with no inline comments during the 600s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [
            "- src/horadus_cli/task_commands.py:2201 https://example.invalid/comment/290 (chatgpt-codex-connector[bot])",
            "  Please resolve this thread.",
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "_maybe_request_fresh_review",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not request review")),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/290\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/290"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-290: finish CI failure reporting","body":"Primary-Task: TASK-290\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-290", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is blocked by unresolved review comments."
    assert any("review gate passed:" in line for line in lines)
    assert lines[-1] == "  Please resolve this thread."


def test_finish_task_data_blocks_when_pr_metadata_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            return _completed(args, returncode=1, stderr="metadata failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: metadata failed"


def test_finish_task_data_blocks_when_pr_metadata_is_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            return _completed(args, stdout="{bad")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: Unable to parse the PR title/body."


def test_finish_task_data_blocks_when_pr_state_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, returncode=1, stderr="state failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/257"
    assert lines[0] == "Task finish blocked: state failed"


def test_finish_task_data_blocks_when_branch_is_not_pushed_after_pr_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert (
        lines[0]
        == "Task finish blocked: branch `codex/task-257-coverage-hard-fail` is not pushed to origin."
    )


def test_finish_task_data_blocks_when_pr_draft_status_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, returncode=1, stderr="draft failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines[0] == "Task finish blocked: draft failed"


def test_finish_task_data_blocks_when_pr_is_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="true\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert lines[0] == "Task finish blocked: PR is draft; refusing to merge."


def test_finish_task_data_dry_run_reports_merge_and_sync_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-257-coverage-hard-fail",
            branch_task_id="TASK-257",
            task_id="TASK-257",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-257 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if args[:4] == ["gh", "pr", "view", "codex/task-257-coverage-hard-fail"]:
            return _completed(args, stdout="https://example.invalid/pr/257\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/257"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-257: coverage hard fail","body":"Primary-Task: TASK-257\\n"}',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-257", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["dry_run"] is True
    assert (
        lines[-1]
        == "Dry run: scope and PR preconditions passed; would wait for checks, merge, and sync main."
    )


def test_finish_task_data_rejects_zero_review_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "0")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        "Task finish blocked: REVIEW_TIMEOUT_SECONDS must be positive for `horadus tasks finish`.",
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_rejects_review_timeout_override_without_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-283", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        (
            "Task finish blocked: REVIEW_TIMEOUT_SECONDS may differ from the default 600s "
            "(10 minutes) only when "
            "HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE=1 confirms an explicit human "
            "request."
        ),
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_allows_review_timeout_override_with_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("HORADUS_HUMAN_APPROVED_REVIEW_TIMEOUT_OVERRIDE", "1")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-283-finish-review-thumbs-up",
            branch_task_id="TASK-283",
            task_id="TASK-283",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-283 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate passed: chatgpt-codex-connector[bot] reacted THUMBS_UP on the "
                "PR summary during the 5s wait window."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-283", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/283\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/283"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-283: finish review thumbs up","body":"Primary-Task: TASK-283\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-283\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/283"]:
            return _completed(args)
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-283-finish-review-thumbs-up",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-283", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-283"
    assert any("reacted THUMBS_UP on the PR summary" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-283 and synced main."


def test_task_lifecycle_data_does_not_enforce_finish_timeout_override_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: task_commands_module.TaskLifecycleSnapshot(
            task_id="TASK-283",
            current_branch="codex/task-283-finish-review-thumbs-up",
            branch_name="codex/task-283-finish-review-thumbs-up",
            local_branch_names=["codex/task-283-finish-review-thumbs-up"],
            remote_branch_names=["origin/codex/task-283-finish-review-thumbs-up"],
            remote_branch_exists=True,
            working_tree_clean=True,
            pr=task_commands_module.TaskPullRequest(
                number=217,
                url="https://example.invalid/pr/283",
                state="OPEN",
                is_draft=False,
                head_ref_name="codex/task-283-finish-review-thumbs-up",
                head_ref_oid="head-sha-283",
                merge_commit_oid=None,
                check_state="pass",
            ),
            local_main_sha="main-sha",
            remote_main_sha="main-sha",
            local_main_synced=True,
            merge_commit_available_locally=None,
            merge_commit_on_main=None,
            lifecycle_state="ci-green",
            strict_complete=False,
        ),
    )

    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-283",
        strict=False,
        dry_run=False,
    )

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["task_id"] == "TASK-283"
    assert lines[0] == "Task lifecycle: TASK-283"


def test_finish_task_data_rejects_review_timeout_policy_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_POLICY", "fail")

    exit_code, _data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=True)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert lines == [
        "Task finish blocked: REVIEW_TIMEOUT_POLICY must remain `allow` for `horadus tasks finish`.",
        "Next action: Fix the invalid environment override and re-run `horadus tasks finish`.",
    ]


def test_finish_task_data_allows_merge_when_review_gate_times_out_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-275-enforce-finish-review-timeout",
            branch_task_id="TASK-275",
            task_id="TASK-275",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-275 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            returncode=0,
            stdout=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-275 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-276", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/275\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/275"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-275: enforce finish timeout","body":"Primary-Task: TASK-275\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-275\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/275"]:
            return _completed(args)
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-275-enforce-finish-review-timeout",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-275", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["pr_url"] == "https://example.invalid/pr/275"
    assert data["merge_commit"] == "merge-commit-275"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-275 and synced main."


def test_finish_task_data_resumes_from_main_with_explicit_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-289-finish-branch-context-recovery",
            branch_task_id="TASK-289",
            task_id="TASK-289",
            current_branch="main",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-289 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-289 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-289", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:4]
            == [
                "gh",
                "pr",
                "view",
                "codex/task-289-finish-branch-context-recovery",
            ]
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/289\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/289"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-289: finish branch context recovery","body":"Primary-Task: TASK-289\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-289\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/289"]:
            return _completed(args)
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-289-finish-branch-context-recovery",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-289", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["pr_url"] == "https://example.invalid/pr/289"
    assert data["merge_commit"] == "merge-commit-289"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert lines[0] == (
        "Resuming TASK-289 from main using task branch codex/task-289-finish-branch-context-recovery."
    )
    assert any("review gate timeout:" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-289 and synced main."


def test_finish_task_data_blocks_when_review_gate_process_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-284-finish-timeout-exit",
            branch_task_id="TASK-284",
            task_id="TASK-284",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-284 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )

    def fake_run_review_gate(**_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise task_commands_module.CommandTimeoutError(
            ["python", "./scripts/check_pr_review_gate.py"],
            631,
        )

    monkeypatch.setattr(task_commands_module, "_run_review_gate", fake_run_review_gate)

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/284\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/284"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-284: finish timeout exit","body":"Primary-Task: TASK-284\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-284", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/284"
    assert (
        lines[0]
        == "Task finish blocked: review gate command did not exit after the configured wait window."
    )
    assert lines[-1] == "Command timed out after 631s: python ./scripts/check_pr_review_gate.py"


def test_finish_task_data_blocks_when_merge_command_hangs_after_review_gate_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-284-finish-timeout-exit",
            branch_task_id="TASK-284",
            task_id="TASK-284",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-284 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            stdout=(
                "review gate timeout: no actionable current-head review feedback from "
                "chatgpt-codex-connector[bot] for head-sha-284 within 600s. "
                "Continuing due to timeout policy=allow."
            ),
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    real_run_command_with_timeout = task_commands_module._run_command_with_timeout

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/284\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/284"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-284: finish timeout exit","body":"Primary-Task: TASK-284\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    def fake_run_command_with_timeout(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "merge"]:
            raise task_commands_module.CommandTimeoutError(args, 120)
        return real_run_command_with_timeout(args, **kwargs)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        fake_run_command_with_timeout,
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-284", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/284"
    assert (
        lines[0]
        == "Task finish blocked: merge command did not exit cleanly after the review gate passed."
    )
    assert lines[-1].startswith("Command timed out after 120s: gh pr merge")


def test_finish_task_data_blocks_when_review_gate_finds_actionable_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-276-allow-silent-review-timeout",
            branch_task_id="TASK-276",
            task_id="TASK-276",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-276 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(
            ["review"],
            returncode=2,
            stdout=(
                "review gate failed: actionable current-head review comments found:\n"
                "- src/horadus_cli/task_commands.py:1900 https://example.invalid/comment/276\n"
                "  Please address this before merge."
            ),
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/276\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/276"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-276: allow silent review timeout","body":"Primary-Task: TASK-276\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-276", dry_run=False)

    assert exit_code == 2
    assert data["pr_url"] == "https://example.invalid/pr/276"
    assert lines[0] == "Task finish blocked: review gate did not pass."
    assert (
        lines[1]
        == "Next action: Address the current-head review feedback, then re-run `horadus tasks finish`."
    )
    assert lines[-2].startswith("- src/horadus_cli/task_commands.py:1900")


def test_finish_task_data_blocks_when_pr_title_or_body_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-274-standardize-task-pr-titles",
            branch_task_id="TASK-274",
            task_id="TASK-274",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"],
            returncode=1,
            stdout="PR scope guard failed.\nPR title must match required task format:\n  TASK-XXX: short summary\n",
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/274\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/274"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"feat(repo): standardize PR titles","body":"Primary-Task: TASK-274\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-274", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/274"
    assert "PR scope validation failed." in lines[0]
    assert "Fix the PR title to `TASK-274: short summary`" in lines[1]
    assert "PR title must match required task format" in lines[-2]


def test_finish_task_data_succeeds_when_pr_already_merged_after_remote_branch_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_wait_for_required_checks",
        lambda **_kwargs: (True, []),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="review gate passed"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert "PR already merged; skipping merge step." in lines
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."


def test_finish_task_data_enables_auto_merge_when_branch_policy_requires_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="review gate passed"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
        if args[:4] == ["gh", "pr", "merge", "https://example.invalid/pr/258"]:
            if "--auto" in args:
                return _completed(args)
            return _completed(
                args,
                returncode=1,
                stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
            )
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert data["lifecycle"]["lifecycle_state"] == "local-main-synced"
    assert any("Base branch policy requires auto-merge" in line for line in lines)
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."


def test_finish_task_data_continues_when_merge_timeout_or_failure_still_results_in_merged_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="review gate passed"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def make_fake_run_command(state_outputs: list[str]):
        state_calls = 0

        def fake_run_command(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal state_calls
            if args[:2] == ["git", "ls-remote"]:
                return _completed(args)
            if (
                args[:3] == ["gh", "pr", "view"]
                and len(args) >= 6
                and args[3].startswith("codex/task-")
                and "--json" in args
                and "url" in args
            ):
                return _completed(args, stdout="https://example.invalid/pr/258\n")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
                if "--json" in args and "title,body" in args:
                    return _completed(
                        args,
                        stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                    )
                if "--json" in args and "state" in args:
                    output = state_outputs[min(state_calls, len(state_outputs) - 1)]
                    state_calls += 1
                    return _completed(args, stdout=output)
                if "--json" in args and "isDraft" in args:
                    return _completed(args, stdout="false\n")
                if "--json" in args and "mergeCommit" in args:
                    return _completed(args, stdout="merge-commit-258\n")
            if args[:3] == ["git", "switch", "main"]:
                return _completed(args)
            if args[:3] == ["git", "pull", "--ff-only"]:
                return _completed(args, stdout="Already up to date.\n")
            if args[:3] == ["git", "cat-file", "-e"]:
                return _completed(args)
            if args[:4] == [
                "git",
                "show-ref",
                "--verify",
                "refs/heads/codex/task-258-canonical-finish",
            ]:
                return _completed(args, returncode=1)
            raise AssertionError(args)

        return fake_run_command

    monkeypatch.setattr(
        task_commands_module, "_run_command", make_fake_run_command(["OPEN\n", "MERGED\n"])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: (_ for _ in ()).throw(
            task_commands_module.CommandTimeoutError(args, 120)
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Merge command timed out, but PR is already MERGED; continuing." in lines

    monkeypatch.setattr(
        task_commands_module, "_run_command", make_fake_run_command(["OPEN\n", "MERGED\n"])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: _completed(
            args, returncode=1, stderr="merge exited after server-side completion"
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Merge step reported failure, but PR is already MERGED; continuing." in lines


def test_finish_task_data_covers_auto_merge_timeout_and_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="review gate passed"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def make_fake_run_command(stage: str):
        state_calls = 0

        def fake_run_command(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal state_calls
            if args[:2] == ["git", "ls-remote"]:
                return _completed(args)
            if (
                args[:3] == ["gh", "pr", "view"]
                and len(args) >= 6
                and args[3].startswith("codex/task-")
                and "--json" in args
                and "url" in args
            ):
                return _completed(args, stdout="https://example.invalid/pr/258\n")
            if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
                if "--json" in args and "title,body" in args:
                    return _completed(
                        args,
                        stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                    )
                if "--json" in args and "state" in args:
                    state_calls += 1
                    if stage == "auto-timeout-success":
                        if state_calls <= 2:
                            return _completed(args, stdout="OPEN\n")
                        return _completed(args, stdout="MERGED\n")
                    if stage == "auto-failure-merged":
                        if state_calls <= 2:
                            return _completed(args, stdout="OPEN\n")
                        return _completed(args, stdout="MERGED\n")
                    if stage == "auto-timeout-blocked":
                        return _completed(args, stdout="OPEN\n")
                    return _completed(args, stdout="OPEN\n")
                if "--json" in args and "isDraft" in args:
                    return _completed(args, stdout="false\n")
                if "--json" in args and "mergeCommit" in args:
                    return _completed(args, stdout="merge-commit-258\n")
            if args[:3] == ["git", "switch", "main"]:
                return _completed(args)
            if args[:3] == ["git", "pull", "--ff-only"]:
                return _completed(args, stdout="Already up to date.\n")
            if args[:3] == ["git", "cat-file", "-e"]:
                return _completed(args)
            if args[:4] == [
                "git",
                "show-ref",
                "--verify",
                "refs/heads/codex/task-258-canonical-finish",
            ]:
                return _completed(args, returncode=1)
            raise AssertionError(args)

        return fake_run_command

    def make_fake_run_command_with_timeout(stage: str):
        def fake_run_command_with_timeout(
            args: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if "--auto" not in args:
                return _completed(
                    args,
                    returncode=1,
                    stderr="the base branch policy prohibits the merge. add the `--auto` flag.",
                )
            if stage == "auto-timeout-success":
                raise task_commands_module.CommandTimeoutError(args, 120)
            if stage == "auto-timeout-blocked":
                raise task_commands_module.CommandTimeoutError(args, 120)
            if stage == "auto-failure-merged":
                return _completed(args, returncode=1, stderr="auto merge finished server-side")
            if stage == "auto-failure-blocked":
                return _completed(args, returncode=1, stderr="auto merge still blocked")
            if stage == "auto-merge-wait-timeout":
                return _completed(args)
            raise AssertionError(stage)

        return fake_run_command_with_timeout

    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-timeout-success"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-timeout-success"),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert "Auto-merge command timed out, but PR is already MERGED; continuing." in lines

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-timeout-blocked"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-timeout-blocked"),
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert (
        lines[0]
        == "Task finish blocked: auto-merge command did not exit cleanly after the review gate passed."
    )

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-failure-merged"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-failure-merged"),
    )
    monkeypatch.setattr(task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (True, []))
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-failure-blocked"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-failure-blocked"),
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: merge failed."
    assert lines[-1] == "auto merge still blocked"

    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        make_fake_run_command("auto-merge-wait-timeout"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        make_fake_run_command_with_timeout("auto-merge-wait-timeout"),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_pr_state", lambda **_kwargs: (False, ["still waiting"])
    )
    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: auto-merge did not complete before timeout."
    assert lines[-1] == "still waiting"


def test_finish_task_data_blocks_when_merge_fails_without_auto_merge_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_wait_for_required_checks", lambda **_kwargs: (True, [])
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_review_gate",
        lambda **_kwargs: _completed(["review"], stdout="review gate passed"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_current_required_checks_blocker",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        task_commands_module,
        "_unresolved_review_thread_lines",
        lambda **_kwargs: [],
    )

    state_calls = 0

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal state_calls
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                state_calls += 1
                return _completed(args, stdout="OPEN\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)
    monkeypatch.setattr(
        task_commands_module,
        "_run_command_with_timeout",
        lambda args, **_kwargs: _completed(
            args, returncode=1, stderr="merge failed for another reason"
        ),
    )

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == "Task finish blocked: merge failed."
    assert lines[-1] == "merge failed for another reason"


def test_finish_task_data_blocks_when_completion_verifier_fails_after_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-259-done-state-verifier",
            branch_task_id="TASK-259",
            task_id="TASK-259",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-259 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.VALIDATION_ERROR,
            {"lifecycle_state": "merged", "strict_complete": False},
            [
                "Task lifecycle: TASK-259",
                "- state: merged",
                "- strict complete: no",
                "Strict verification failed: repo-policy completion requires state `local-main-synced`.",
            ],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/259\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/259"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-259: done state verifier","body":"Primary-Task: TASK-259\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-259\n")
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-259-done-state-verifier",
        ]:
            return _completed(args, returncode=1)
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-259", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data["lifecycle"]["lifecycle_state"] == "merged"
    assert "completion verifier did not pass after merge" in lines[0]
    assert "horadus tasks lifecycle TASK-259 --strict" in lines[1]


@pytest.mark.parametrize(
    ("stage", "expected_first_line", "expected_last_line"),
    [
        (
            "merge-commit",
            "Task finish blocked: could not determine merge commit.",
            "Next action: Inspect the merged PR state in GitHub, then re-run `horadus tasks finish`.",
        ),
        (
            "switch-main",
            "Task finish blocked: switch failed",
            "Next action: Resolve the local git state and switch to `main`, then re-run `horadus tasks finish`.",
        ),
        (
            "pull-main",
            "Task finish blocked: pull failed",
            "Next action: Resolve the local `main` sync issue and re-run `horadus tasks finish`.",
        ),
        (
            "cat-file",
            "Task finish blocked: merge commit merge-commit-258 is not available locally after syncing main.",
            "Next action: Fetch/pull `main` successfully, then re-run `horadus tasks finish`.",
        ),
        (
            "delete-branch",
            "Task finish blocked: merged branch `codex/task-258-canonical-finish` still exists locally and could not be deleted.",
            "Next action: Delete `codex/task-258-canonical-finish` locally after syncing main, then re-run `horadus tasks finish`.",
        ),
    ],
)
def test_finish_task_data_blocks_on_post_merge_sync_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_first_line: str,
    expected_last_line: str,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                if stage == "merge-commit":
                    return _completed(args, returncode=1, stderr="merge commit unavailable")
                return _completed(args, stdout="merge-commit-258\n")
        if args[:3] == ["git", "switch", "main"]:
            if stage == "switch-main":
                return _completed(args, returncode=1, stderr="switch failed")
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            if stage == "pull-main":
                return _completed(args, returncode=1, stderr="pull failed")
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            if stage == "cat-file":
                return _completed(args, returncode=1)
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args, returncode=0 if stage == "delete-branch" else 1)
        if args[:3] == ["git", "branch", "-d"]:
            return _completed(args, returncode=1, stderr="delete failed")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["pr_url"] == "https://example.invalid/pr/258"
    assert lines[0] == expected_first_line
    assert lines[1] == expected_last_line


def test_finish_task_data_deletes_local_branch_when_it_still_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_resolve_finish_context",
        lambda *_args, **_kwargs: task_commands_module.FinishContext(
            branch_name="codex/task-258-canonical-finish",
            branch_task_id="TASK-258",
            task_id="TASK-258",
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_pr_scope_guard",
        lambda **_kwargs: _completed(
            ["scope"], stdout="PR scope guard passed: TASK-258 (Primary-Task)"
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "task_lifecycle_data",
        lambda *_args, **_kwargs: (
            task_commands_module.ExitCode.OK,
            {"lifecycle_state": "local-main-synced", "strict_complete": True},
            ["Task lifecycle: TASK-258", "- state: local-main-synced", "- strict complete: yes"],
        ),
    )

    def fake_run_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "ls-remote"]:
            return _completed(args, returncode=2)
        if (
            args[:3] == ["gh", "pr", "view"]
            and len(args) >= 6
            and args[3].startswith("codex/task-")
            and "--json" in args
            and "url" in args
        ):
            return _completed(args, stdout="https://example.invalid/pr/258\n")
        if args[:4] == ["gh", "pr", "view", "https://example.invalid/pr/258"]:
            if "--json" in args and "title,body" in args:
                return _completed(
                    args,
                    stdout='{"title":"TASK-258: canonical finish","body":"Primary-Task: TASK-258\\n"}\n',
                )
            if "--json" in args and "state" in args:
                return _completed(args, stdout="MERGED\n")
            if "--json" in args and "isDraft" in args:
                return _completed(args, stdout="false\n")
            if "--json" in args and "mergeCommit" in args:
                return _completed(args, stdout="merge-commit-258\n")
        if args[:3] == ["git", "switch", "main"]:
            return _completed(args)
        if args[:3] == ["git", "pull", "--ff-only"]:
            return _completed(args, stdout="Already up to date.\n")
        if args[:3] == ["git", "cat-file", "-e"]:
            return _completed(args)
        if args[:4] == [
            "git",
            "show-ref",
            "--verify",
            "refs/heads/codex/task-258-canonical-finish",
        ]:
            return _completed(args)
        if args[:3] == ["git", "branch", "-d"]:
            return _completed(args, stdout="Deleted branch.\n")
        raise AssertionError(args)

    monkeypatch.setattr(task_commands_module, "_run_command", fake_run_command)

    exit_code, data, lines = task_commands_module.finish_task_data("TASK-258", dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["merge_commit"] == "merge-commit-258"
    assert lines[-1] == "Task finish passed: merged merge-commit-258 and synced main."


def test_task_lifecycle_data_handles_finish_config_and_resolution_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad config")),
    )
    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data == {}
    assert lines == ["bad config"]

    monkeypatch.setattr(
        task_commands_module,
        "_finish_config",
        lambda **_kwargs: task_commands_module.FinishConfig(
            gh_bin="gh",
            git_bin="git",
            python_bin="python3",
            checks_timeout_seconds=1,
            checks_poll_seconds=0,
            review_timeout_seconds=1,
            review_poll_seconds=0,
            review_bot_login="bot",
            review_timeout_policy="allow",
        ),
    )
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    expected = (
        task_commands_module.ExitCode.NOT_FOUND,
        {"task_id": "TASK-259"},
        ["No local, remote, or PR lifecycle state found for TASK-259."],
    )
    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: expected,
    )

    assert (
        task_commands_module.task_lifecycle_data("TASK-259", strict=False, dry_run=False)
        == expected
    )

    monkeypatch.setattr(
        task_commands_module,
        "resolve_task_lifecycle",
        lambda *_args, **_kwargs: _task_snapshot(branch_name=None, pr=None),
    )
    exit_code, data, lines = task_commands_module.task_lifecycle_data(
        "TASK-259",
        strict=False,
        dry_run=False,
    )
    assert exit_code == task_commands_module.ExitCode.OK
    assert data["branch_name"] is None
    assert "- task branch:" not in "\n".join(lines)


def test_handle_show_returns_not_found_for_unknown_task() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-999"))

    assert result.exit_code == task_commands_module.ExitCode.NOT_FOUND
    assert result.error_lines == ["TASK-999 not found in tasks/BACKLOG.md"]


def test_handle_show_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="bad-task"))

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_show_returns_task_details() -> None:
    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-253"))

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.lines is not None
    assert result.lines[0].startswith("# TASK-253:")
    assert "Acceptance Criteria:" in result.lines


def test_handle_show_includes_spec_paths_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    record = task_repo_module.task_record("TASK-253")
    assert record is not None
    record.spec_paths = ["tasks/specs/253-coverage.md"]
    monkeypatch.setattr(task_commands_module, "task_record", lambda _task_id: record)

    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-253"))

    assert result.lines is not None
    assert "Specs:" in result.lines
    assert "- tasks/specs/253-coverage.md" in result.lines


def test_handle_show_skips_empty_optional_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-253",
        title="Coverage",
        priority="P0",
        estimate="2d",
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="active",
        sprint_lines=["- `TASK-253` Coverage"],
        spec_paths=[],
    )
    monkeypatch.setattr(task_commands_module, "task_record", lambda _task_id: record)

    result = task_commands_module.handle_show(argparse.Namespace(task_id="TASK-253"))

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
    assert "## Spec Contract Template" in result.lines
    assert "tasks/specs/TEMPLATE.md" in result.lines
    assert "## Suggested Workflow Commands" in result.lines
    assert "uv run --no-sync horadus tasks context-pack TASK-253" in result.lines
    assert "uv run --no-sync horadus tasks finish TASK-253" in result.lines
    assert "## Suggested Validation Commands" in result.lines
    assert result.data is not None
    assert result.data["spec_template_path"] == "tasks/specs/TEMPLATE.md"
    assert (
        result.data["suggested_workflow_commands"][0] == "uv run --no-sync horadus tasks preflight"
    )


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


def test_handle_safe_start_rejects_invalid_task_id() -> None:
    result = task_commands_module.handle_safe_start(
        argparse.Namespace(task_id="bad-task", name="coverage")
    )

    assert result.exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert result.error_lines == ["Invalid task id 'bad-task'. Expected TASK-XXX or XXX."]


def test_handle_safe_start_wraps_safe_start_task_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        task_commands_module,
        "safe_start_task_data",
        lambda _task_id, name, *, dry_run: (
            task_commands_module.ExitCode.OK,
            {"task_id": "TASK-253", "branch_name": f"codex/task-253-{name}", "dry_run": dry_run},
            ["safe start ok"],
        ),
    )

    result = task_commands_module.handle_safe_start(
        argparse.Namespace(task_id="TASK-253", name="coverage", dry_run=True)
    )

    assert result.exit_code == task_commands_module.ExitCode.OK
    assert result.data == {
        "task_id": "TASK-253",
        "branch_name": "codex/task-253-coverage",
        "dry_run": True,
    }
    assert result.lines == ["safe start ok"]


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


def test_recent_assessment_paths_skips_invalid_dates_and_honors_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment_dir = tmp_path / "artifacts" / "assessments" / "ops" / "daily"
    assessment_dir.mkdir(parents=True)
    (assessment_dir / "2026-03-06.md").write_text("ok", encoding="utf-8")
    (assessment_dir / "2026-02-10.md").write_text("old", encoding="utf-8")
    (assessment_dir / "invalid.md").write_text("bad", encoding="utf-8")

    class _FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 3, 7, tzinfo=UTC)

    monkeypatch.setattr(triage_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_commands_module, "datetime", _FakeDatetime)

    paths = triage_commands_module._recent_assessment_paths(lookback_days=7)

    assert paths == ["artifacts/assessments/ops/daily/2026-03-06.md"]


def test_compile_or_pattern_and_handle_collect_cover_optional_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert triage_commands_module._compile_or_pattern([" ", "alpha", "beta?"]) == "alpha|beta\\?"
    assert triage_commands_module._compile_or_pattern([" ", ""]) is None

    line_hit = task_repo_module.SearchHit(
        source="tasks/BACKLOG.md",
        line_number=1,
        line="TASK-253 hit",
    )
    active_task = task_repo_module.ActiveTask(
        task_id="TASK-253",
        title="Coverage task",
        requires_human=False,
        note=None,
        raw_line="- `TASK-253` Coverage task",
    )

    monkeypatch.setattr(triage_commands_module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(triage_commands_module, "completed_path", lambda: tmp_path / "COMPLETED.md")
    monkeypatch.setattr(
        triage_commands_module,
        "current_sprint_path",
        lambda: tmp_path / "CURRENT_SPRINT.md",
    )
    monkeypatch.setattr(
        triage_commands_module,
        "_recent_assessment_paths",
        lambda _lookback_days: ["artifacts/assessments/ops/daily/2026-03-06.md"],
    )
    monkeypatch.setattr(
        triage_commands_module,
        "line_search",
        lambda _path, _pattern: [line_hit],
    )
    monkeypatch.setattr(triage_commands_module, "parse_active_tasks", lambda: [active_task])
    monkeypatch.setattr(triage_commands_module, "parse_human_blockers", lambda **_kwargs: [])

    result = triage_commands_module.handle_collect(
        argparse.Namespace(
            keyword=["agent"],
            path=["src/core"],
            proposal_id=["PROPOSAL-1"],
            lookback_days=14,
        )
    )

    assert result.lines is not None
    assert "- paths=src/core" in result.lines
    assert "- proposal_ids=PROPOSAL-1" in result.lines
    assert all("overdue_tasks=" not in line for line in result.lines)
    assert result.data is not None
    assert result.data["searches"]["path_hits"][0]["source"] == "tasks/BACKLOG.md"
    assert result.data["searches"]["proposal_hits"][0]["line"] == "TASK-253 hit"


def test_blocker_urgency_defaults_to_pending_without_next_action() -> None:
    urgency = task_repo_module.blocker_urgency(
        last_touched="2026-03-01",
        next_action="",
        escalate_after_days=0,
        as_of=date(2026, 3, 7),
    )

    assert urgency.state == "pending"
    assert urgency.days_until_next_action is None
    assert urgency.is_overdue is False


def test_parse_human_blockers_skips_non_kv_chunks(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Human Blocker Metadata\n"
        "- TASK-253 | owner=alice | malformed | next_action=2026-03-10 | escalate_after_days=3\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert len(blockers) == 1
    assert blockers[0].owner == "alice"
    assert blockers[0].last_touched == ""


def test_parse_human_blockers_ignores_non_bullet_lines(tmp_path: Path) -> None:
    sprint_path = tmp_path / "CURRENT_SPRINT.md"
    sprint_path.write_text(
        "# Current Sprint\n\n## Human Blocker Metadata\n"
        "TASK-253 | owner=alice | last_touched=2026-03-06 | next_action=2026-03-10 | escalate_after_days=3\n"
        "- TASK-254 | owner=bob | last_touched=2026-03-06 | next_action=2026-03-10 | escalate_after_days=3\n",
        encoding="utf-8",
    )

    blockers = task_repo_module.parse_human_blockers(sprint_path)

    assert [blocker.task_id for blocker in blockers] == ["TASK-254"]


def test_parse_task_block_stops_description_at_unknown_heading() -> None:
    raw_block = """### TASK-253: Coverage
**Priority**: P0
**Estimate**: 2d
This is part of the description.
**Unexpected**
This should not stay in the description.
"""

    record = task_repo_module._parse_task_block("TASK-253", "Coverage", raw_block)

    assert record.description == ["This is part of the description."]


def test_task_record_stays_backlog_without_sprint_or_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = task_repo_module.TaskRecord(
        task_id="TASK-253",
        title="Coverage",
        priority="P0",
        estimate="2d",
        description=[],
        files=[],
        acceptance_criteria=[],
        assessment_refs=[],
        raw_block="raw",
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
    )
    monkeypatch.setattr(task_repo_module, "backlog_task_records", lambda: {"TASK-253": record})
    monkeypatch.setattr(task_repo_module, "sprint_lines_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "spec_paths_for_task", lambda _task_id: [])
    monkeypatch.setattr(task_repo_module, "is_task_completed", lambda _task_id: False)

    resolved = task_repo_module.task_record("TASK-253")

    assert resolved is not None
    assert resolved.status == "backlog"
