"""
Helpers for loading YAML trend config into lightweight in-memory trend objects.

This is used by runtime canaries and offline eval tooling to avoid requiring a DB
session just to access the trend taxonomy.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import yaml
from pydantic import ValidationError

from src.horadus_cli.v2.runtime.core.trend_config import TrendConfig


def discover_trend_config_files(*, config_dir: Path) -> list[Path]:
    if not config_dir.exists() or not config_dir.is_dir():
        msg = f"Trend config directory not found: {config_dir}"
        raise ValueError(msg)

    files = sorted([*config_dir.glob("*.yaml"), *config_dir.glob("*.yml")])
    if not files:
        msg = f"No trend config YAML files found in: {config_dir}"
        raise ValueError(msg)
    return files


def load_trends_from_config_dir(*, config_dir: Path) -> list[SimpleNamespace]:
    files = discover_trend_config_files(config_dir=config_dir)

    trends: list[SimpleNamespace] = []
    seen_ids: set[str] = set()
    for file_path in files:
        try:
            raw_config = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            msg = f"Failed to load trend config {file_path.name}: {exc}"
            raise ValueError(msg) from exc

        if not isinstance(raw_config, dict):
            msg = f"Trend config {file_path.name} must be a mapping"
            raise ValueError(msg)

        try:
            parsed = TrendConfig.model_validate(raw_config)
        except ValidationError as exc:
            msg = f"TrendConfig validation failed for {file_path.name}: {exc}"
            raise ValueError(msg) from exc

        trend_id = (parsed.id or "").strip()
        if not trend_id:
            msg = f"Trend config {file_path.name} missing required trend id"
            raise ValueError(msg)
        if trend_id in seen_ids:
            msg = f"Duplicate trend id in config dir: {trend_id}"
            raise ValueError(msg)
        seen_ids.add(trend_id)

        trends.append(
            SimpleNamespace(
                id=uuid5(NAMESPACE_URL, f"trend/{trend_id}"),
                name=parsed.name,
                definition={"id": trend_id},
                description=parsed.description,
                indicators={
                    signal_type: {
                        "weight": config.weight,
                        "direction": config.direction,
                        "type": config.type,
                        "decay_half_life_days": config.decay_half_life_days,
                        "description": config.description,
                        "keywords": list(config.keywords),
                    }
                    for signal_type, config in parsed.indicators.items()
                },
            )
        )

    trends.sort(key=lambda trend: str(getattr(trend, "definition", {}).get("id", "")))
    return trends
