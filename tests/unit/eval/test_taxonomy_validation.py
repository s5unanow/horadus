from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import taxonomy_validation as taxonomy_module

pytestmark = pytest.mark.unit


def _write_trend_config(
    path: Path,
    *,
    trend_id: str | None,
    trend_name: str,
    indicators: dict[str, str],
) -> None:
    id_line = f'id: "{trend_id}"\n' if trend_id is not None else ""
    indicator_blocks = []
    for signal_type, direction in indicators.items():
        indicator_blocks.append(
            "\n".join(
                [
                    f"  {signal_type}:",
                    "    weight: 0.04",
                    f"    direction: {direction}",
                    "    type: leading",
                ]
            )
        )
    indicator_lines = "\n".join(indicator_blocks)
    path.write_text(
        (
            f"{id_line}"
            f'name: "{trend_name}"\n'
            "baseline_probability: 0.10\n"
            "decay_half_life_days: 30\n"
            "indicators:\n"
            f"{indicator_lines}\n"
        ),
        encoding="utf-8",
    )


def _gold_row(
    *,
    item_id: str,
    tier1_scores: dict[str, int],
    tier2: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "title": f"title-{item_id}",
        "content": f"content-{item_id}",
        "label_verification": "human_verified",
        "expected": {
            "tier1": {
                "trend_scores": tier1_scores,
                "max_relevance": max(tier1_scores.values()) if tier1_scores else 0,
            },
            "tier2": tier2,
        },
    }


def _write_gold_set(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_run_trend_taxonomy_validation_passes_for_aligned_dataset(tmp_path: Path) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "eu-russia.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia",
        indicators={"military_movement": "escalatory"},
    )
    _write_trend_config(
        trend_dir / "us-china.yaml",
        trend_id="us-china",
        trend_name="US-China",
        indicators={"diplomatic_engagement": "de_escalatory"},
    )

    gold_path = tmp_path / "gold_set.jsonl"
    _write_gold_set(
        gold_path,
        [
            _gold_row(
                item_id="eval-1",
                tier1_scores={"eu-russia": 8, "us-china": 2},
                tier2={
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.8,
                    "confidence": 0.9,
                },
            )
        ],
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(gold_path),
        output_dir=str(tmp_path / "results"),
    )

    assert result.errors == []
    assert result.warnings == []
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["passes_validation"] is True
    assert payload["summary"]["configured_trends_count"] == 2


def test_run_trend_taxonomy_validation_reports_duplicate_and_missing_ids(tmp_path: Path) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "first.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia A",
        indicators={"military_movement": "escalatory"},
    )
    _write_trend_config(
        trend_dir / "missing-id.yaml",
        trend_id=None,
        trend_name="Missing ID",
        indicators={"military_movement": "escalatory"},
    )
    _write_trend_config(
        trend_dir / "duplicate.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia B",
        indicators={"military_movement": "escalatory"},
    )

    gold_path = tmp_path / "gold_set.jsonl"
    _write_gold_set(
        gold_path,
        [_gold_row(item_id="eval-1", tier1_scores={"eu-russia": 8}, tier2=None)],
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(gold_path),
        output_dir=str(tmp_path / "results"),
    )

    assert any("missing required trend 'id'" in message for message in result.errors)
    assert any("duplicate trend id 'eu-russia'" in message for message in result.errors)


def test_run_trend_taxonomy_validation_fails_unknown_tier2_trend_id(tmp_path: Path) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "eu-russia.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia",
        indicators={"military_movement": "escalatory"},
    )

    gold_path = tmp_path / "gold_set.jsonl"
    _write_gold_set(
        gold_path,
        [
            _gold_row(
                item_id="eval-1",
                tier1_scores={"eu-russia": 9},
                tier2={
                    "trend_id": "middle-east",
                    "signal_type": "energy_disruption",
                    "direction": "escalatory",
                    "severity": 0.7,
                    "confidence": 0.9,
                },
            )
        ],
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(gold_path),
        output_dir=str(tmp_path / "results"),
    )

    assert any(
        "Tier-2 labels contain unknown trend_id values" in message for message in result.errors
    )


def test_run_trend_taxonomy_validation_fails_tier1_key_mismatch_in_strict_mode(
    tmp_path: Path,
) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "eu-russia.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia",
        indicators={"military_movement": "escalatory"},
    )
    _write_trend_config(
        trend_dir / "us-china.yaml",
        trend_id="us-china",
        trend_name="US-China",
        indicators={"diplomatic_engagement": "de_escalatory"},
    )

    gold_path = tmp_path / "gold_set.jsonl"
    _write_gold_set(
        gold_path,
        [_gold_row(item_id="eval-1", tier1_scores={"eu-russia": 9}, tier2=None)],
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(gold_path),
        output_dir=str(tmp_path / "results"),
        tier1_trend_mode="strict",
    )

    assert any(
        "Tier-1 strict mode requires exact trend_scores keys" in message
        for message in result.errors
    )


def test_run_trend_taxonomy_validation_handles_unknown_signal_types_in_warn_mode(
    tmp_path: Path,
) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "eu-russia.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia",
        indicators={"military_movement": "escalatory"},
    )

    gold_path = tmp_path / "gold_set.jsonl"
    _write_gold_set(
        gold_path,
        [
            _gold_row(
                item_id="eval-1",
                tier1_scores={"eu-russia": 9},
                tier2={
                    "trend_id": "eu-russia",
                    "signal_type": "energy_disruption",
                    "direction": "escalatory",
                    "severity": 0.7,
                    "confidence": 0.9,
                },
            )
        ],
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(gold_path),
        output_dir=str(tmp_path / "results"),
        signal_type_mode="warn",
    )

    assert result.errors == []
    assert any(
        "Tier-2 labels contain unknown signal_type values" in message for message in result.warnings
    )
