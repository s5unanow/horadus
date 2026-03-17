"""Helpers for trend forecast-contract read/write normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.trend_config import normalize_definition_payload
from src.core.trend_forecast_contract import (
    TrendForecastContract,
    normalize_forecast_contract_payload,
)


def merge_forecast_contract_into_definition(
    *,
    definition: Mapping[str, Any] | None,
    forecast_contract: TrendForecastContract | dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge an explicit API forecast contract into the persisted definition payload."""

    normalized_definition = normalize_definition_payload(definition)
    normalized_forecast_contract = normalize_forecast_contract_payload(forecast_contract)
    if normalized_forecast_contract is None:
        return normalized_definition

    existing_forecast_contract = normalized_definition.get("forecast_contract")
    if existing_forecast_contract is not None:
        if not isinstance(existing_forecast_contract, Mapping):
            msg = "definition.forecast_contract must be a mapping"
            raise ValueError(msg)
        normalized_existing = normalize_forecast_contract_payload(dict(existing_forecast_contract))
        if normalized_existing != normalized_forecast_contract:
            msg = "forecast_contract must match definition.forecast_contract when both are provided"
            raise ValueError(msg)

    normalized_definition["forecast_contract"] = normalized_forecast_contract
    return normalized_definition


def forecast_contract_from_definition(
    definition: Mapping[str, Any] | None,
) -> TrendForecastContract | None:
    """Extract a validated forecast contract from a trend definition payload."""

    normalized_definition = normalize_definition_payload(definition)
    raw_forecast_contract = normalized_definition.get("forecast_contract")
    if raw_forecast_contract is None:
        return None
    if not isinstance(raw_forecast_contract, Mapping):
        msg = "definition.forecast_contract must be a mapping"
        raise ValueError(msg)
    return TrendForecastContract.model_validate(dict(raw_forecast_contract))
