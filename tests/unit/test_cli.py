from __future__ import annotations

from uuid import uuid4

import pytest

from src.cli import _change_arrow, _format_trend_status_lines
from src.core.calibration_dashboard import TrendMovement

pytestmark = pytest.mark.unit


def test_change_arrow_maps_signs() -> None:
    assert _change_arrow(0.1) == "^"
    assert _change_arrow(-0.1) == "v"
    assert _change_arrow(0.0) == "="


def test_format_trend_status_lines_includes_probability_change_and_movers() -> None:
    movement = TrendMovement(
        trend_id=uuid4(),
        trend_name="EU-Russia",
        current_probability=0.123,
        weekly_change=0.021,
        risk_level="guarded",
        top_movers_7d=["military_movement", "diplomatic_breakdown"],
        movement_chart="._-~=+",
    )

    lines = _format_trend_status_lines(movement)

    assert len(lines) == 2
    assert "EU-Russia" in lines[0]
    assert "12.3%" in lines[0]
    assert "^ +2.1% this week" in lines[0]
    assert "[._-~=+]" in lines[0]
    assert "military_movement, diplomatic_breakdown" in lines[1]
