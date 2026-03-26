from __future__ import annotations

from pathlib import Path

import pytest

from tools.horadus.python.horadus_cli.app import _build_parser, main

pytestmark = pytest.mark.unit


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


def test_build_parser_accepts_task_automation_lock_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "automation-lock",
            "check",
            "--automation-id",
            "horadus-sprint-autopilot",
            "--format",
            "json",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "automation-lock"
    assert args.automation_lock_command == "check"
    assert args.automation_id == "horadus-sprint-autopilot"
    assert args.output_format == "json"


def test_build_parser_accepts_task_local_review_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "tasks",
            "local-review",
            "--provider",
            "codex",
            "--base",
            "main",
            "--instructions",
            "Focus on workflow regressions.",
            "--allow-provider-fallback",
            "--save-raw-output",
            "--usefulness",
            "follow-up-changes",
            "--format",
            "json",
        ]
    )

    assert args.command == "tasks"
    assert args.tasks_command == "local-review"
    assert args.provider == "codex"
    assert args.base == "main"
    assert args.instructions == "Focus on workflow regressions."
    assert args.allow_provider_fallback is True
    assert args.save_raw_output is True
    assert args.usefulness == "follow-up-changes"
    assert args.output_format == "json"


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
            "tier2-gpt5-mini-medium",
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
    assert args.config == ["tier2-gpt5-mini-medium"]
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


def test_build_parser_uses_default_embedding_lineage_model_from_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "EMBEDDING_MODEL=text-embedding-3-large\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    parser = _build_parser()
    args = parser.parse_args(["eval", "embedding-lineage"])

    assert args.target_model == "text-embedding-3-large"


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
            "tools/horadus/python/horadus_cli/app.py",
            "--proposal-id",
            "PROPOSAL-2026-03-02-agents-cross-role-promotion-dedupe",
            "--lookback-days",
            "7",
            "--assessment-path-limit",
            "3",
            "--include-raw",
            "--format",
            "json",
        ]
    )

    assert args.command == "triage"
    assert args.triage_command == "collect"
    assert args.keyword == ["agent"]
    assert args.path == ["tools/horadus/python/horadus_cli/app.py"]
    assert args.proposal_id == ["PROPOSAL-2026-03-02-agents-cross-role-promotion-dedupe"]
    assert args.lookback_days == 7
    assert args.assessment_path_limit == 3
    assert args.include_assessment_paths is False
    assert args.include_raw is True
    assert args.output_format == "json"


def test_build_parser_accepts_triage_collect_full_assessment_paths() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "triage",
            "collect",
            "--include-assessment-paths",
            "--format",
            "json",
        ]
    )

    assert args.command == "triage"
    assert args.triage_command == "collect"
    assert args.include_assessment_paths is True
    assert args.assessment_path_limit is None


def test_build_parser_rejects_non_positive_assessment_path_limit() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "triage",
                "collect",
                "--assessment-path-limit",
                "0",
            ]
        )


def test_build_parser_preserves_root_flags_for_ops_command() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--format", "json", "--dry-run", "pipeline", "dry-run"])

    assert args.command == "pipeline"
    assert args.pipeline_command == "dry-run"
    assert args.dry_run is True
    assert args.output_format == "json"


def test_horadus_app_main_returns_1_without_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main([])

    assert result == 1
    assert "usage:" in capsys.readouterr().out


def test_cli_entrypoint_is_owned_by_tools_package() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'horadus = "tools.horadus.python.horadus_cli.app:main"' in pyproject
