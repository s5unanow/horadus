"""Shared trend write-path normalization for API and config sync."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypedDict, cast

import src.core.trend_forecast_contract as trend_forecast_contract_module
from src.api.routes._trend_forecast_contract import merge_forecast_contract_into_definition
from src.core.trend_config import TrendConfig, build_trend_config
from src.core.trend_engine import logodds_to_prob, prob_to_logodds

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type TrendDefinitionInput = Mapping[str, object] | None
type TrendForecastContractInput = (
    trend_forecast_contract_module.TrendForecastContract | Mapping[str, object] | None
)
type TrendIndicatorsInput = Mapping[str, object] | None
type TrendDefinitionPayload = dict[str, JSONValue]


class TrendIndicatorPayload(TypedDict, total=False):
    """JSON-safe indicator payload persisted for validated trend writes."""

    weight: float
    direction: Literal["escalatory", "de_escalatory"]
    type: Literal["leading", "lagging"]
    decay_half_life_days: int | None
    description: str | None
    keywords: list[str]


type TrendIndicatorsPayload = dict[str, TrendIndicatorPayload]


@dataclass(frozen=True, slots=True)
class ValidatedTrendWritePayload:
    """Canonical normalized payload for trend create/update/sync writes."""

    trend_config: TrendConfig
    runtime_trend_id: str
    baseline_log_odds: float
    definition: TrendDefinitionPayload
    indicators: TrendIndicatorsPayload


def build_validated_trend_write_payload(
    *,
    name: str,
    description: str | None,
    baseline_probability: object,
    decay_half_life_days: object,
    indicators: TrendIndicatorsInput,
    definition: TrendDefinitionInput,
    forecast_contract: TrendForecastContractInput = None,
    require_forecast_contract: bool = True,
) -> ValidatedTrendWritePayload:
    merged_definition = merge_forecast_contract_into_definition(
        definition=definition,
        forecast_contract=forecast_contract,
    )
    validated_config = build_trend_config(
        name=name,
        description=description,
        baseline_probability=cast("float", baseline_probability),
        decay_half_life_days=cast("int", decay_half_life_days),
        indicators=indicators,
        definition=merged_definition,
        require_forecast_contract=require_forecast_contract,
    )
    runtime_trend_id = (validated_config.id or "").strip()
    if not runtime_trend_id:
        msg = "Trend runtime id cannot be blank"
        raise ValueError(msg)

    baseline_log_odds = prob_to_logodds(validated_config.baseline_probability)
    normalized_definition = cast(
        "TrendDefinitionPayload",
        validated_config.model_dump(mode="json", exclude_none=True),
    )
    normalized_definition["baseline_probability"] = round(
        logodds_to_prob(float(baseline_log_odds)),
        6,
    )
    normalized_indicators = cast(
        "TrendIndicatorsPayload",
        {
            signal_name: indicator.model_dump(mode="json")
            for signal_name, indicator in validated_config.indicators.items()
        },
    )
    return ValidatedTrendWritePayload(
        trend_config=validated_config,
        runtime_trend_id=runtime_trend_id,
        baseline_log_odds=baseline_log_odds,
        definition=normalized_definition,
        indicators=normalized_indicators,
    )
