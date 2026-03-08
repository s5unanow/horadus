from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.processing.dry_run_pipeline as dry_run_module
from src.processing.dry_run_pipeline import (
    FixtureItem,
    _cluster_items,
    _deduplicate,
    _item_signature,
    _load_fixture_items,
    _load_trend_configs,
    _parse_datetime,
    run_pipeline_dry_run,
)

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


def test_dry_run_pipeline_helpers_cover_edge_cases(tmp_path: Path) -> None:
    assert _parse_datetime("2026-03-01T00:00:00Z").tzinfo is not None
    assert _parse_datetime("2026-03-01T00:00:00").tzinfo is not None
    assert (
        _item_signature(
            FixtureItem(
                item_id="1",
                title="the and or",
                url="https://example.com/1",
                published_at=_parse_datetime("2026-03-01T00:00:00Z"),
                content="content",
                source="rss",
            )
        )
        == "misc"
    )

    fixture_path = tmp_path / "fixtures.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                "",
                json.dumps(
                    {
                        "title": "First item",
                        "url": "https://example.com/1",
                        "published_at": "2026-03-01T00:00:00",
                        "content": "content",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    items = _load_fixture_items(fixture_path)
    assert items[0].item_id == "fixture-002"
    assert items[0].source == "fixture"

    fixture_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        _load_fixture_items(fixture_path)


def test_deduplicate_cluster_and_load_trend_configs_helpers(tmp_path: Path) -> None:
    first = FixtureItem(
        item_id="1",
        title="Border escalation update",
        url="https://example.com/a?utm_source=x",
        published_at=_parse_datetime("2026-03-01T00:00:00Z"),
        content="same content",
        source="rss",
    )
    duplicate_url = FixtureItem(
        item_id="2",
        title="Border escalation update",
        url="https://www.example.com/a",
        published_at=_parse_datetime("2026-03-01T01:00:00Z"),
        content="different content",
        source="rss",
    )
    duplicate_hash = FixtureItem(
        item_id="3",
        title="Border escalation update",
        url="https://example.com/b",
        published_at=_parse_datetime("2026-03-01T02:00:00Z"),
        content="same content",
        source="wire",
    )
    no_url = FixtureItem(
        item_id="4",
        title="Signal with no URL",
        url="",
        published_at=_parse_datetime("2026-03-01T03:00:00Z"),
        content="fresh content",
        source="wire",
    )

    kept, duplicates = _deduplicate([first, duplicate_url, duplicate_hash, no_url])
    clusters = _cluster_items(kept)

    assert [item.item_id for item in kept] == ["1", "4"]
    assert [row["reason"] for row in duplicates] == ["url", "content_hash"]
    assert clusters[0]["source_count"] == 1
    assert "Border escalation update same content" in clusters[0]["text"]

    trend_dir = tmp_path / "trends"
    trend_dir.mkdir()
    (trend_dir / "skip.yaml").write_text("- invalid\n", encoding="utf-8")
    (trend_dir / "custom.yaml").write_text(
        "\n".join(
            [
                "name: Custom Trend",
                "baseline_probability: 0.2",
                "description: Custom trend",
                "indicators:",
                "  signal_one:",
                "    weight: 0.5",
                "    direction: escalatory",
                "    keywords: ['', border]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = _load_trend_configs(trend_dir)

    assert [trend_id for trend_id, _config in loaded] == ["custom"]


def test_score_trends_ignores_blank_keywords() -> None:
    clusters = [{"cluster_id": "cluster-1", "source_count": 2, "text": "border border update"}]
    trend_scores = dry_run_module._score_trends(
        clusters=clusters,
        trend_configs=[
            (
                "custom",
                SimpleNamespace(
                    baseline_probability=0.2,
                    indicators={
                        "signal_one": SimpleNamespace(
                            keywords=[" ", "border"],
                            weight=0.5,
                            direction="escalatory",
                        )
                    },
                ),
            )
        ],
    )

    assert trend_scores[0]["trend_id"] == "custom"
    assert trend_scores[0]["matched_signals"][0]["keyword_hits"] == 2


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
