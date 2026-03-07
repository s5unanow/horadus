from __future__ import annotations

from pathlib import Path

import pytest

from src.core.trend_config_loader import load_trends_from_config_dir

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
