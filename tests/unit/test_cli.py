from __future__ import annotations

from uuid import uuid4

import pytest

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
            "--max-items",
            "100",
            "--config",
            "baseline",
            "--require-human-verified",
        ]
    )

    assert args.command == "eval"
    assert args.eval_command == "benchmark"
    assert args.gold_set == "ai/eval/gold_set.jsonl"
    assert args.output_dir == "ai/eval/results"
    assert args.max_items == 100
    assert args.config == ["baseline"]
    assert args.require_human_verified is True


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
