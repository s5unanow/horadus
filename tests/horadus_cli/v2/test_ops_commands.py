from __future__ import annotations

import argparse
import io
import json
import runpy
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib import error as urllib_error

import pytest

import src.cli_runtime as runtime_module
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
import src.processing.dry_run_pipeline as dry_run_pipeline_module
import src.storage.database as database_module
import tools.horadus.python.horadus_cli.ops_commands as ops_module
from tools.horadus.python.horadus_cli.result import ExitCode

pytestmark = pytest.mark.unit

_ORIGINAL_HTTP_GET = ops_module._http_get
_ORIGINAL_HTTP_GET_JSON = ops_module._http_get_json
_ORIGINAL_DOCTOR_CHECK_DATABASE = runtime_module._doctor_check_database
_ORIGINAL_DOCTOR_CHECK_REDIS = runtime_module._doctor_check_redis


@pytest.fixture(autouse=True)
def reset_ops_helpers() -> None:
    ops_module._http_get = _ORIGINAL_HTTP_GET
    ops_module._http_get_json = _ORIGINAL_HTTP_GET_JSON
    runtime_module._doctor_check_database = _ORIGINAL_DOCTOR_CHECK_DATABASE
    runtime_module._doctor_check_redis = _ORIGINAL_DOCTOR_CHECK_REDIS


def test_parse_iso_datetime_and_embedding_count_helpers() -> None:
    assert ops_module._parse_iso_datetime(None) is None
    assert ops_module._parse_iso_datetime("  ") is None
    assert ops_module._parse_iso_datetime("2026-03-08T12:00:00Z") == datetime(
        2026, 3, 8, 12, 0, tzinfo=UTC
    )
    assert ops_module._parse_iso_datetime("2026-03-08T14:00:00+02:00") == datetime(
        2026, 3, 8, 14, 0, tzinfo=datetime.fromisoformat("2026-03-08T14:00:00+02:00").tzinfo
    )

    empty_summary = SimpleNamespace(model_counts=[])
    populated_summary = SimpleNamespace(
        model_counts=[
            SimpleNamespace(model="text-embedding-3-large", count=2),
            SimpleNamespace(model="legacy", count=1),
        ]
    )

    assert ops_module._format_embedding_model_counts(empty_summary) == "none"
    assert (
        ops_module._format_embedding_model_counts(populated_summary)
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

    data, lines = await runtime_module._collect_trends_status(limit=3)

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

    data, lines = await runtime_module._collect_trends_status(limit=3)

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

    data, lines = await runtime_module._collect_dashboard_export(str(tmp_path), 5)

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
    monkeypatch.setattr(runtime_module.settings, "OPENAI_API_KEY", "stub")

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

    _, _, benchmark_exit = await runtime_module._collect_eval_benchmark(benchmark_args)
    _, _, replay_exit = await runtime_module._collect_eval_replay(replay_args)
    _, _, vector_exit = await runtime_module._collect_eval_vector_benchmark(vector_args)

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
    monkeypatch.setattr(runtime_module.settings, "ENABLE_RSS_INGESTION", True)
    monkeypatch.setattr(runtime_module.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(runtime_module.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 1)

    lineage_args = SimpleNamespace(target_model="canonical", fail_on_mixed=True)
    freshness_args = SimpleNamespace(stale_multiplier=2.0, fail_on_stale=True)

    (
        lineage_data,
        lineage_lines,
        lineage_exit,
    ) = await runtime_module._collect_eval_embedding_lineage(lineage_args)
    (
        freshness_data,
        freshness_lines,
        freshness_exit,
    ) = await runtime_module._collect_eval_source_freshness(freshness_args)

    assert lineage_data["has_mixed_populations"] is True
    assert any("mixed_population=true" in line for line in lineage_lines)
    assert lineage_exit == ExitCode.VALIDATION_ERROR
    assert freshness_data["catchup_candidates"] == ["rss"]
    assert any("stale_count=2" in line for line in freshness_lines)
    assert freshness_exit == ExitCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_collect_source_freshness_without_enabled_collectors_has_no_catchup_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    freshness_report = SimpleNamespace(
        checked_at=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
        stale_multiplier=2.0,
        stale_count=1,
        stale_collectors=["rss", "gdelt"],
        rows=[],
    )

    @asynccontextmanager
    async def fake_session_maker():
        yield object()

    async def fake_source_freshness_report(
        session: object, stale_multiplier: float | None
    ) -> object:
        del session, stale_multiplier
        return freshness_report

    monkeypatch.setattr(database_module, "async_session_maker", fake_session_maker)
    monkeypatch.setattr(
        source_freshness_module,
        "build_source_freshness_report",
        fake_source_freshness_report,
    )
    monkeypatch.setattr(runtime_module.settings, "ENABLE_RSS_INGESTION", False)
    monkeypatch.setattr(runtime_module.settings, "ENABLE_GDELT_INGESTION", False)
    monkeypatch.setattr(runtime_module.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 2)

    freshness_data, _lines, _exit = await runtime_module._collect_eval_source_freshness(
        SimpleNamespace(stale_multiplier=2.0, fail_on_stale=False)
    )

    assert freshness_data["catchup_candidates"] == []


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

    audit_data, audit_lines, audit_exit = runtime_module._collect_eval_audit(audit_args)
    taxonomy_data, taxonomy_lines, taxonomy_exit = runtime_module._collect_eval_validate_taxonomy(
        taxonomy_args
    )
    pipeline_data, pipeline_lines, pipeline_exit = runtime_module._collect_pipeline_dry_run(
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


def test_collect_eval_audit_and_taxonomy_without_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        audit_module,
        "run_gold_set_audit",
        lambda **_kwargs: SimpleNamespace(output_path=tmp_path / "audit.json", warnings=[]),
    )
    monkeypatch.setattr(
        taxonomy_validation_module,
        "run_trend_taxonomy_validation",
        lambda **_kwargs: SimpleNamespace(
            output_path=tmp_path / "taxonomy.json",
            warnings=[],
            errors=[],
        ),
    )

    audit_data, audit_lines, audit_exit = runtime_module._collect_eval_audit(
        SimpleNamespace(
            gold_set="gold.jsonl", output_dir=str(tmp_path), max_items=0, fail_on_warnings=False
        )
    )
    taxonomy_data, taxonomy_lines, taxonomy_exit = runtime_module._collect_eval_validate_taxonomy(
        SimpleNamespace(
            trend_config_dir="config/trends",
            gold_set="gold.jsonl",
            output_dir=str(tmp_path),
            max_items=0,
            tier1_trend_mode="strict",
            signal_type_mode="warn",
            unknown_trend_mode="warn",
            fail_on_warnings=False,
        )
    )

    assert audit_data["warnings"] == []
    assert not any("Audit warnings:" in line for line in audit_lines)
    assert audit_exit == ExitCode.OK
    assert taxonomy_data["warnings"] == []
    assert taxonomy_data["errors"] == []
    assert not any("Taxonomy validation warnings:" in line for line in taxonomy_lines)
    assert taxonomy_exit == ExitCode.OK


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
        ops_module.urllib_request,
        "urlopen",
        urlopen_success,
    )

    assert ops_module._http_get("https://example.com", timeout_seconds=1.0) == 200
    assert ops_module._http_get_json("https://example.com", timeout_seconds=1.0) == (
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
        ops_module.urllib_request,
        "urlopen",
        urlopen_http_error,
    )

    assert ops_module._http_get("https://example.com", timeout_seconds=1.0) == 404
    assert ops_module._http_get_json("https://example.com", timeout_seconds=1.0) == (
        404,
        {"detail": "missing"},
    )

    def urlopen_url_error(_request, timeout=None):
        del timeout
        return (_ for _ in ()).throw(urllib_error.URLError("down"))

    monkeypatch.setattr(
        ops_module.urllib_request,
        "urlopen",
        urlopen_url_error,
    )
    assert ops_module._http_get("https://example.com", timeout_seconds=1.0) == 0
    assert ops_module._http_get_json("https://example.com", timeout_seconds=1.0) == (0, None)


def test_eval_taxonomy_and_http_json_cover_warning_and_non_dict_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        trend_config_dir="config/trends",
        gold_set="gold.jsonl",
        output_dir=str(tmp_path),
        max_items=0,
        tier1_trend_mode="strict",
        signal_type_mode="warn",
        unknown_trend_mode="warn",
        fail_on_warnings=True,
    )

    monkeypatch.setattr(
        taxonomy_validation_module,
        "run_trend_taxonomy_validation",
        lambda **_kwargs: SimpleNamespace(
            output_path=tmp_path / "taxonomy.json",
            warnings=["warn"],
            errors=[],
        ),
    )

    data, lines, exit_code = runtime_module._collect_eval_validate_taxonomy(args)

    assert data["warnings"] == ["warn"]
    assert data["errors"] == []
    assert any("Taxonomy validation warnings:" in line for line in lines)
    assert exit_code == ExitCode.VALIDATION_ERROR

    class ResponseContext:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def urlopen_list_payload(_request, timeout=None):
        del timeout
        return ResponseContext(200, b'["not-a-dict"]')

    monkeypatch.setattr(ops_module.urllib_request, "urlopen", urlopen_list_payload)
    assert ops_module._http_get_json("https://example.com", timeout_seconds=1.0) == (200, None)

    invalid_http_error = urllib_error.HTTPError(
        "https://example.com",
        400,
        "bad",
        {},
        io.BytesIO(b"not-json"),
    )

    def urlopen_invalid_http_error(_request, timeout=None):
        del timeout
        return (_ for _ in ()).throw(invalid_http_error)

    monkeypatch.setattr(ops_module.urllib_request, "urlopen", urlopen_invalid_http_error)
    assert ops_module._http_get_json("https://example.com", timeout_seconds=1.0) == (400, None)


def test_agent_smoke_helpers_cover_failure_and_auth_hint_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ops_module, "_http_get", lambda url, **_kwargs: 500 if url.endswith("/health") else 0
    )
    exit_code, lines, data = ops_module._agent_smoke_checks(
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
    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (200, None))

    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )

    assert exit_code == ExitCode.OK
    assert lines[-1].endswith("auth_enforced_without_key (unknown)")
    assert data["auth_hint"] == "unknown"

    monkeypatch.setattr(ops_module, "_http_get", lambda _url, **_kwargs: 200)
    monkeypatch.setattr(ops_module, "_http_get_json", lambda _url, **_kwargs: (0, None))
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key=None,
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /openapi.json connection_error"
    assert data == {"health_status": 200, "openapi_status": 0}

    statuses = {
        "http://127.0.0.1:8000/health": 200,
        "http://127.0.0.1:8000/api/v1/trends": 403,
    }
    monkeypatch.setattr(ops_module, "_http_get", lambda url, **_kwargs: statuses[url])
    monkeypatch.setattr(
        ops_module, "_http_get_json", lambda _url, **_kwargs: (200, {"openapi": True})
    )
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key="stub",  # pragma: allowlist secret
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /api/v1/trends 403 api_key_rejected"
    assert data["trend_status"] == 403

    statuses["http://127.0.0.1:8000/api/v1/trends"] = 0
    exit_code, lines, data = ops_module._agent_smoke_checks(
        base_url="http://127.0.0.1:8000",
        timeout_seconds=1.0,
        api_key="stub",  # pragma: allowlist secret
    )
    assert exit_code == ExitCode.VALIDATION_ERROR
    assert lines[-1] == "FAIL /api/v1/trends connection_error"
    assert data["trend_status"] == 0


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
    monkeypatch.setattr(runtime_module.settings, "DATABASE_URL", "postgres://db")
    assert await runtime_module._doctor_check_database(0.2) == (
        "PASS",
        "database connectivity ok; migration parity healthy",
    )

    monkeypatch.setattr(migration_parity_module, "check_migration_parity", failing_migration)
    status, message = await runtime_module._doctor_check_database(0.2)
    assert status == "FAIL"
    assert "drifted" in message

    class FakeRedisClient:
        async def ping(self) -> None:
            return None

        async def close(self) -> None:
            return None

    fake_redis_module = ModuleType("redis.asyncio")
    fake_redis_module.from_url = lambda _url: FakeRedisClient()
    monkeypatch.setattr(runtime_module.settings, "REDIS_URL", "redis://cache")
    import builtins

    original_import = builtins.__import__
    fake_redis_package = ModuleType("redis")
    fake_redis_package.asyncio = fake_redis_module
    monkeypatch.setitem(sys.modules, "redis", fake_redis_package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_redis_module)
    assert await runtime_module._doctor_check_redis(0.2) == ("PASS", "redis connectivity ok")

    def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis.asyncio":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert await runtime_module._doctor_check_redis(0.2) == (
        "FAIL",
        "redis client is not installed",
    )

    class BrokenRedisClient:
        async def ping(self) -> None:
            raise RuntimeError("boom")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(builtins, "__import__", original_import)
    fake_redis_module.from_url = lambda _url: BrokenRedisClient()
    assert await runtime_module._doctor_check_redis(0.2) == ("FAIL", "redis check failed: boom")


def test_doctor_helpers_and_command_result_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert runtime_module._doctor_check_required_hooks()[0] == "FAIL"

    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        path = hooks_dir / hook_name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)

    assert runtime_module._doctor_check_required_hooks()[0] == "PASS"
    assert runtime_module._is_loopback_host("localhost") is True
    assert runtime_module._is_loopback_host("example.com") is False

    monkeypatch.setattr(runtime_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(runtime_module.settings, "RUNTIME_PROFILE", "agent")
    monkeypatch.setattr(runtime_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(runtime_module.settings, "AGENT_ALLOW_NON_LOOPBACK", False)
    monkeypatch.setattr(runtime_module.settings, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(runtime_module.settings, "API_AUTH_ENABLED", False)
    refusals = runtime_module._doctor_safety_refusals()
    assert "agent profile is not allowed in production" in refusals
    assert any("loopback API_HOST" in refusal for refusal in refusals)
    assert any("API_AUTH_ENABLED=false" in refusal for refusal in refusals)

    async def fake_db(_timeout: float) -> tuple[str, str]:
        return ("PASS", "db ok")

    async def fake_redis(_timeout: float) -> tuple[str, str]:
        return ("FAIL", "redis down")

    monkeypatch.setattr(runtime_module, "_doctor_check_database", fake_db)
    monkeypatch.setattr(runtime_module, "_doctor_check_redis", fake_redis)
    monkeypatch.setattr(runtime_module, "_doctor_safety_refusals", lambda: ["blocked"])
    monkeypatch.setattr(
        runtime_module, "_doctor_check_required_hooks", lambda: ("PASS", "hooks ok")
    )

    data, lines, exit_code = runtime_module._collect_doctor(0.2)
    assert data["database"]["status"] == "PASS"
    assert any("SAFETY_REFUSALS:" in line for line in lines)
    assert exit_code == ExitCode.VALIDATION_ERROR

    sync_result = ops_module._sync_result({"ok": True}, ["line"], ExitCode.OK)
    assert sync_result.data == {"ok": True}

    async def async_lines():
        return ({"value": 1}, ["line"])

    async def async_exit():
        return ({"value": 2}, ["line"], ExitCode.VALIDATION_ERROR)

    assert ops_module._async_result(async_lines()).data == {"value": 1}
    assert ops_module._async_result_with_exit(async_exit()).exit_code == ExitCode.VALIDATION_ERROR

    monkeypatch.setattr(
        ops_module,
        "_agent_smoke_checks",
        lambda **_kwargs: (ExitCode.OK, ["ok"], {"health_status": 200}),
    )
    handled = ops_module._handle_agent_smoke(
        SimpleNamespace(base_url="http://127.0.0.1", timeout_seconds=0, api_key=" token ")
    )
    assert handled.exit_code == ExitCode.OK
    assert handled.data["health_status"] == 200


def test_ops_leaf_options_and_register_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    ops_module.register_ops_commands(subparsers)

    args = parser.parse_args(["eval", "benchmark", "--config", "baseline", "--format", "json"])
    assert args.command == "eval"
    assert args.eval_command == "benchmark"
    assert args.config == ["baseline"]
    assert args.output_format == "json"

    args = parser.parse_args(["agent", "smoke", "--dry-run"])
    assert args.command == "agent"
    assert args.agent_command == "smoke"
    assert args.dry_run is True

    eval_parser = next(
        action.choices["eval"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction) and "eval" in action.choices
    )
    benchmark_parser = next(
        action.choices["benchmark"]
        for action in eval_parser._actions
        if isinstance(action, argparse._SubParsersAction) and "benchmark" in action.choices
    )
    help_text = benchmark_parser.format_help()
    assert "Defaults to the baseline set (baseline, alternative)" in help_text
    assert "GPT-5 candidates require explicit --config selection" in help_text


def test_runtime_result_wraps_runtime_bridge_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ops_module,
        "_run_runtime_bridge",
        lambda action, payload: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "exit_code": 2,
                    "data": {"action": action, "payload": payload},
                    "lines": ["line-one"],
                    "error_lines": ["line-two"],
                }
            ),
            stderr="",
        ),
    )

    result = ops_module._runtime_result(
        "doctor",
        SimpleNamespace(timeout_seconds=1.5, output_format="json", handler=object()),
    )

    assert result.exit_code == ExitCode.VALIDATION_ERROR
    assert result.data == {"action": "doctor", "payload": {"timeout_seconds": 1.5}}
    assert result.lines == ["line-one"]
    assert result.error_lines == ["line-two"]


def test_runtime_result_reports_invalid_runtime_bridge_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ops_module,
        "_run_runtime_bridge",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=4, stdout="not-json", stderr="boom"),
    )

    result = ops_module._runtime_result("doctor", SimpleNamespace(timeout_seconds=2.0))

    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert result.error_lines is not None
    assert "invalid JSON" in result.error_lines[0]


def test_runtime_result_reports_missing_and_non_object_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ops_module,
        "_run_runtime_bridge",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=4, stdout="", stderr="boom"),
    )
    missing = ops_module._runtime_result("doctor", SimpleNamespace(timeout_seconds=2.0))
    assert missing.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert missing.error_lines == ["doctor runtime bridge returned no JSON output", "boom"]

    monkeypatch.setattr(
        ops_module,
        "_run_runtime_bridge",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout='["bad"]', stderr=""),
    )
    non_object = ops_module._runtime_result("doctor", SimpleNamespace(timeout_seconds=2.0))
    assert non_object.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert non_object.error_lines == ["doctor runtime bridge returned a non-object payload"]

    monkeypatch.setattr(
        ops_module,
        "_run_runtime_bridge",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"exit_code": 0, "data": [], "lines": "line", "error_lines": "err"}),
            stderr="",
        ),
    )
    normalized = ops_module._runtime_result("doctor", SimpleNamespace(timeout_seconds=2.0))
    assert normalized.data is None
    assert normalized.lines == ["line"]
    assert normalized.error_lines == ["err"]


def test_runtime_payload_and_bridge_command_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = ops_module._runtime_payload(
        SimpleNamespace(
            timeout_seconds=1.5,
            handler=object(),
            output_format="json",
            command="doctor",
            optional=None,
        )
    )
    assert payload == {"timeout_seconds": 1.5, "optional": None}

    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(ops_module.subprocess, "run", fake_run)
    completed = ops_module._run_runtime_bridge(
        "doctor", {"when": datetime(2026, 3, 8, 12, 0, tzinfo=UTC)}
    )

    assert completed.returncode == 0
    assert captured["command"] == [
        sys.executable,
        "-m",
        "src.cli_runtime",
        "doctor",
        "--payload",
        '{"when": "2026-03-08T12:00:00+00:00"}',
    ]
    assert captured["kwargs"] == {"capture_output": True, "text": True, "check": False}


def test_ops_json_default_and_env_defaults_cover_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass
    class _Unsupported:
        value: int

    assert ops_module._json_default(datetime(2026, 3, 8, 12, 0, tzinfo=UTC)).endswith("+00:00")
    assert ops_module._json_default(Path("artifacts/out.json")) == "artifacts/out.json"
    with pytest.raises(TypeError):
        ops_module._json_default(_Unsupported(1))

    monkeypatch.delenv("API_HOST", raising=False)
    assert ops_module._env_default("API_HOST", "0.0.0.0") == "0.0.0.0"
    monkeypatch.delenv("API_PORT", raising=False)
    assert ops_module._default_agent_base_url() == "http://127.0.0.1:8000"
    monkeypatch.setenv("API_HOST", "  ")
    assert ops_module._env_default("API_HOST", "0.0.0.0") == "0.0.0.0"
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "9000")
    assert ops_module._default_agent_base_url() == "http://127.0.0.1:9000"


def test_runtime_module_helper_functions_cover_result_serialization_and_namespace() -> None:
    @dataclass
    class _Payload:
        value: int

    assert runtime_module._json_default(datetime(2026, 3, 8, 12, 0, tzinfo=UTC)).endswith("+00:00")
    assert runtime_module._json_default(Path("artifacts/out.json")) == "artifacts/out.json"
    assert runtime_module._json_default(_Payload(1)) == {"value": 1}
    with pytest.raises(TypeError):
        runtime_module._json_default(object())

    assert runtime_module._result_payload(exit_code=0) == {"exit_code": 0}
    assert runtime_module._result_payload(
        exit_code=2,
        data={"ok": True},
        lines=["line"],
        error_lines=["error"],
    ) == {
        "exit_code": 2,
        "data": {"ok": True},
        "lines": ["line"],
        "error_lines": ["error"],
    }
    assert runtime_module._parse_iso_datetime(None) is None
    assert runtime_module._parse_iso_datetime(" ") is None
    assert runtime_module._parse_iso_datetime("2026-03-08T12:00:00Z") == datetime(
        2026, 3, 8, 12, 0, tzinfo=UTC
    )
    assert runtime_module._parse_iso_datetime("2026-03-08T14:00:00+02:00") == datetime(
        2026, 3, 8, 14, 0, tzinfo=datetime.fromisoformat("2026-03-08T14:00:00+02:00").tzinfo
    )
    assert runtime_module._format_embedding_model_counts(SimpleNamespace(model_counts=[])) == "none"
    assert runtime_module._namespace({"value": 3}).value == 3


def test_runtime_action_wrappers_delegate_to_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_trends(limit: int) -> tuple[dict[str, int], list[str]]:
        assert limit == 1
        return ({"limit": limit}, ["trend"])

    async def fake_dashboard(output_dir: str, limit: int) -> tuple[dict[str, str], list[str]]:
        assert output_dir == "artifacts/dashboard"
        assert limit == 1
        return ({"output_dir": output_dir}, ["dashboard"])

    async def fake_async_collector(args: SimpleNamespace) -> tuple[dict[str, str], list[str], int]:
        return ({"value": args.value}, ["async"], ExitCode.OK)

    def fake_sync_collector(args: SimpleNamespace) -> tuple[dict[str, str], list[str], int]:
        return ({"value": args.value}, ["sync"], ExitCode.VALIDATION_ERROR)

    monkeypatch.setattr(runtime_module, "_collect_trends_status", fake_trends)
    monkeypatch.setattr(runtime_module, "_collect_dashboard_export", fake_dashboard)
    monkeypatch.setattr(runtime_module, "_collect_eval_benchmark", fake_async_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_audit", fake_sync_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_validate_taxonomy", fake_sync_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_replay", fake_async_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_vector_benchmark", fake_async_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_embedding_lineage", fake_async_collector)
    monkeypatch.setattr(runtime_module, "_collect_eval_source_freshness", fake_async_collector)
    monkeypatch.setattr(runtime_module, "_collect_pipeline_dry_run", fake_sync_collector)
    monkeypatch.setattr(
        runtime_module,
        "_collect_doctor",
        lambda timeout: ({"timeout": timeout}, ["doctor"], ExitCode.OK),
    )

    assert runtime_module._action_trends_status({"limit": 0})["data"] == {"limit": 1}
    assert runtime_module._action_dashboard_export({"limit": 0})["data"] == {
        "output_dir": "artifacts/dashboard"
    }
    assert runtime_module._action_eval_benchmark({"value": "x"})["data"] == {"value": "x"}
    assert (
        runtime_module._action_eval_audit({"value": "x"})["exit_code"] == ExitCode.VALIDATION_ERROR
    )
    assert runtime_module._action_eval_validate_taxonomy({"value": "x"})["lines"] == ["sync"]
    assert runtime_module._action_eval_replay({"value": "x"})["data"] == {"value": "x"}
    assert runtime_module._action_eval_vector_benchmark({"value": "x"})["data"] == {"value": "x"}
    assert runtime_module._action_eval_embedding_lineage({"value": "x"})["data"] == {"value": "x"}
    assert runtime_module._action_eval_source_freshness({"value": "x"})["data"] == {"value": "x"}
    assert runtime_module._action_pipeline_dry_run({"value": "x"})["lines"] == ["sync"]
    assert runtime_module._action_doctor({"timeout_seconds": 0.0})["data"] == {"timeout": 0.1}


def test_runtime_parser_and_main_cover_success_and_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    parser = runtime_module._build_parser()
    parsed = parser.parse_args(["doctor", "--payload", '{"timeout_seconds": 1.5}'])
    assert parsed.action == "doctor"

    monkeypatch.setitem(
        runtime_module._ACTIONS,
        "doctor",
        lambda payload: runtime_module._result_payload(
            exit_code=ExitCode.OK,
            data={"payload": payload},
            lines=["ok"],
        ),
    )
    assert runtime_module.main(["doctor", "--payload", '{"timeout_seconds": 1.5}']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"] == {"payload": {"timeout_seconds": 1.5}}

    assert runtime_module.main(["doctor", "--payload", "[]"]) == ExitCode.ENVIRONMENT_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert "payload must decode to a JSON object" in payload["error_lines"][0]

    monkeypatch.setitem(
        runtime_module._ACTIONS,
        "doctor",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert runtime_module.main(["doctor", "--payload", '{"timeout_seconds": 1.5}']) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_lines"] == ["doctor runtime bridge failed: boom"]

    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        path = hooks_dir / hook_name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_module.settings, "DATABASE_URL", "")
    monkeypatch.setattr(runtime_module.settings, "REDIS_URL", "")
    monkeypatch.setattr(
        sys, "argv", ["src.cli_runtime", "doctor", "--payload", '{"timeout_seconds": 0.1}']
    )
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("src.cli_runtime", run_name="__main__")
