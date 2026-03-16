from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.trend_config import build_trend_config, resolve_runtime_trend_id
from src.core.trend_config_loader import discover_trend_config_files, load_trends_from_config_dir

pytestmark = pytest.mark.unit


def test_load_trends_from_config_dir_preserves_indicator_descriptions(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "eu-russia.yaml").write_text(
        """
id: "eu-russia"
name: "EU-Russia"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  military_movement:
    weight: 0.05
    direction: escalatory
    type: leading
    description: "Force repositioning without direct hostile contact."
    keywords: ["troops", "deployment"]
  military_incident:
    weight: 0.06
    direction: escalatory
    type: leading
    keywords: ["fired upon", "collision"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    trends = load_trends_from_config_dir(config_dir=config_dir)

    assert len(trends) == 1
    indicators = trends[0].indicators
    assert indicators["military_movement"]["description"] == (
        "Force repositioning without direct hostile contact."
    )
    assert indicators["military_incident"]["description"] is None


def test_load_trends_from_config_dir_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Trend config directory not found"):
        load_trends_from_config_dir(config_dir=tmp_path / "missing")


def test_load_trends_from_config_dir_rejects_empty_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()

    with pytest.raises(ValueError, match="No trend config YAML files found"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_load_trends_from_config_dir_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "invalid.yaml").write_text("- item\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_load_trends_from_config_dir_rejects_invalid_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "invalid.yaml").write_text("id: [\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Failed to load trend config invalid\.yaml"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_load_trends_from_config_dir_rejects_validation_errors(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "invalid.yaml").write_text(
        """
id: "eu-russia"
name: "EU-Russia"
indicators: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"TrendConfig validation failed for invalid\.yaml"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_load_trends_from_config_dir_rejects_blank_trend_id(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "blank-id.yaml").write_text(
        """
id: "   "
name: "Blank"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  signal:
    weight: 0.05
    direction: escalatory
    type: leading
    keywords: ["one"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required trend id"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_load_trends_from_config_dir_rejects_duplicate_ids_and_sorts_results(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    (config_dir / "b.yaml").write_text(
        """
id: "beta"
name: "Beta"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  signal:
    weight: 0.05
    direction: escalatory
    type: leading
    keywords: ["one"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "a.yml").write_text(
        """
id: "alpha"
name: "Alpha"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  signal:
    weight: 0.05
    direction: escalatory
    type: leading
    keywords: ["one"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    trends = load_trends_from_config_dir(config_dir=config_dir)

    assert [trend.definition["id"] for trend in trends] == ["alpha", "beta"]

    (config_dir / "dup.yaml").write_text(
        """
id: "alpha"
name: "Duplicate"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  signal:
    weight: 0.05
    direction: escalatory
    type: leading
    keywords: ["one"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate trend id in config dir: alpha"):
        load_trends_from_config_dir(config_dir=config_dir)


def test_discover_trend_config_files_ignores_nested_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / "trends"
    config_dir.mkdir()
    nested_dir = config_dir / "nested"
    nested_dir.mkdir()
    (config_dir / "top.yaml").write_text(
        """
id: "top"
name: "Top"
baseline_probability: 0.10
decay_half_life_days: 30
indicators:
  signal:
    weight: 0.05
    direction: escalatory
    type: leading
    keywords: ["one"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (nested_dir / "ignored.yaml").write_text("id: nested\n", encoding="utf-8")

    files = discover_trend_config_files(config_dir=config_dir)
    trends = load_trends_from_config_dir(config_dir=config_dir)

    assert files == [config_dir / "top.yaml"]
    assert [trend.definition["id"] for trend in trends] == ["top"]


def test_resolve_runtime_trend_id_falls_back_from_blank_definition_id() -> None:
    assert (
        resolve_runtime_trend_id(definition={"id": "   "}, trend_name="Signal Watch")
        == "signal-watch"
    )


def test_resolve_runtime_trend_id_rejects_blank_name_without_identifier() -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        resolve_runtime_trend_id(definition={"id": "   "}, trend_name=" ")


def test_resolve_runtime_trend_id_rejects_overlength_identifier() -> None:
    with pytest.raises(ValueError, match="cannot exceed 255 characters"):
        resolve_runtime_trend_id(definition={"id": "x" * 256}, trend_name="Signal Watch")


def test_build_trend_config_rejects_non_mapping_indicators() -> None:
    with pytest.raises(ValidationError, match="indicators"):
        build_trend_config(
            name="Signal Watch",
            description=None,
            baseline_probability=0.1,
            decay_half_life_days=30,
            indicators=["not-a-mapping"],  # type: ignore[arg-type]
        )
