"""Storage-owned scoring contract constants shared across runtime layers."""

from __future__ import annotations

from typing import Any

TREND_SCORING_MATH_VERSION = "trend-scoring-v1"
TREND_SCORING_PARAMETER_SET = "stable-default-v1"
TREND_SCORING_PROMOTION_CHECK: dict[str, Any] = {
    "required_eval": "historical_replay",
    "champion_config": "stable",
    "minimum_window_days": 90,
}
