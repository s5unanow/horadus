from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import taxonomy_validation as taxonomy_module
from src.eval.benchmark import GoldSetItem, Tier1GoldLabel

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
            "forecast_contract:\n"
            '  question: "Will a test conflict occur by 2030-12-31?"\n'
            "  horizon:\n"
            "    kind: fixed_date\n"
            "    fixed_date: 2030-12-31\n"
            '  resolution_basis: "Binary event question resolved against confirmed direct conflict."\n'
            '  resolver_source: "Official statements plus multi-source corroborated reporting."\n'
            '  resolver_basis: "Resolve yes on confirmed conflict; otherwise resolve no at horizon."\n'
            '  closure_rule: "binary_event_by_horizon"\n'
            '  occurrence_definition: "Confirmed direct conflict occurs."\n'
            '  non_occurrence_definition: "No confirmed direct conflict occurs by the horizon date."\n'
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


def test_run_trend_taxonomy_validation_handles_gold_set_load_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    _write_trend_config(
        trend_dir / "eu-russia.yaml",
        trend_id="eu-russia",
        trend_name="EU-Russia",
        indicators={"military_movement": "escalatory"},
    )

    monkeypatch.setattr(
        taxonomy_module,
        "load_gold_set",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(json.JSONDecodeError("bad", "{}", 0)),
    )

    result = taxonomy_module.run_trend_taxonomy_validation(
        trend_config_dir=str(trend_dir),
        gold_set_path=str(tmp_path / "gold_set.jsonl"),
        output_dir=str(tmp_path / "results"),
    )

    assert any("Gold set load failed" in message for message in result.errors)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["items_evaluated"] == 0
    assert payload["passes_validation"] is False


def test_load_trend_taxonomy_handles_directory_and_file_errors(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    indicators, errors = taxonomy_module._load_trend_taxonomy(config_dir=missing_dir)
    assert indicators == {}
    assert errors == [f"Trend config directory not found: {missing_dir}"]

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    indicators, errors = taxonomy_module._load_trend_taxonomy(config_dir=empty_dir)
    assert indicators == {}
    assert errors == [f"No trend config YAML files found in: {empty_dir}"]

    bad_yaml_dir = tmp_path / "bad-yaml"
    bad_yaml_dir.mkdir()
    (bad_yaml_dir / "broken.yaml").write_text(": bad", encoding="utf-8")
    indicators, errors = taxonomy_module._load_trend_taxonomy(config_dir=bad_yaml_dir)
    assert indicators == {}
    assert any("failed to read YAML" in message for message in errors)


def test_load_trend_taxonomy_handles_invalid_root_and_validation_errors(tmp_path: Path) -> None:
    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    (trend_dir / "list-root.yaml").write_text("- invalid\n", encoding="utf-8")
    (trend_dir / "invalid-config.yaml").write_text(
        "id: trend\nname: bad\nbaseline_probability: 0.1\ndecay_half_life_days: 30\nindicators: []\n",
        encoding="utf-8",
    )

    indicators, errors = taxonomy_module._load_trend_taxonomy(config_dir=trend_dir)

    assert indicators == {}
    assert any("YAML root must be a mapping" in message for message in errors)
    assert any("TrendConfig validation failed" in message for message in errors)


def test_validation_helpers_cover_warn_mode_and_summary_limits() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    taxonomy_module._record_finding(
        mode="warn",
        message="warning",
        errors=errors,
        warnings=warnings,
    )

    assert errors == []
    assert warnings == ["warning"]
    assert taxonomy_module._sample_item_ids([]) == "no items"
    assert taxonomy_module._sample_item_ids(["c", "a", "b", "d"]) == "sample=a, b, c, +1 more"

    grouped = {f"key-{index}": [f"item-{index}"] for index in range(10)}
    summary = taxonomy_module._format_group_summary(grouped, limit=8)
    assert "+2 more" in summary


def test_validate_gold_set_alignment_records_unknown_tier1_keys_in_warn_mode() -> None:
    errors: list[str] = []
    warnings: list[str] = []
    item = GoldSetItem(
        item_id="eval-1",
        title="title",
        content="content",
        label_verification="human_verified",
        tier1=Tier1GoldLabel(
            trend_scores={"unknown-trend": 5},
            max_relevance=5,
        ),
        tier2=None,
    )

    taxonomy_module._validate_gold_set_alignment(
        items=[item],
        indicators_by_trend={"eu-russia": {"military_movement"}},
        tier1_trend_mode="subset",
        signal_type_mode="strict",
        unknown_trend_mode="warn",
        errors=errors,
        warnings=warnings,
    )

    assert errors == []
    assert any(
        "Tier-1 trend_scores contains unknown trend_id values" in message for message in warnings
    )
