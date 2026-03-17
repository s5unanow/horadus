"""Shared trend write-path normalization for API and config sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import src.core.trend_forecast_contract as trend_forecast_contract_module  # noqa: TC001
from src.api.routes._trend_forecast_contract import merge_forecast_contract_into_definition
from src.core.trend_config import TrendConfig, build_trend_config
from src.core.trend_engine import logodds_to_prob, prob_to_logodds


@dataclass(frozen=True, slots=True)
class ValidatedTrendWritePayload:
    """Canonical normalized payload for trend create/update/sync writes."""

    trend_config: TrendConfig
    runtime_trend_id: str
    baseline_log_odds: float
    definition: dict[str, Any]
    indicators: dict[str, Any]


def build_validated_trend_write_payload(
    *,
    name: str,
    description: str | None,
    baseline_probability: Any,
    decay_half_life_days: Any,
    indicators: dict[str, Any] | None,
    definition: dict[str, Any] | None,
    forecast_contract: trend_forecast_contract_module.TrendForecastContract
    | dict[str, Any]
    | None = None,
) -> ValidatedTrendWritePayload:
    merged_definition = merge_forecast_contract_into_definition(
        definition=definition,
        forecast_contract=forecast_contract,
    )
    validated_config = build_trend_config(
        name=name,
        description=description,
        baseline_probability=baseline_probability,
        decay_half_life_days=decay_half_life_days,
        indicators=indicators,
        definition=merged_definition,
    )
    runtime_trend_id = (validated_config.id or "").strip()
    if not runtime_trend_id:
        msg = "Trend runtime id cannot be blank"
        raise ValueError(msg)

    baseline_log_odds = prob_to_logodds(validated_config.baseline_probability)
    normalized_definition = validated_config.model_dump(mode="json", exclude_none=True)
    normalized_definition["baseline_probability"] = round(
        logodds_to_prob(float(baseline_log_odds)),
        6,
    )
    normalized_indicators = {
        signal_name: indicator.model_dump(mode="json")
        for signal_name, indicator in validated_config.indicators.items()
    }
    return ValidatedTrendWritePayload(
        trend_config=validated_config,
        runtime_trend_id=runtime_trend_id,
        baseline_log_odds=baseline_log_odds,
        definition=normalized_definition,
        indicators=normalized_indicators,
    )
