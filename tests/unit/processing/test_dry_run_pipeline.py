from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.processing.dry_run_pipeline import run_pipeline_dry_run

pytestmark = pytest.mark.unit


def test_run_pipeline_dry_run_writes_expected_artifact(tmp_path: Path) -> None:
    fixture_path = Path("ai/eval/fixtures/pipeline_dry_run_items.jsonl")
    trend_dir = Path("config/trends")
    output_path = tmp_path / "dry-run-output.json"

    result_path = run_pipeline_dry_run(
        fixture_path=fixture_path,
        trend_config_dir=trend_dir,
        output_path=output_path,
    )

    assert result_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["items_total"] == 5
    assert payload["items_after_dedup"] == 4
    assert any(row["item_id"] == "fixture-002" for row in payload["duplicates"])
    assert payload["clusters"]
    assert payload["trend_scores"]


def test_run_pipeline_dry_run_is_stable_except_timestamp(tmp_path: Path) -> None:
    fixture_path = Path("ai/eval/fixtures/pipeline_dry_run_items.jsonl")
    trend_dir = Path("config/trends")
    output_a = tmp_path / "a.json"
    output_b = tmp_path / "b.json"

    run_pipeline_dry_run(
        fixture_path=fixture_path,
        trend_config_dir=trend_dir,
        output_path=output_a,
    )
    run_pipeline_dry_run(
        fixture_path=fixture_path,
        trend_config_dir=trend_dir,
        output_path=output_b,
    )

    payload_a = json.loads(output_a.read_text(encoding="utf-8"))
    payload_b = json.loads(output_b.read_text(encoding="utf-8"))
    payload_a.pop("generated_at", None)
    payload_b.pop("generated_at", None)

    assert payload_a == payload_b
