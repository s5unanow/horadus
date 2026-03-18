from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from src.core.config import settings as runtime_settings

settings = runtime_settings


class ExitCode(IntEnum):
    OK = 0
    VALIDATION_ERROR = 2
    NOT_FOUND = 3
    ENVIRONMENT_ERROR = 4


def _json_default(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return asdict(cast("Any", value))
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _result_payload(
    *,
    exit_code: int,
    data: dict[str, Any] | None = None,
    lines: list[str] | None = None,
    error_lines: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"exit_code": int(exit_code)}
    if data is not None:
        payload["data"] = data
    if lines:
        payload["lines"] = lines
    if error_lines:
        payload["error_lines"] = error_lines
    return payload


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
        header = (
            f"# {movement.trend_name}: "
            f"{movement.current_probability * 100:.1f}% "
            f"({movement.risk_level}) "
            f"{'^' if movement.weekly_change > 0 else 'v' if movement.weekly_change < 0 else '='} "
            f"{movement.weekly_change * 100:+.1f}% this week "
            f"[{movement.movement_chart}]"
        )
        movers = ", ".join(movement.top_movers_7d) if movement.top_movers_7d else "none"
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
        lines.extend([header, f"  Top movers: {movers}"])
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


def _collect_eval_audit(args: Any) -> tuple[dict[str, Any], list[str], int]:
    from src.eval.audit import run_gold_set_audit

    max_items = None if args.max_items <= 0 else args.max_items
    result = run_gold_set_audit(
        gold_set_path=args.gold_set, output_dir=args.output_dir, max_items=max_items
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


def _namespace(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**payload)


def _action_trends_status(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines = asyncio.run(_collect_trends_status(max(int(payload.get("limit", 20)), 1)))
    return _result_payload(exit_code=ExitCode.OK, data=data, lines=lines)


def _action_dashboard_export(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines = asyncio.run(
        _collect_dashboard_export(
            str(payload.get("output_dir", "artifacts/dashboard")),
            max(int(payload.get("limit", 20)), 1),
        )
    )
    return _result_payload(exit_code=ExitCode.OK, data=data, lines=lines)


def _action_eval_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = asyncio.run(_collect_eval_benchmark(_namespace(payload)))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_audit(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = _collect_eval_audit(_namespace(payload))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_validate_taxonomy(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = _collect_eval_validate_taxonomy(_namespace(payload))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_replay(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = asyncio.run(_collect_eval_replay(_namespace(payload)))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_vector_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = asyncio.run(_collect_eval_vector_benchmark(_namespace(payload)))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_embedding_lineage(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = asyncio.run(_collect_eval_embedding_lineage(_namespace(payload)))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_eval_source_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = asyncio.run(_collect_eval_source_freshness(_namespace(payload)))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_pipeline_dry_run(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = _collect_pipeline_dry_run(_namespace(payload))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


def _action_doctor(payload: dict[str, Any]) -> dict[str, Any]:
    data, lines, exit_code = _collect_doctor(max(0.1, float(payload.get("timeout_seconds", 2.0))))
    return _result_payload(exit_code=exit_code, data=data, lines=lines)


_ACTIONS: dict[str, Any] = {
    "dashboard-export": _action_dashboard_export,
    "doctor": _action_doctor,
    "eval-audit": _action_eval_audit,
    "eval-benchmark": _action_eval_benchmark,
    "eval-embedding-lineage": _action_eval_embedding_lineage,
    "eval-replay": _action_eval_replay,
    "eval-source-freshness": _action_eval_source_freshness,
    "eval-validate-taxonomy": _action_eval_validate_taxonomy,
    "eval-vector-benchmark": _action_eval_vector_benchmark,
    "pipeline-dry-run": _action_pipeline_dry_run,
    "trends-status": _action_trends_status,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.horadus.python.horadus_app_cli_runtime")
    parser.add_argument("action", choices=sorted(_ACTIONS))
    parser.add_argument("--payload", required=True, help="JSON payload for the action.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.payload)
        if not isinstance(payload, dict):
            raise ValueError("payload must decode to a JSON object")
        result = _ACTIONS[args.action](payload)
    except Exception as exc:
        result = _result_payload(
            exit_code=ExitCode.ENVIRONMENT_ERROR,
            error_lines=[f"{args.action} runtime bridge failed: {exc}"],
        )
    print(json.dumps(result, sort_keys=True, default=_json_default))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ExitCode",
    "_collect_dashboard_export",
    "_collect_doctor",
    "_collect_eval_audit",
    "_collect_eval_benchmark",
    "_collect_eval_embedding_lineage",
    "_collect_eval_replay",
    "_collect_eval_source_freshness",
    "_collect_eval_validate_taxonomy",
    "_collect_eval_vector_benchmark",
    "_collect_pipeline_dry_run",
    "_collect_trends_status",
    "_doctor_check_database",
    "_doctor_check_redis",
    "_doctor_check_required_hooks",
    "_doctor_safety_refusals",
    "_format_embedding_model_counts",
    "_is_loopback_host",
    "_parse_iso_datetime",
    "main",
    "settings",
]
