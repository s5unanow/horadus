from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID

from src.core.config import settings
from src.horadus_cli.result import CommandResult, ExitCode


def _change_arrow(change: float) -> str:
    if change > 0:
        return "^"
    if change < 0:
        return "v"
    return "="


def _format_trend_status_lines(movement: Any) -> list[str]:
    header = (
        f"# {movement.trend_name}: "
        f"{movement.current_probability * 100:.1f}% "
        f"({movement.risk_level}) "
        f"{_change_arrow(movement.weekly_change)} "
        f"{movement.weekly_change * 100:+.1f}% this week "
        f"[{movement.movement_chart}]"
    )
    movers = ", ".join(movement.top_movers_7d) if movement.top_movers_7d else "none"
    return [header, f"  Top movers: {movers}"]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _format_embedding_model_counts(summary: Any) -> str:
    if not summary.model_counts:
        return "none"
    return ", ".join(f"{entry.model}={entry.count}" for entry in summary.model_counts)


async def _collect_trends_status(limit: int) -> tuple[dict[str, Any], list[str]]:
    from src.core.calibration_dashboard import CalibrationDashboardService
    from src.storage.database import async_session_maker

    async with async_session_maker() as session:
        service = CalibrationDashboardService(session)
        dashboard = await service.build_dashboard()

    rows = dashboard.trend_movements[:limit]
    if not rows:
        return ({"trends": []}, ["No active trends found."])

    lines: list[str] = []
    trends: list[dict[str, Any]] = []
    for movement in rows:
        trends.append(
            {
                "trend_id": str(movement.trend_id),
                "trend_name": movement.trend_name,
                "current_probability": movement.current_probability,
                "weekly_change": movement.weekly_change,
                "risk_level": movement.risk_level,
                "top_movers_7d": list(movement.top_movers_7d),
                "movement_chart": movement.movement_chart,
            }
        )
        lines.extend(_format_trend_status_lines(movement))
    return ({"trends": trends}, lines)


async def _collect_dashboard_export(
    output_dir: str, limit: int
) -> tuple[dict[str, Any], list[str]]:
    from src.core.calibration_dashboard import CalibrationDashboardService
    from src.core.dashboard_export import export_calibration_dashboard
    from src.storage.database import async_session_maker

    async with async_session_maker() as session:
        service = CalibrationDashboardService(session)
        dashboard = await service.build_dashboard()

    result = export_calibration_dashboard(dashboard, output_dir=output_dir, trend_limit=limit)
    data = {
        "json_path": str(result.json_path),
        "html_path": str(result.html_path),
        "latest_json_path": str(result.latest_json_path),
        "latest_html_path": str(result.latest_html_path),
        "index_html_path": str(result.index_html_path),
    }
    lines = [
        f"Exported JSON: {result.json_path}",
        f"Exported HTML: {result.html_path}",
        f"Latest JSON: {result.latest_json_path}",
        f"Latest HTML: {result.latest_html_path}",
        f"Hosting index: {result.index_html_path}",
    ]
    return (data, lines)


async def _collect_eval_benchmark(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.benchmark import run_gold_set_benchmark

    output_path = await run_gold_set_benchmark(
        gold_set_path=args.gold_set,
        output_dir=args.output_dir,
        api_key=settings.OPENAI_API_KEY,
        trend_config_dir=args.trend_config_dir,
        max_items=max(1, args.max_items),
        config_names=args.config,
        require_human_verified=args.require_human_verified,
        dispatch_mode=args.dispatch_mode,
        request_priority=args.request_priority,
    )
    return ({"output_path": str(output_path)}, [f"Benchmark output: {output_path}"], ExitCode.OK)


async def _collect_eval_replay(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.replay import run_historical_replay_comparison

    parsed_trend_id = UUID(args.trend_id) if args.trend_id else None
    output_path = await run_historical_replay_comparison(
        output_dir=args.output_dir,
        champion_config_name=args.champion_config,
        challenger_config_name=args.challenger_config,
        trend_id=parsed_trend_id,
        start_date=_parse_iso_datetime(args.start_date),
        end_date=_parse_iso_datetime(args.end_date),
        days=max(1, args.days),
    )
    return ({"output_path": str(output_path)}, [f"Replay output: {output_path}"], ExitCode.OK)


async def _collect_eval_vector_benchmark(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.vector_benchmark import run_vector_retrieval_benchmark

    output_path = await run_vector_retrieval_benchmark(
        output_dir=args.output_dir,
        database_url=args.database_url,
        dataset_size=max(100, args.dataset_size),
        query_count=max(10, args.query_count),
        dimensions=max(8, args.dimensions),
        top_k=max(1, args.top_k),
        similarity_threshold=args.similarity_threshold,
        seed=args.seed,
    )
    return (
        {"output_path": str(output_path)},
        [f"Vector benchmark output: {output_path}"],
        ExitCode.OK,
    )


async def _collect_eval_embedding_lineage(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.core.embedding_lineage import build_embedding_lineage_report
    from src.storage.database import async_session_maker

    async with async_session_maker() as session:
        report = await build_embedding_lineage_report(session, target_model=args.target_model)

    lines = [f"Embedding target model: {report.target_model}"]
    summaries = []
    for summary in (report.raw_items, report.events):
        summaries.append(
            {
                "entity": summary.entity,
                "vectors": summary.vectors,
                "target_model_vectors": summary.target_model_vectors,
                "vectors_other_models": summary.vectors_other_models,
                "vectors_missing_model": summary.vectors_missing_model,
                "reembed_scope": summary.reembed_scope,
                "model_counts": [
                    {"model": entry.model, "count": entry.count} for entry in summary.model_counts
                ],
            }
        )
        lines.append(
            f"{summary.entity}: vectors={summary.vectors}, "
            f"target={summary.target_model_vectors}, "
            f"other_models={summary.vectors_other_models}, "
            f"missing_model={summary.vectors_missing_model}, "
            f"reembed_scope={summary.reembed_scope}"
        )
        lines.append(f"  model_counts: {_format_embedding_model_counts(summary)}")

    lines.append(
        f"total_vectors={report.total_vectors}, "
        f"total_reembed_scope={report.total_reembed_scope}, "
        f"mixed_population={str(report.has_mixed_populations).lower()}"
    )
    exit_code = (
        ExitCode.VALIDATION_ERROR
        if args.fail_on_mixed and report.has_mixed_populations
        else ExitCode.OK
    )
    return (
        {
            "target_model": report.target_model,
            "summaries": summaries,
            "total_vectors": report.total_vectors,
            "total_reembed_scope": report.total_reembed_scope,
            "has_mixed_populations": report.has_mixed_populations,
        },
        lines,
        exit_code,
    )


async def _collect_eval_source_freshness(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.core.source_freshness import build_source_freshness_report
    from src.storage.database import async_session_maker

    async with async_session_maker() as session:
        report = await build_source_freshness_report(
            session=session, stale_multiplier=args.stale_multiplier
        )

    enabled_collectors: list[str] = []
    if settings.ENABLE_RSS_INGESTION:
        enabled_collectors.append("rss")
    if settings.ENABLE_GDELT_INGESTION:
        enabled_collectors.append("gdelt")

    dispatch_budget = max(0, settings.SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES)
    catchup_candidates = [
        collector for collector in report.stale_collectors if collector in enabled_collectors
    ][:dispatch_budget]

    lines = [
        f"checked_at={report.checked_at.isoformat()}",
        f"stale_multiplier={report.stale_multiplier}",
        f"stale_count={report.stale_count}",
        "catchup_candidates=" + (",".join(catchup_candidates) if catchup_candidates else "none"),
    ]
    rows = []
    for row in report.rows:
        last_fetched = row.last_fetched_at.isoformat() if row.last_fetched_at else "never"
        age = row.age_seconds if row.age_seconds is not None else "unknown"
        lines.append(
            f"- {row.collector}:{row.source_name} stale={str(row.is_stale).lower()} "
            f"age_seconds={age} stale_after_seconds={row.stale_after_seconds} "
            f"last_fetched_at={last_fetched}"
        )
        rows.append(
            {
                "collector": row.collector,
                "source_name": row.source_name,
                "is_stale": row.is_stale,
                "age_seconds": row.age_seconds,
                "stale_after_seconds": row.stale_after_seconds,
                "last_fetched_at": row.last_fetched_at.isoformat() if row.last_fetched_at else None,
            }
        )
    exit_code = (
        ExitCode.VALIDATION_ERROR if args.fail_on_stale and report.stale_count > 0 else ExitCode.OK
    )
    return (
        {
            "checked_at": report.checked_at.isoformat(),
            "stale_multiplier": report.stale_multiplier,
            "stale_count": report.stale_count,
            "catchup_candidates": catchup_candidates,
            "rows": rows,
        },
        lines,
        exit_code,
    )


def _collect_eval_audit(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.audit import run_gold_set_audit

    result = run_gold_set_audit(
        gold_set_path=args.gold_set, output_dir=args.output_dir, max_items=max(1, args.max_items)
    )
    lines = [f"Audit output: {result.output_path}"]
    if result.warnings:
        lines.append("Audit warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    exit_code = (
        ExitCode.VALIDATION_ERROR if args.fail_on_warnings and result.warnings else ExitCode.OK
    )
    return (
        {"output_path": str(result.output_path), "warnings": list(result.warnings)},
        lines,
        exit_code,
    )


def _collect_eval_validate_taxonomy(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.taxonomy_validation import run_trend_taxonomy_validation

    result = run_trend_taxonomy_validation(
        trend_config_dir=args.trend_config_dir,
        gold_set_path=args.gold_set,
        output_dir=args.output_dir,
        max_items=max(1, args.max_items),
        tier1_trend_mode=args.tier1_trend_mode,
        signal_type_mode=args.signal_type_mode,
        unknown_trend_mode=args.unknown_trend_mode,
    )
    lines = [f"Taxonomy validation output: {result.output_path}"]
    if result.warnings:
        lines.append("Taxonomy validation warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if result.errors:
        lines.append("Taxonomy validation errors:")
        lines.extend(f"- {error}" for error in result.errors)
        return (
            {
                "output_path": str(result.output_path),
                "warnings": list(result.warnings),
                "errors": list(result.errors),
            },
            lines,
            ExitCode.VALIDATION_ERROR,
        )
    exit_code = (
        ExitCode.VALIDATION_ERROR if args.fail_on_warnings and result.warnings else ExitCode.OK
    )
    return (
        {"output_path": str(result.output_path), "warnings": list(result.warnings), "errors": []},
        lines,
        exit_code,
    )


def _http_get(url: str, *, timeout_seconds: float, headers: dict[str, str] | None = None) -> int:
    request = urllib_request.Request(url=url, method="GET", headers=headers or {})
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            return int(response.status)
    except urllib_error.HTTPError as exc:
        return int(exc.code)
    except urllib_error.URLError:
        return 0


def _http_get_json(
    url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    request = urllib_request.Request(url=url, method="GET", headers=headers or {})
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                return status, payload
            return status, None
    except urllib_error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return int(exc.code), payload
        return int(exc.code), None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, None


def _agent_smoke_checks(
    *,
    base_url: str,
    timeout_seconds: float,
    api_key: str | None,
) -> tuple[int, list[str], dict[str, Any]]:
    normalized_base_url = base_url.rstrip("/")
    lines: list[str] = []

    health_status = _http_get(f"{normalized_base_url}/health", timeout_seconds=timeout_seconds)
    if 200 <= health_status < 300:
        lines.append(f"PASS /health {health_status}")
    else:
        lines.append(f"FAIL /health {health_status or 'connection_error'}")
        return (ExitCode.VALIDATION_ERROR, lines, {"health_status": health_status})

    openapi_status, openapi_payload = _http_get_json(
        f"{normalized_base_url}/openapi.json",
        timeout_seconds=timeout_seconds,
    )
    if 200 <= openapi_status < 300:
        lines.append(f"PASS /openapi.json {openapi_status}")
    else:
        lines.append(f"FAIL /openapi.json {openapi_status or 'connection_error'}")
        return (
            ExitCode.VALIDATION_ERROR,
            lines,
            {"health_status": health_status, "openapi_status": openapi_status},
        )

    trend_headers = {"X-API-Key": api_key} if api_key else None
    trend_status = _http_get(
        f"{normalized_base_url}/api/v1/trends",
        timeout_seconds=timeout_seconds,
        headers=trend_headers,
    )
    if 200 <= trend_status < 300:
        lines.append(f"PASS /api/v1/trends {trend_status}")
        return (
            ExitCode.OK,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    if trend_status in {401, 403} and not api_key:
        auth_hint = "unknown"
        if openapi_payload is not None:
            auth_hint = "openapi_security_present"
        lines.append(f"PASS /api/v1/trends {trend_status} auth_enforced_without_key ({auth_hint})")
        return (
            ExitCode.OK,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
                "auth_hint": auth_hint,
            },
        )

    if trend_status in {401, 403} and api_key:
        lines.append(f"FAIL /api/v1/trends {trend_status} api_key_rejected")
        return (
            ExitCode.VALIDATION_ERROR,
            lines,
            {
                "health_status": health_status,
                "openapi_status": openapi_status,
                "trend_status": trend_status,
            },
        )

    lines.append(f"FAIL /api/v1/trends {trend_status or 'connection_error'}")
    return (
        ExitCode.VALIDATION_ERROR,
        lines,
        {
            "health_status": health_status,
            "openapi_status": openapi_status,
            "trend_status": trend_status,
        },
    )


def _run_agent_smoke(*, base_url: str, timeout_seconds: float, api_key: str | None) -> int:
    exit_code, lines, _data = _agent_smoke_checks(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
    )
    for line in lines:
        print(line)
    return int(exit_code)


def _doctor_check_required_hooks() -> tuple[str, str]:
    hooks_dir = Path(".git") / "hooks"
    required = ("pre-commit", "pre-push", "commit-msg")
    missing: list[str] = []
    for hook_name in required:
        hook_path = hooks_dir / hook_name
        if (
            not hook_path.exists()
            or not hook_path.is_file()
            or not hook_path.stat().st_mode & 0o111
        ):
            missing.append(hook_name)
    if missing:
        return ("FAIL", f"missing executable hooks: {', '.join(missing)} (run: make hooks)")
    return ("PASS", "required git hooks installed")


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "localhost"}


def _doctor_safety_refusals() -> list[str]:
    refusals: list[str] = []
    if settings.is_production and settings.is_agent_profile:
        refusals.append("agent profile is not allowed in production")
    if (
        settings.is_agent_profile
        and not settings.AGENT_ALLOW_NON_LOOPBACK
        and not _is_loopback_host(settings.API_HOST)
    ):
        refusals.append(
            "agent profile requires loopback API_HOST unless AGENT_ALLOW_NON_LOOPBACK=true"
        )
    if settings.is_production_like and not settings.API_AUTH_ENABLED:
        refusals.append("API_AUTH_ENABLED=false in production-like environment")
    return refusals


async def _doctor_check_database(timeout_seconds: float) -> tuple[str, str]:
    from sqlalchemy import text

    from src.core.migration_parity import check_migration_parity
    from src.storage.database import async_session_maker

    database_url = settings.DATABASE_URL.strip()
    if not database_url:
        return ("SKIP", "DATABASE_URL not configured")

    try:
        async with async_session_maker() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")), timeout=max(0.1, timeout_seconds)
            )
            migration = await asyncio.wait_for(
                check_migration_parity(session),
                timeout=max(0.1, timeout_seconds),
            )
    except Exception as exc:
        return ("FAIL", f"database check failed: {exc}")

    migration_status = str(migration.get("status", "unknown"))
    if migration_status != "healthy":
        message = str(migration.get("message", "migration parity mismatch"))
        return ("FAIL", f"database ok; migrations {migration_status}: {message}")
    return ("PASS", "database connectivity ok; migration parity healthy")


async def _doctor_check_redis(timeout_seconds: float) -> tuple[str, str]:
    redis_url = settings.REDIS_URL.strip()
    if not redis_url:
        return ("SKIP", "REDIS_URL not configured")

    try:
        import redis.asyncio as redis
    except ImportError:
        return ("FAIL", "redis client is not installed")

    client = redis.from_url(redis_url)
    try:
        await asyncio.wait_for(client.ping(), timeout=max(0.1, timeout_seconds))
    except Exception as exc:
        return ("FAIL", f"redis check failed: {exc}")
    finally:
        await client.close()
    return ("PASS", "redis connectivity ok")


def _collect_doctor(timeout_seconds: float) -> tuple[dict[str, Any], list[str], int]:
    lines = [
        f"ENVIRONMENT={settings.ENVIRONMENT}",
        f"RUNTIME_PROFILE={settings.RUNTIME_PROFILE}",
        f"API_HOST={settings.API_HOST}",
    ]
    hook_status, hook_message = _doctor_check_required_hooks()
    lines.append(f"HOOKS: {hook_status} - {hook_message}")

    refusals = _doctor_safety_refusals()
    if refusals:
        lines.append("SAFETY_REFUSALS:")
        lines.extend(f"- {refusal}" for refusal in refusals)
    else:
        lines.append("SAFETY_REFUSALS: none")

    db_status, db_message = asyncio.run(_doctor_check_database(timeout_seconds))
    redis_status, redis_message = asyncio.run(_doctor_check_redis(timeout_seconds))
    lines.append(f"DATABASE: {db_status} - {db_message}")
    lines.append(f"REDIS: {redis_status} - {redis_message}")

    exit_code = ExitCode.OK
    if "FAIL" in {hook_status, db_status, redis_status} or refusals:
        exit_code = ExitCode.VALIDATION_ERROR

    return (
        {
            "environment": settings.ENVIRONMENT,
            "runtime_profile": settings.RUNTIME_PROFILE,
            "api_host": settings.API_HOST,
            "hooks": {"status": hook_status, "message": hook_message},
            "safety_refusals": refusals,
            "database": {"status": db_status, "message": db_message},
            "redis": {"status": redis_status, "message": redis_message},
        },
        lines,
        exit_code,
    )


def _run_doctor(*, timeout_seconds: float) -> int:
    _data, lines, exit_code = _collect_doctor(timeout_seconds)
    for line in lines:
        print(line)
    return int(exit_code)


def _collect_pipeline_dry_run(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.processing.dry_run_pipeline import run_pipeline_dry_run

    artifact_path = run_pipeline_dry_run(
        fixture_path=Path(args.fixture_path),
        trend_config_dir=Path(args.trend_config_dir),
        output_path=Path(args.output_path),
    )
    return (
        {"artifact_path": str(artifact_path)},
        [f"Dry-run artifact: {artifact_path}"],
        ExitCode.OK,
    )


def _legacy_leaf_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Validate and describe the command without making changes.",
    )


def register_legacy_commands(subparsers: Any) -> None:
    trends_parser = subparsers.add_parser("trends")
    trends_subparsers = trends_parser.add_subparsers(dest="trends_command")
    trends_status_parser = trends_subparsers.add_parser(
        "status",
        help="Show trend probabilities, weekly movement, and top movers.",
    )
    _legacy_leaf_options(trends_status_parser)
    trends_status_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of active trends to display."
    )
    trends_status_parser.set_defaults(
        handler=lambda args: _async_result(_collect_trends_status(max(args.limit, 1)))
    )

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")
    dashboard_export_parser = dashboard_subparsers.add_parser(
        "export",
        help="Export calibration dashboard to static JSON/HTML artifacts.",
    )
    _legacy_leaf_options(dashboard_export_parser)
    dashboard_export_parser.add_argument(
        "--output-dir",
        default="artifacts/dashboard",
        help="Directory where dashboard artifacts are written.",
    )
    dashboard_export_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of trend movement rows included in export.",
    )
    dashboard_export_parser.set_defaults(
        handler=lambda args: _async_result(
            _collect_dashboard_export(args.output_dir, max(args.limit, 1))
        )
    )

    eval_parser = subparsers.add_parser("eval")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    from src.eval.benchmark import available_configs
    from src.eval.replay import available_replay_configs

    eval_benchmark_parser = eval_subparsers.add_parser(
        "benchmark",
        help="Run Tier-1/Tier-2 benchmark against ai/eval gold set.",
    )
    _legacy_leaf_options(eval_benchmark_parser)
    eval_benchmark_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_benchmark_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for benchmark result artifacts."
    )
    eval_benchmark_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files used for benchmark taxonomy.",
    )
    eval_benchmark_parser.add_argument(
        "--max-items",
        type=int,
        default=50,
        help="Maximum gold-set items to evaluate (use 200 for full run).",
    )
    eval_benchmark_parser.add_argument(
        "--config",
        action="append",
        choices=sorted(available_configs().keys()),
        help="Benchmark config name (repeat to run multiple). Defaults to all.",
    )
    eval_benchmark_parser.add_argument(
        "--require-human-verified",
        action="store_true",
        help="Evaluate only rows where label_verification=human_verified.",
    )
    eval_benchmark_parser.add_argument(
        "--dispatch-mode",
        choices=["realtime", "batch"],
        default="realtime",
        help="Offline dispatch profile.",
    )
    eval_benchmark_parser.add_argument(
        "--request-priority",
        choices=["realtime", "flex"],
        default="realtime",
        help="Provider priority hint.",
    )
    eval_benchmark_parser.set_defaults(
        handler=lambda args: _async_result_with_exit(_collect_eval_benchmark(args))
    )

    eval_audit_parser = eval_subparsers.add_parser(
        "audit", help="Audit gold-set quality (provenance, diversity, and label coverage)."
    )
    _legacy_leaf_options(eval_audit_parser)
    eval_audit_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_audit_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for audit result artifacts."
    )
    eval_audit_parser.add_argument(
        "--max-items", type=int, default=200, help="Maximum dataset rows to audit."
    )
    eval_audit_parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero exit code if audit warnings are present.",
    )
    eval_audit_parser.set_defaults(handler=lambda args: _sync_result(*_collect_eval_audit(args)))

    eval_taxonomy_parser = eval_subparsers.add_parser(
        "validate-taxonomy",
        help="Validate trend config taxonomy contract against the evaluation gold set.",
    )
    _legacy_leaf_options(eval_taxonomy_parser)
    eval_taxonomy_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files.",
    )
    eval_taxonomy_parser.add_argument(
        "--gold-set", default="ai/eval/gold_set.jsonl", help="Path to gold-set JSONL file."
    )
    eval_taxonomy_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for taxonomy validation result artifacts.",
    )
    eval_taxonomy_parser.add_argument(
        "--max-items", type=int, default=200, help="Maximum dataset rows to validate."
    )
    eval_taxonomy_parser.add_argument(
        "--tier1-trend-mode",
        choices=["strict", "subset"],
        default="strict",
        help="Tier-1 key validation mode.",
    )
    eval_taxonomy_parser.add_argument(
        "--signal-type-mode",
        choices=["strict", "warn"],
        default="strict",
        help="Tier-2 signal-type mismatch behavior.",
    )
    eval_taxonomy_parser.add_argument(
        "--unknown-trend-mode",
        choices=["strict", "warn"],
        default="strict",
        help="Unknown trend mismatch behavior.",
    )
    eval_taxonomy_parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero exit code when warnings are emitted.",
    )
    eval_taxonomy_parser.set_defaults(
        handler=lambda args: _sync_result(*_collect_eval_validate_taxonomy(args))
    )

    eval_replay_parser = eval_subparsers.add_parser(
        "replay", help="Run historical champion/challenger replay over stored outcomes."
    )
    _legacy_leaf_options(eval_replay_parser)
    eval_replay_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for replay result artifacts."
    )
    replay_configs = sorted(available_replay_configs().keys())
    eval_replay_parser.add_argument(
        "--champion-config",
        default="stable",
        choices=replay_configs,
        help="Champion replay policy config.",
    )
    eval_replay_parser.add_argument(
        "--challenger-config",
        default="fast_lower_threshold",
        choices=replay_configs,
        help="Challenger replay policy config.",
    )
    eval_replay_parser.add_argument("--trend-id", default=None, help="Optional trend UUID scope.")
    eval_replay_parser.add_argument(
        "--start-date", default=None, help="Optional ISO-8601 start datetime."
    )
    eval_replay_parser.add_argument(
        "--end-date", default=None, help="Optional ISO-8601 end datetime."
    )
    eval_replay_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Replay window in days when start-date is not provided.",
    )
    eval_replay_parser.set_defaults(
        handler=lambda args: _async_result_with_exit(_collect_eval_replay(args))
    )

    eval_vector_parser = eval_subparsers.add_parser(
        "vector-benchmark", help="Benchmark exact vs IVFFlat vs HNSW retrieval quality/latency."
    )
    _legacy_leaf_options(eval_vector_parser)
    eval_vector_parser.add_argument(
        "--output-dir", default="ai/eval/results", help="Directory for vector benchmark artifacts."
    )
    eval_vector_parser.add_argument(
        "--database-url", default=None, help="Optional PostgreSQL URL override."
    )
    eval_vector_parser.add_argument(
        "--dataset-size", type=int, default=4000, help="Number of benchmark vectors to generate."
    )
    eval_vector_parser.add_argument(
        "--query-count", type=int, default=200, help="Number of query vectors to evaluate."
    )
    eval_vector_parser.add_argument(
        "--dimensions",
        type=int,
        default=64,
        help="Embedding dimensions for synthetic benchmark vectors.",
    )
    eval_vector_parser.add_argument(
        "--top-k", type=int, default=10, help="Neighbors returned per query."
    )
    eval_vector_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.88,
        help="Cosine similarity threshold used for retrieval filtering.",
    )
    eval_vector_parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for deterministic synthetic data."
    )
    eval_vector_parser.set_defaults(
        handler=lambda args: _async_result_with_exit(_collect_eval_vector_benchmark(args))
    )

    eval_embedding_lineage_parser = eval_subparsers.add_parser(
        "embedding-lineage", help="Report embedding model lineage and re-embed scope."
    )
    _legacy_leaf_options(eval_embedding_lineage_parser)
    eval_embedding_lineage_parser.add_argument(
        "--target-model",
        default=settings.EMBEDDING_MODEL,
        help="Embedding model that should be considered canonical.",
    )
    eval_embedding_lineage_parser.add_argument(
        "--fail-on-mixed",
        action="store_true",
        help="Return non-zero when multiple embedding models are detected.",
    )
    eval_embedding_lineage_parser.set_defaults(
        handler=lambda args: _async_result_with_exit(_collect_eval_embedding_lineage(args))
    )

    eval_source_freshness_parser = eval_subparsers.add_parser(
        "source-freshness", help="Report stale RSS/GDELT sources and catch-up candidates."
    )
    _legacy_leaf_options(eval_source_freshness_parser)
    eval_source_freshness_parser.add_argument(
        "--stale-multiplier",
        type=float,
        default=None,
        help="Optional override for freshness stale threshold multiplier.",
    )
    eval_source_freshness_parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Return non-zero exit code when any stale source is detected.",
    )
    eval_source_freshness_parser.set_defaults(
        handler=lambda args: _async_result_with_exit(_collect_eval_source_freshness(args))
    )

    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_subparsers = pipeline_parser.add_subparsers(dest="pipeline_command")
    pipeline_dry_run_parser = pipeline_subparsers.add_parser(
        "dry-run",
        help="Run deterministic offline pipeline scoring on local fixtures.",
    )
    _legacy_leaf_options(pipeline_dry_run_parser)
    pipeline_dry_run_parser.add_argument(
        "--fixture-path",
        default="ai/eval/fixtures/pipeline_dry_run_items.jsonl",
        help="Path to fixture JSONL file.",
    )
    pipeline_dry_run_parser.add_argument(
        "--trend-config-dir",
        default="config/trends",
        help="Directory containing trend config YAML files.",
    )
    pipeline_dry_run_parser.add_argument(
        "--output-path",
        default="artifacts/agent/pipeline-dry-run-output.json",
        help="Output JSON artifact path.",
    )
    pipeline_dry_run_parser.set_defaults(
        handler=lambda args: _sync_result(*_collect_pipeline_dry_run(args))
    )

    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
    agent_smoke_parser = agent_subparsers.add_parser(
        "smoke",
        help="Run local agent-oriented smoke checks against a running Horadus API server.",
    )
    _legacy_leaf_options(agent_smoke_parser)
    agent_smoke_parser.add_argument(
        "--base-url",
        default=f"http://{settings.API_HOST}:{settings.API_PORT}",
        help="Base URL for local smoke checks.",
    )
    agent_smoke_parser.add_argument(
        "--timeout-seconds", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    agent_smoke_parser.add_argument(
        "--api-key",
        default=settings.API_KEY or "",
        help="Optional API key used when auth-protected smoke endpoints are checked.",
    )
    agent_smoke_parser.set_defaults(handler=_handle_agent_smoke)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run local runtime diagnostics (hooks, config, DB, Redis, migration parity).",
    )
    _legacy_leaf_options(doctor_parser)
    doctor_parser.add_argument(
        "--timeout-seconds", type=float, default=2.0, help="Timeout per dependency check."
    )
    doctor_parser.set_defaults(
        handler=lambda args: _sync_result(*_collect_doctor(max(0.1, args.timeout_seconds)))
    )


def _sync_result(data: dict[str, Any], lines: list[str], exit_code: int) -> CommandResult:
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def _async_result(coro: Any) -> CommandResult:
    data, lines = asyncio.run(coro)
    return CommandResult(lines=lines, data=data)


def _async_result_with_exit(coro: Any) -> CommandResult:
    data, lines, exit_code = asyncio.run(coro)
    return CommandResult(exit_code=exit_code, lines=lines, data=data)


def _handle_agent_smoke(args: Any) -> CommandResult:
    exit_code, lines, data = _agent_smoke_checks(
        base_url=args.base_url,
        timeout_seconds=max(0.1, args.timeout_seconds),
        api_key=(args.api_key or "").strip() or None,
    )
    return CommandResult(exit_code=exit_code, lines=lines, data=data)
