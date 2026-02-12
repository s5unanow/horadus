"""
Horadus command-line interface.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from src.core.calibration_dashboard import CalibrationDashboardService, TrendMovement
from src.core.config import settings
from src.core.dashboard_export import export_calibration_dashboard
from src.eval.audit import run_gold_set_audit
from src.eval.benchmark import available_configs, run_gold_set_benchmark
from src.eval.replay import available_replay_configs, run_historical_replay_comparison
from src.eval.vector_benchmark import run_vector_retrieval_benchmark
from src.storage.database import async_session_maker


def _change_arrow(change: float) -> str:
    if change > 0:
        return "^"
    if change < 0:
        return "v"
    return "="


def _format_trend_status_lines(movement: TrendMovement) -> list[str]:
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


async def _run_trends_status(*, limit: int) -> int:
    async with async_session_maker() as session:
        service = CalibrationDashboardService(session)
        dashboard = await service.build_dashboard()

    rows = dashboard.trend_movements[:limit]
    if not rows:
        print("No active trends found.")
        return 0

    for movement in rows:
        for line in _format_trend_status_lines(movement):
            print(line)
    return 0


async def _run_dashboard_export(*, output_dir: str, limit: int) -> int:
    async with async_session_maker() as session:
        service = CalibrationDashboardService(session)
        dashboard = await service.build_dashboard()

    result = export_calibration_dashboard(
        dashboard,
        output_dir=output_dir,
        trend_limit=limit,
    )
    print(f"Exported JSON: {result.json_path}")
    print(f"Exported HTML: {result.html_path}")
    print(f"Latest JSON: {result.latest_json_path}")
    print(f"Latest HTML: {result.latest_html_path}")
    print(f"Hosting index: {result.index_html_path}")
    return 0


async def _run_eval_benchmark(
    *,
    gold_set: str,
    output_dir: str,
    max_items: int,
    config_names: list[str] | None,
    require_human_verified: bool,
) -> int:
    output_path = await run_gold_set_benchmark(
        gold_set_path=gold_set,
        output_dir=output_dir,
        api_key=settings.OPENAI_API_KEY,
        max_items=max(1, max_items),
        config_names=config_names,
        require_human_verified=require_human_verified,
    )
    print(f"Benchmark output: {output_path}")
    return 0


async def _run_eval_replay(
    *,
    output_dir: str,
    champion_config: str,
    challenger_config: str,
    trend_id: str | None,
    start_date: str | None,
    end_date: str | None,
    days: int,
) -> int:
    parsed_trend_id = UUID(trend_id) if trend_id else None
    output_path = await run_historical_replay_comparison(
        output_dir=output_dir,
        champion_config_name=champion_config,
        challenger_config_name=challenger_config,
        trend_id=parsed_trend_id,
        start_date=_parse_iso_datetime(start_date),
        end_date=_parse_iso_datetime(end_date),
        days=max(1, days),
    )
    print(f"Replay output: {output_path}")
    return 0


async def _run_eval_vector_benchmark(
    *,
    output_dir: str,
    database_url: str | None,
    dataset_size: int,
    query_count: int,
    dimensions: int,
    top_k: int,
    similarity_threshold: float,
    seed: int,
) -> int:
    output_path = await run_vector_retrieval_benchmark(
        output_dir=output_dir,
        database_url=database_url,
        dataset_size=max(100, dataset_size),
        query_count=max(10, query_count),
        dimensions=max(8, dimensions),
        top_k=max(1, top_k),
        similarity_threshold=similarity_threshold,
        seed=seed,
    )
    print(f"Vector benchmark output: {output_path}")
    return 0


def _run_eval_audit(
    *,
    gold_set: str,
    output_dir: str,
    max_items: int,
    fail_on_warnings: bool,
) -> int:
    result = run_gold_set_audit(
        gold_set_path=gold_set,
        output_dir=output_dir,
        max_items=max(1, max_items),
    )
    print(f"Audit output: {result.output_path}")
    if result.warnings:
        print("Audit warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
        if fail_on_warnings:
            return 2
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="horadus")
    subparsers = parser.add_subparsers(dest="command")

    trends_parser = subparsers.add_parser("trends")
    trends_subparsers = trends_parser.add_subparsers(dest="trends_command")

    trends_status_parser = trends_subparsers.add_parser(
        "status",
        help="Show trend probabilities, weekly movement, and top movers.",
    )
    trends_status_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of active trends to display.",
    )

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")

    dashboard_export_parser = dashboard_subparsers.add_parser(
        "export",
        help="Export calibration dashboard to static JSON/HTML artifacts.",
    )
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

    eval_parser = subparsers.add_parser("eval")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    eval_benchmark_parser = eval_subparsers.add_parser(
        "benchmark",
        help="Run Tier-1/Tier-2 benchmark against ai/eval gold set.",
    )
    eval_benchmark_parser.add_argument(
        "--gold-set",
        default="ai/eval/gold_set.jsonl",
        help="Path to gold-set JSONL file.",
    )
    eval_benchmark_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for benchmark result artifacts.",
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

    eval_audit_parser = eval_subparsers.add_parser(
        "audit",
        help="Audit gold-set quality (provenance, diversity, and label coverage).",
    )
    eval_audit_parser.add_argument(
        "--gold-set",
        default="ai/eval/gold_set.jsonl",
        help="Path to gold-set JSONL file.",
    )
    eval_audit_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for audit result artifacts.",
    )
    eval_audit_parser.add_argument(
        "--max-items",
        type=int,
        default=200,
        help="Maximum dataset rows to audit.",
    )
    eval_audit_parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero exit code if audit warnings are present.",
    )

    eval_replay_parser = eval_subparsers.add_parser(
        "replay",
        help="Run historical champion/challenger replay over stored outcomes.",
    )
    eval_replay_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for replay result artifacts.",
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
    eval_replay_parser.add_argument(
        "--trend-id",
        default=None,
        help="Optional trend UUID scope.",
    )
    eval_replay_parser.add_argument(
        "--start-date",
        default=None,
        help="Optional ISO-8601 start datetime (e.g. 2026-01-01T00:00:00Z).",
    )
    eval_replay_parser.add_argument(
        "--end-date",
        default=None,
        help="Optional ISO-8601 end datetime (defaults to now).",
    )
    eval_replay_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Replay window in days when start-date is not provided.",
    )

    eval_vector_parser = eval_subparsers.add_parser(
        "vector-benchmark",
        help="Benchmark exact vs IVFFlat vs HNSW retrieval quality/latency.",
    )
    eval_vector_parser.add_argument(
        "--output-dir",
        default="ai/eval/results",
        help="Directory for vector benchmark artifacts.",
    )
    eval_vector_parser.add_argument(
        "--database-url",
        default=None,
        help="Optional PostgreSQL URL override (defaults to DATABASE_URL).",
    )
    eval_vector_parser.add_argument(
        "--dataset-size",
        type=int,
        default=4000,
        help="Number of benchmark vectors to generate.",
    )
    eval_vector_parser.add_argument(
        "--query-count",
        type=int,
        default=200,
        help="Number of query vectors to evaluate.",
    )
    eval_vector_parser.add_argument(
        "--dimensions",
        type=int,
        default=64,
        help="Embedding dimensions for synthetic benchmark vectors.",
    )
    eval_vector_parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Neighbors returned per query.",
    )
    eval_vector_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.88,
        help="Cosine similarity threshold used for retrieval filtering.",
    )
    eval_vector_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic synthetic data.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "trends" and args.trends_command == "status":
        return asyncio.run(_run_trends_status(limit=max(args.limit, 1)))
    if args.command == "dashboard" and args.dashboard_command == "export":
        return asyncio.run(
            _run_dashboard_export(
                output_dir=args.output_dir,
                limit=max(args.limit, 1),
            )
        )
    if args.command == "eval" and args.eval_command == "benchmark":
        return asyncio.run(
            _run_eval_benchmark(
                gold_set=args.gold_set,
                output_dir=args.output_dir,
                max_items=args.max_items,
                config_names=args.config,
                require_human_verified=args.require_human_verified,
            )
        )
    if args.command == "eval" and args.eval_command == "audit":
        return _run_eval_audit(
            gold_set=args.gold_set,
            output_dir=args.output_dir,
            max_items=args.max_items,
            fail_on_warnings=args.fail_on_warnings,
        )
    if args.command == "eval" and args.eval_command == "replay":
        return asyncio.run(
            _run_eval_replay(
                output_dir=args.output_dir,
                champion_config=args.champion_config,
                challenger_config=args.challenger_config,
                trend_id=args.trend_id,
                start_date=args.start_date,
                end_date=args.end_date,
                days=args.days,
            )
        )
    if args.command == "eval" and args.eval_command == "vector-benchmark":
        return asyncio.run(
            _run_eval_vector_benchmark(
                output_dir=args.output_dir,
                database_url=args.database_url,
                dataset_size=args.dataset_size,
                query_count=args.query_count,
                dimensions=args.dimensions,
                top_k=args.top_k,
                similarity_threshold=args.similarity_threshold,
                seed=args.seed,
            )
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
