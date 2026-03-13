from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


def change_arrow(change: float) -> str:
    if change > 0:
        return "^"
    if change < 0:
        return "v"
    return "="


def format_trend_status_lines(movement: Any) -> list[str]:
    header = (
        f"# {movement.trend_name}: "
        f"{movement.current_probability * 100:.1f}% "
        f"({movement.risk_level}) "
        f"{change_arrow(movement.weekly_change)} "
        f"{movement.weekly_change * 100:+.1f}% this week "
        f"[{movement.movement_chart}]"
    )
    movers = ", ".join(movement.top_movers_7d) if movement.top_movers_7d else "none"
    return [header, f"  Top movers: {movers}"]


def parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def format_embedding_model_counts(summary: Any) -> str:
    if not summary.model_counts:
        return "none"
    return ", ".join(f"{entry.model}={entry.count}" for entry in summary.model_counts)


def json_default(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
