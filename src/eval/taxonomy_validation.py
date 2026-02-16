"""
Trend taxonomy and gold-set compatibility validation utilities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import ValidationError

from src.core.trend_config import TrendConfig
from src.eval.benchmark import GoldSetItem, load_gold_set

TrendMode = Literal["strict", "warn"]
Tier1TrendMode = Literal["strict", "subset"]


@dataclass(slots=True)
class TaxonomyValidationRunResult:
    """Result handle for a completed taxonomy validation run."""

    output_path: Path
    errors: list[str]
    warnings: list[str]


def run_trend_taxonomy_validation(
    *,
    trend_config_dir: str,
    gold_set_path: str,
    output_dir: str,
    max_items: int = 200,
    tier1_trend_mode: Tier1TrendMode = "strict",
    signal_type_mode: TrendMode = "strict",
    unknown_trend_mode: TrendMode = "strict",
) -> TaxonomyValidationRunResult:
    """Validate trend config taxonomy and gold-set trend/signal alignment."""
    trend_path = Path(trend_config_dir)
    dataset_path = Path(gold_set_path)
    errors: list[str] = []
    warnings: list[str] = []

    indicators_by_trend, trend_load_errors = _load_trend_taxonomy(config_dir=trend_path)
    errors.extend(trend_load_errors)

    gold_items: list[GoldSetItem] = []
    try:
        gold_items = load_gold_set(dataset_path, max_items=max(1, max_items))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Gold set load failed: {exc}")

    if indicators_by_trend and gold_items:
        _validate_gold_set_alignment(
            items=gold_items,
            indicators_by_trend=indicators_by_trend,
            tier1_trend_mode=tier1_trend_mode,
            signal_type_mode=signal_type_mode,
            unknown_trend_mode=unknown_trend_mode,
            errors=errors,
            warnings=warnings,
        )

    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "trend_config_dir": str(trend_path),
        "gold_set_path": str(dataset_path),
        "items_evaluated": len(gold_items),
        "passes_validation": len(errors) == 0,
        "modes": {
            "tier1_trend_mode": tier1_trend_mode,
            "signal_type_mode": signal_type_mode,
            "unknown_trend_mode": unknown_trend_mode,
        },
        "summary": {
            "configured_trend_ids": sorted(indicators_by_trend.keys()),
            "configured_trends_count": len(indicators_by_trend),
            "configured_indicator_counts": {
                trend_id: len(indicators)
                for trend_id, indicators in sorted(indicators_by_trend.items())
            },
            "tier2_labeled_items": len([item for item in gold_items if item.tier2 is not None]),
        },
        "errors": errors,
        "warnings": warnings,
    }
    output_path = _write_validation_result(output_dir=Path(output_dir), payload=payload)
    return TaxonomyValidationRunResult(output_path=output_path, errors=errors, warnings=warnings)


def _load_trend_taxonomy(*, config_dir: Path) -> tuple[dict[str, set[str]], list[str]]:
    errors: list[str] = []
    indicators_by_trend: dict[str, set[str]] = {}
    trend_sources: dict[str, str] = {}

    if not config_dir.exists() or not config_dir.is_dir():
        return {}, [f"Trend config directory not found: {config_dir}"]

    files = sorted([*config_dir.glob("*.yaml"), *config_dir.glob("*.yml")])
    if not files:
        return {}, [f"No trend config YAML files found in: {config_dir}"]

    for file_path in files:
        try:
            raw_config = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"{file_path.name}: failed to read YAML ({exc})")
            continue

        if not isinstance(raw_config, dict):
            errors.append(f"{file_path.name}: YAML root must be a mapping")
            continue

        try:
            parsed_config = TrendConfig.model_validate(raw_config)
        except ValidationError as exc:
            errors.append(f"{file_path.name}: TrendConfig validation failed ({exc})")
            continue

        trend_id = (parsed_config.id or "").strip()
        if not trend_id:
            errors.append(f"{file_path.name}: missing required trend 'id'")
            continue

        existing_source = trend_sources.get(trend_id)
        if existing_source is not None:
            errors.append(
                f"{file_path.name}: duplicate trend id '{trend_id}' (already defined in {existing_source})"
            )
            continue

        trend_sources[trend_id] = file_path.name
        indicators_by_trend[trend_id] = set(parsed_config.indicators.keys())

    return indicators_by_trend, errors


def _validate_gold_set_alignment(
    *,
    items: list[GoldSetItem],
    indicators_by_trend: dict[str, set[str]],
    tier1_trend_mode: Tier1TrendMode,
    signal_type_mode: TrendMode,
    unknown_trend_mode: TrendMode,
    errors: list[str],
    warnings: list[str],
) -> None:
    configured_ids = set(indicators_by_trend.keys())

    tier1_unknown_keys: dict[str, list[str]] = {}
    tier1_missing_keys: dict[str, list[str]] = {}
    tier1_strict_mismatch_items: list[str] = []
    tier2_unknown_trend_ids: dict[str, list[str]] = {}
    tier2_unknown_signal_types: dict[str, list[str]] = {}

    for item in items:
        row_trend_keys = set(item.tier1.trend_scores.keys())
        unknown_tier1_keys = row_trend_keys - configured_ids
        for key in sorted(unknown_tier1_keys):
            tier1_unknown_keys.setdefault(key, []).append(item.item_id)

        if tier1_trend_mode == "strict":
            missing_tier1_keys = configured_ids - row_trend_keys
            if missing_tier1_keys or unknown_tier1_keys:
                tier1_strict_mismatch_items.append(item.item_id)
            for key in sorted(missing_tier1_keys):
                tier1_missing_keys.setdefault(key, []).append(item.item_id)

        if item.tier2 is None:
            continue

        trend_id = item.tier2.trend_id
        if trend_id not in configured_ids:
            tier2_unknown_trend_ids.setdefault(trend_id, []).append(item.item_id)
            continue

        signal_type = item.tier2.signal_type
        allowed_signal_types = indicators_by_trend.get(trend_id, set())
        if signal_type not in allowed_signal_types:
            mismatch_key = f"{trend_id}:{signal_type}"
            tier2_unknown_signal_types.setdefault(mismatch_key, []).append(item.item_id)

    if tier1_unknown_keys:
        _record_finding(
            mode=unknown_trend_mode,
            message=(
                "Tier-1 trend_scores contains unknown trend_id values: "
                f"{_format_group_summary(tier1_unknown_keys)}."
            ),
            errors=errors,
            warnings=warnings,
        )

    if tier1_trend_mode == "strict" and tier1_missing_keys:
        errors.append(
            "Tier-1 strict mode requires exact trend_scores keys; "
            f"missing configured trend_id values: {_format_group_summary(tier1_missing_keys)}."
        )
    if tier1_trend_mode == "strict" and tier1_strict_mismatch_items:
        errors.append(
            "Tier-1 strict mode mismatch detected for "
            f"{len(tier1_strict_mismatch_items)} item(s): "
            f"{_sample_item_ids(tier1_strict_mismatch_items)}. "
            "Use --tier1-trend-mode subset for intentionally partial datasets."
        )

    if tier2_unknown_trend_ids:
        _record_finding(
            mode=unknown_trend_mode,
            message=(
                "Tier-2 labels contain unknown trend_id values: "
                f"{_format_group_summary(tier2_unknown_trend_ids)}."
            ),
            errors=errors,
            warnings=warnings,
        )

    if tier2_unknown_signal_types:
        _record_finding(
            mode=signal_type_mode,
            message=(
                "Tier-2 labels contain unknown signal_type values for configured trends: "
                f"{_format_group_summary(tier2_unknown_signal_types)}."
            ),
            errors=errors,
            warnings=warnings,
        )


def _record_finding(
    *,
    mode: TrendMode,
    message: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if mode == "strict":
        errors.append(message)
        return
    warnings.append(message)


def _format_group_summary(grouped_items: dict[str, list[str]], *, limit: int = 8) -> str:
    ordered = sorted(grouped_items.items(), key=lambda entry: (-len(entry[1]), entry[0]))
    parts: list[str] = []
    for key, item_ids in ordered[:limit]:
        parts.append(f"{key}({len(item_ids)}; {_sample_item_ids(item_ids)})")
    if len(ordered) > limit:
        parts.append(f"+{len(ordered) - limit} more")
    return ", ".join(parts)


def _sample_item_ids(item_ids: list[str], *, limit: int = 3) -> str:
    samples = sorted(item_ids)[:limit]
    if not samples:
        return "no items"
    suffix = f", +{len(item_ids) - limit} more" if len(item_ids) > limit else ""
    return f"sample={', '.join(samples)}{suffix}"


def _write_validation_result(*, output_dir: Path, payload: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"taxonomy-validation-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
