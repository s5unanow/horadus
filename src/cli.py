"""
Horadus command-line interface.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from src.core.calibration_dashboard import CalibrationDashboardService, TrendMovement
from src.core.config import settings
from src.core.dashboard_export import export_calibration_dashboard
from src.eval.benchmark import available_configs, run_gold_set_benchmark
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
) -> int:
    output_path = await run_gold_set_benchmark(
        gold_set_path=gold_set,
        output_dir=output_dir,
        api_key=settings.OPENAI_API_KEY,
        max_items=max(1, max_items),
        config_names=config_names,
    )
    print(f"Benchmark output: {output_path}")
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
            )
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
