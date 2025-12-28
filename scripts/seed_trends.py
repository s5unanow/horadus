"""
Seed Trend definitions into the database from `config/trends/*.yaml`.

This script is intentionally simple and idempotent:
- Inserts missing trends
- Updates existing trends matched by `Trend.name`

Usage:
  python3 scripts/seed_trends.py
  python3 scripts/seed_trends.py --path config/trends --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from src.core.trend_engine import (
    DEFAULT_BASELINE_PROBABILITY,
    DEFAULT_DECAY_HALF_LIFE_DAYS,
    prob_to_logodds,
)
from src.storage.database import async_session_maker
from src.storage.models import Trend


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Trend file must be a YAML mapping: {path}")
    return data


def _trend_name(definition: dict[str, Any], path: Path) -> str:
    name = definition.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    raise ValueError(f"Missing required 'name' in trend file: {path}")


async def seed_trends(trends_path: Path, dry_run: bool) -> int:
    if not trends_path.exists():
        raise FileNotFoundError(f"Trends path not found: {trends_path}")

    files = sorted([p for p in trends_path.glob("*.y*ml") if p.is_file()])
    if not files:
        raise FileNotFoundError(f"No YAML files found in: {trends_path}")

    created = 0
    updated = 0

    async with async_session_maker() as session:
        for path in files:
            definition = _load_yaml(path)
            name = _trend_name(definition, path)

            baseline_probability = float(
                definition.get("baseline_probability", DEFAULT_BASELINE_PROBABILITY)
            )
            decay_half_life_days = int(
                definition.get("decay_half_life_days", DEFAULT_DECAY_HALF_LIFE_DAYS)
            )
            indicators = definition.get("indicators") or {}
            if not isinstance(indicators, dict):
                raise ValueError(f"'indicators' must be a mapping in {path}")

            baseline_log_odds = prob_to_logodds(baseline_probability)

            existing = await session.execute(select(Trend).where(Trend.name == name))
            trend = existing.scalar_one_or_none()

            if trend is None:
                created += 1
                if not dry_run:
                    session.add(
                        Trend(
                            name=name,
                            description=definition.get("description"),
                            definition=definition,
                            baseline_log_odds=baseline_log_odds,
                            current_log_odds=baseline_log_odds,
                            indicators=indicators,
                            decay_half_life_days=decay_half_life_days,
                            is_active=True,
                        )
                    )
            else:
                updated += 1
                if not dry_run:
                    trend.description = definition.get("description")
                    trend.definition = definition
                    trend.indicators = indicators
                    trend.decay_half_life_days = decay_half_life_days
                    trend.baseline_log_odds = baseline_log_odds
                    # Do not overwrite current probability when reseeding.

        if not dry_run:
            await session.commit()

    print(
        f"Seeded trends from {trends_path}: created={created} updated={updated} dry_run={dry_run}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed trends into DB from YAML config.")
    parser.add_argument(
        "--path", default="config/trends", help="Directory containing trend YAML files"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to the database")
    args = parser.parse_args()

    return asyncio.run(seed_trends(Path(args.path), dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
