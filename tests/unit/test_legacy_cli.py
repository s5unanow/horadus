from __future__ import annotations

import argparse
import io
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib import error as urllib_error

import pytest

import src.core.calibration_dashboard as calibration_dashboard_module
import src.core.dashboard_export as dashboard_export_module
import src.core.embedding_lineage as embedding_lineage_module
import src.core.migration_parity as migration_parity_module
import src.core.source_freshness as source_freshness_module
import src.eval.audit as audit_module
import src.eval.benchmark as benchmark_module
import src.eval.replay as replay_module
import src.eval.taxonomy_validation as taxonomy_validation_module
import src.eval.vector_benchmark as vector_benchmark_module
import src.horadus_cli.legacy as legacy_module
import src.processing.dry_run_pipeline as dry_run_pipeline_module
import src.storage.database as database_module
from src.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit

_ORIGINAL_HTTP_GET = legacy_module._http_get
_ORIGINAL_HTTP_GET_JSON = legacy_module._http_get_json
_ORIGINAL_DOCTOR_CHECK_DATABASE = legacy_module._doctor_check_database
_ORIGINAL_DOCTOR_CHECK_REDIS = legacy_module._doctor_check_redis


@pytest.fixture(autouse=True)
def reset_legacy_helpers() -> None:
    legacy_module._http_get = _ORIGINAL_HTTP_GET
    legacy_module._http_get_json = _ORIGINAL_HTTP_GET_JSON
    legacy_module._doctor_check_database = _ORIGINAL_DOCTOR_CHECK_DATABASE
    legacy_module._doctor_check_redis = _ORIGINAL_DOCTOR_CHECK_REDIS


def test_parse_iso_datetime_and_embedding_count_helpers() -> None:
    assert legacy_module._parse_iso_datetime(None) is None
    assert legacy_module._parse_iso_datetime("  ") is None
    assert legacy_module._parse_iso_datetime("2026-03-08T12:00:00Z") == datetime(
        2026, 3, 8, 12, 0, tzinfo=UTC
    )

    empty_summary = SimpleNamespace(model_counts=[])
    populated_summary = SimpleNamespace(
        model_counts=[
            SimpleNamespace(model="text-embedding-3-large", count=2),
            SimpleNamespace(model="legacy", count=1),
        ]
    )

    assert legacy_module._format_embedding_model_counts(empty_summary) == "none"
    assert (
        legacy_module._format_embedding_model_counts(populated_summary)
        == "text-embedding-3-large=2, legacy=1"
    )


@pytest.mark.asyncio
async def test_collect_trends_status_handles_empty_and_populated_dashboards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboard = SimpleNamespace(trend_movements=[])

    class FakeService:
        def __init__(self, _session: object) -> None:
            pass

        async def build_dashboard(self) -> object:
            return dashboard

    @asynccontextmanager
    async def fake_session_maker():
        yield object()

    monkeypatch.setattr(database_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(calibration_dashboard_module, "CalibrationDashboardService", FakeService)

    data, lines = await legacy_module._collect_trends_status(limit=3)

    assert data == {"trends": []}
    assert lines == ["No active trends found."]

    movement = SimpleNamespace(
        trend_id="trend-1",
        trend_name="Alpha",
        current_probability=0.42,
        weekly_change=-0.05,
        risk_level="guarded",
        top_movers_7d=["diplomacy"],
        movement_chart="._^",
    )
    dashboard.trend_movements = [movement]

    data, lines = await legacy_module._collect_trends_status(limit=3)

    assert data["trends"][0]["trend_name"] == "Alpha"
    assert any("Top movers: diplomacy" in line for line in lines)


@pytest.mark.asyncio
async def test_collect_dashboard_export_returns_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dashboard = SimpleNamespace()

    class FakeService:
        def __init__(self, _session: object) -> None:
            pass

        async def build_dashboard(self) -> object:
            return dashboard

    @asynccontextmanager
    async def fake_session_maker():
        yield object()

    result = SimpleNamespace(
        json_path=tmp_path / "dashboard.json",
        html_path=tmp_path / "dashboard.html",
        latest_json_path=tmp_path / "latest.json",
        latest_html_path=tmp_path / "latest.html",
        index_html_path=tmp_path / "index.html",
    )

    monkeypatch.setattr(database_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(calibration_dashboard_module, "CalibrationDashboardService", FakeService)
    monkeypatch.setattr(
        dashboard_export_module, "export_calibration_dashboard", lambda *_args, **_kwargs: result
    )

    data, lines = await legacy_module._collect_dashboard_export(str(tmp_path), 5)

    assert data["json_path"].endswith("dashboard.json")
    assert any("Hosting index:" in line for line in lines)


@pytest.mark.asyncio
async def test_collect_eval_wrappers_pass_normalized_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    benchmark_calls: dict[str, object] = {}
    replay_calls: dict[str, object] = {}
    vector_calls: dict[str, object] = {}

    async def fake_benchmark(**kwargs):
        benchmark_calls.update(kwargs)
        return tmp_path / "benchmark.json"

    async def fake_replay(**kwargs):
        replay_calls.update(kwargs)
        return tmp_path / "replay.json"

    async def fake_vector(**kwargs):
        vector_calls.update(kwargs)
        return tmp_path / "vector.json"

    monkeypatch.setattr(benchmark_module, "run_gold_set_benchmark", fake_benchmark)
    monkeypatch.setattr(replay_module, "run_historical_replay_comparison", fake_replay)
    monkeypatch.setattr(vector_benchmark_module, "run_vector_retrieval_benchmark", fake_vector)
    monkeypatch.setattr(legacy_module.settings, "OPENAI_API_KEY", "token")

    benchmark_args = SimpleNamespace(
        gold_set="gold.jsonl",
        output_dir=str(tmp_path),
        trend_config_dir="config/trends",
        max_items=0,
        config=["baseline"],
        require_human_verified=True,
        dispatch_mode="batch",
        request_priority="flex",
    )
    replay_args = SimpleNamespace(
        output_dir=str(tmp_path),
        champion_config="stable",
        challenger_config="fast",
        trend_id="550e8400-e29b-41d4-a716-446655440000",
        start_date="2026-03-01T00:00:00Z",
        end_date="2026-03-07T00:00:00Z",
        days=0,
    )
    vector_args = SimpleNamespace(
        output_dir=str(tmp_path),
        database_url="postgres://db",
        dataset_size=50,
        query_count=2,
        dimensions=4,
        top_k=0,
        similarity_threshold=0.9,
        seed=7,
    )

    _, _, benchmark_exit = await legacy_module._collect_eval_benchmark(benchmark_args)
    _, _, replay_exit = await legacy_module._collect_eval_replay(replay_args)
    _, _, vector_exit = await legacy_module._collect_eval_vector_benchmark(vector_args)

    assert benchmark_calls["max_items"] == 1
    assert replay_calls["trend_id"].hex == "550e8400e29b41d4a716446655440000"
    assert replay_calls["start_date"] == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert replay_calls["days"] == 1
    assert vector_calls["dataset_size"] == 100
    assert vector_calls["query_count"] == 10
    assert vector_calls["dimensions"] == 8
    assert vector_calls["top_k"] == 1
    assert benchmark_exit == replay_exit == vector_exit == ExitCode.OK


@pytest.mark.asyncio
async def test_collect_embedding_lineage_and_source_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = SimpleNamespace(
        entity="raw_items",
        vectors=5,
        target_model_vectors=3,
        vectors_other_models=1,
        vectors_missing_model=1,
        reembed_scope=2,
        model_counts=[SimpleNamespace(model="canonical", count=3)],
    )
    report = SimpleNamespace(
        target_model="canonical",
        raw_items=summary,
        events=summary,
        total_vectors=10,
        total_reembed_scope=4,
        has_mixed_populations=True,
    )

    freshness_report = SimpleNamespace(
        checked_at=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
        stale_multiplier=2.0,
        stale_count=2,
        stale_collectors=["rss", "gdelt", "telegram"],
        rows=[
            SimpleNamespace(
                collector="rss",
                source_name="Feed A",
                is_stale=True,
                age_seconds=3600,
                stale_after_seconds=1800,
                last_fetched_at=datetime(2026, 3, 8, 11, 0, tzinfo=UTC),
            )
        ],
    )

    @asynccontextmanager
    async def fake_session_maker():
        yield object()

    monkeypatch.setattr(database_module, "async_session_maker", fake_session_maker)

    async def fake_embedding_lineage_report(_session: object, target_model: str) -> object:
        del target_model
        return report

    async def fake_source_freshness_report(
        session: object, stale_multiplier: float | None
    ) -> object:
        del session, stale_multiplier
        return freshness_report

    monkeypatch.setattr(
        embedding_lineage_module,
        "build_embedding_lineage_report",
        fake_embedding_lineage_report,
    )
    monkeypatch.setattr(
        source_freshness_module,
        "build_source_freshness_report",
        fake_source_freshness_report,
    )
    monkeypatch.setattr(legacy_module.settings, "ENABLE_RSS_INGESTION", True)
    monkeypatch.setattr(legacy_module.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(legacy_module.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 1)

    lineage_args = SimpleNamespace(target_model="canonical", fail_on_mixed=True)
    freshness_args = SimpleNamespace(stale_multiplier=2.0, fail_on_stale=True)

    lineage_data, lineage_lines, lineage_exit = await legacy_module._collect_eval_embedding_lineage(
        lineage_args
    )
    (
        freshness_data,
        freshness_lines,
        freshness_exit,
    ) = await legacy_module._collect_eval_source_freshness(freshness_args)

    assert lineage_data["has_mixed_populations"] is True
    assert any("mixed_population=true" in line for line in lineage_lines)
    assert lineage_exit == ExitCode.VALIDATION_ERROR
    assert freshness_data["catchup_candidates"] == ["rss"]
    assert any("stale_count=2" in line for line in freshness_lines)
    assert freshness_exit == ExitCode.VALIDATION_ERROR


def test_collect_eval_audit_validate_taxonomy_and_pipeline_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        audit_module,
        "run_gold_set_audit",
        lambda **_kwargs: SimpleNamespace(output_path=tmp_path / "audit.json", warnings=["warn"]),
    )
    monkeypatch.setattr(
        taxonomy_validation_module,
        "run_trend_taxonomy_validation",
        lambda **_kwargs: SimpleNamespace(
            output_path=tmp_path / "taxonomy.json",
            warnings=["warn"],
            errors=["err"],
        ),
    )
    monkeypatch.setattr(
        dry_run_pipeline_module,
        "run_pipeline_dry_run",
        lambda **_kwargs: tmp_path / "pipeline.json",
    )

    audit_args = SimpleNamespace(
        gold_set="gold.jsonl", output_dir=str(tmp_path), max_items=0, fail_on_warnings=True
    )
    taxonomy_args = SimpleNamespace(
        trend_config_dir="config/trends",
        gold_set="gold.jsonl",
        output_dir=str(tmp_path),
        max_items=0,
        tier1_trend_mode="strict",
        signal_type_mode="warn",
        unknown_trend_mode="warn",
        fail_on_warnings=False,
    )
    pipeline_args = SimpleNamespace(
        fixture_path="fixture.jsonl",
        trend_config_dir="config/trends",
        output_path=str(tmp_path / "pipeline.json"),
    )

    audit_data, audit_lines, audit_exit = legacy_module._collect_eval_audit(audit_args)
    taxonomy_data, taxonomy_lines, taxonomy_exit = legacy_module._collect_eval_validate_taxonomy(
        taxonomy_args
    )
    pipeline_data, pipeline_lines, pipeline_exit = legacy_module._collect_pipeline_dry_run(
        pipeline_args
    )

    assert audit_data["warnings"] == ["warn"]
    assert any("Audit warnings:" in line for line in audit_lines)
    assert audit_exit == ExitCode.VALIDATION_ERROR
    assert taxonomy_data["errors"] == ["err"]
    assert any("Taxonomy validation errors:" in line for line in taxonomy_lines)
    assert taxonomy_exit == ExitCode.VALIDATION_ERROR
    assert pipeline_data["artifact_path"].endswith("pipeline.json")
    assert pipeline_lines == [f"Dry-run artifact: {tmp_path / 'pipeline.json'}"]
    assert pipeline_exit == ExitCode.OK


def test_http_helpers_cover_success_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResponseContext:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> ResponseContext:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    def urlopen_success(_request, timeout=None):
        del timeout
        return ResponseContext(200, b'{"ok": true}')

    monkeypatch.setattr(
        legacy_module.urllib_request,
        "urlopen",
        urlopen_success,
    )

    assert legacy_module._http_get("https://example.com", timeout_seconds=1.0) == 200
    assert legacy_module._http_get_json("https://example.com", timeout_seconds=1.0) == (
        200,
        {"ok": True},
    )

    http_error = urllib_error.HTTPError(
        "https://example.com",
        404,
        "bad",
        {},
        io.BytesIO(b'{"detail": "missing"}'),
    )

    def urlopen_http_error(_request, timeout=None):
        del timeout
        return (_ for _ in ()).throw(http_error)

    monkeypatch.setattr(
        legacy_module.urllib_request,
        "urlopen",
        urlopen_http_error,
    )

    assert legacy_module._http_get("https://example.com", timeout_seconds=1.0) == 404
    assert legacy_module._http_get_json("https://example.com", timeout_seconds=1.0) == (
        404,
        {"detail": "missing"},
    )

    def urlopen_url_error(_request, timeout=None):
        del timeout
        return (_ for _ in ()).throw(urllib_error.URLError("down"))

    monkeypatch.setattr(
        legacy_module.urllib_request,
        "urlopen",
        urlopen_url_error,
    )
    assert legacy_module._http_get("https://example.com", timeout_seconds=1.0) == 0
    assert legacy_module._http_get_json("https://example.com", timeout_seconds=1.0) == (0, None)


def test_agent_smoke_helpers_cover_failure_and_auth_hint_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        legacy_module, "_http_get", lambda url, **_kwargs: 500 if url.endswith("/health") else 0
    )
    exit_code, lines, data = legacy_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines == ["FAIL /health 500"]
    assert data == {"health_status": 500}

    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 401,
    }
    monkeypatch.setattr(legacy_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(legacy_module, "_http_get_json", lambda _url, **_kwargs: (200, None))

    exit_code, lines, data = legacy_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )

    assert exit_code == ExitCode.OK
    assert lines[-1].endswith("auth_enforced_without_key (unknown)")
    assert data["auth_hint"] == "unknown"


@pytest.mark.asyncio
async def test_doctor_dependency_checks_cover_success_failure_and_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(*_args, **_kwargs) -> None:
        return None

    session = SimpleNamespace(execute=execute)

    @asynccontextmanager
    async def fake_session_maker():
        yield session

    async def healthy_migration(_session: object) -> dict[str, str]:
        return {"status": "healthy", "message": "ok"}

    async def failing_migration(_session: object) -> dict[str, str]:
        return {"status": "drifted", "message": "missing migration"}

    monkeypatch.setattr(database_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(migration_parity_module, "check_migration_parity", healthy_migration)
    monkeypatch.setattr(legacy_module.settings, "DATABASE_URL", "postgres://db")
    assert await legacy_module._doctor_check_database(0.2) == (
        "PASS",
        "database connectivity ok; migration parity healthy",
    )

    monkeypatch.setattr(migration_parity_module, "check_migration_parity", failing_migration)
    status, message = await legacy_module._doctor_check_database(0.2)
    assert status == "FAIL"
    assert "drifted" in message

    class FakeRedisClient:
        async def ping(self) -> None:
            return None

        async def close(self) -> None:
            return None

    fake_redis_module = ModuleType("redis.asyncio")
    fake_redis_module.from_url = lambda _url: FakeRedisClient()
    monkeypatch.setattr(legacy_module.settings, "REDIS_URL", "redis://cache")
    import builtins

    original_import = builtins.__import__
    fake_redis_package = ModuleType("redis")
    fake_redis_package.asyncio = fake_redis_module
    monkeypatch.setitem(sys.modules, "redis", fake_redis_package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_redis_module)
    assert await legacy_module._doctor_check_redis(0.2) == ("PASS", "redis connectivity ok")

    def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis.asyncio":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert await legacy_module._doctor_check_redis(0.2) == ("FAIL", "redis client is not installed")


def test_doctor_helpers_and_command_result_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert legacy_module._doctor_check_required_hooks()[0] == "FAIL"

    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        path = hooks_dir / hook_name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)

    assert legacy_module._doctor_check_required_hooks()[0] == "PASS"
    assert legacy_module._is_loopback_host("localhost") is True
    assert legacy_module._is_loopback_host("example.com") is False

    monkeypatch.setattr(legacy_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(legacy_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(legacy_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(legacy_module.settings, "AGENT_ALLOW_NON_LOOPBACK", False)
    monkeypatch.setattr(legacy_module.settings, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(legacy_module.settings, "API_AUTH_ENABLED", False)
    refusals = legacy_module._doctor_safety_refusals()
    assert "agent profile is not allowed in production" in refusals
    assert any("loopback API_HOST" in refusal for refusal in refusals)
    assert any("API_AUTH_ENABLED=false" in refusal for refusal in refusals)

    async def fake_db(_timeout: float) -> tuple[str, str]:
        return ("PASS", "db ok")

    async def fake_redis(_timeout: float) -> tuple[str, str]:
        return ("FAIL", "redis down")

    monkeypatch.setattr(legacy_module, "_doctor_check_database", fake_db)
    monkeypatch.setattr(legacy_module, "_doctor_check_redis", fake_redis)
    monkeypatch.setattr(legacy_module, "_doctor_safety_refusals", lambda: ["blocked"])
    monkeypatch.setattr(legacy_module, "_doctor_check_required_hooks", lambda: ("PASS", "hooks ok"))

    data, lines, exit_code = legacy_module._collect_doctor(0.2)
    assert data["database"]["status"] == "PASS"
    assert any("SAFETY_REFUSALS:" in line for line in lines)
    assert exit_code == ExitCode.VALIDATION_ERROR

    sync_result = legacy_module._sync_result({"ok": True}, ["line"], ExitCode.OK)
    assert sync_result.data == {"ok": True}

    async def async_lines():
        return ({"value": 1}, ["line"])

    async def async_exit():
        return ({"value": 2}, ["line"], ExitCode.VALIDATION_ERROR)

    assert legacy_module._async_result(async_lines()).data == {"value": 1}
    assert (
        legacy_module._async_result_with_exit(async_exit()).exit_code == ExitCode.VALIDATION_ERROR
    )

    monkeypatch.setattr(
        legacy_module,
        "_agent_smoke_checks",
        lambda **_kwargs: (ExitCode.OK, ["ok"], {"health_status": 200}),
    )
    handled = legacy_module._handle_agent_smoke(
        SimpleNamespace(base_url="http://127.0.0.1", timeout_seconds=0, api_key=" token ")
    )
    assert handled.exit_code == ExitCode.OK
    assert handled.data["health_status"] == 200


def test_legacy_leaf_options_and_register_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark_module, "available_configs", lambda: {"baseline": object()})
    monkeypatch.setattr(replay_module, "available_replay_configs", lambda: {"stable": object()})

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    legacy_module.register_legacy_commands(subparsers)

    args = parser.parse_args(["eval", "benchmark", "--config", "baseline", "--format", "json"])
    assert args.command == "eval"
    assert args.eval_command == "benchmark"
    assert args.config == ["baseline"]
    assert args.output_format == "json"

    args = parser.parse_args(["agent", "smoke", "--dry-run"])
    assert args.command == "agent"
    assert args.agent_command == "smoke"
    assert args.dry_run is True
