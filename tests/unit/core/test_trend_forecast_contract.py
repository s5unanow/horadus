from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.trend_config import build_trend_config
from src.core.trend_forecast_contract import (
    TrendForecastContract,
    TrendForecastHorizon,
    normalize_forecast_contract_payload,
)
from tests.unit.trend_forecast_contract_fixtures import (
    sample_binary_forecast_contract,
    sample_threshold_forecast_contract,
)

pytestmark = pytest.mark.unit


def test_trend_forecast_contract_accepts_valid_binary_event_contract() -> None:
    contract = TrendForecastContract.model_validate(sample_binary_forecast_contract())

    assert contract.closure_rule == "binary_event_by_horizon"
    assert contract.horizon.kind == "fixed_date"
    assert contract.occurrence_definition == "Confirmed direct conflict occurs."


def test_trend_forecast_contract_rejects_missing_horizon_date() -> None:
    payload = sample_binary_forecast_contract()
    payload.pop("horizon")

    with pytest.raises(ValidationError, match="horizon"):
        TrendForecastContract.model_validate(payload)


def test_trend_forecast_contract_rejects_ambiguous_threshold_contract() -> None:
    with pytest.raises(ValidationError, match="resolution_basis"):
        TrendForecastContract.model_validate(
            sample_threshold_forecast_contract(
                occurrence_definition="This should not be set for threshold questions.",
            )
        )


def test_build_trend_config_requires_forecast_contract() -> None:
    with pytest.raises(ValidationError, match="forecast_contract"):
        build_trend_config(
            name="Signal Watch",
            description=None,
            baseline_probability=0.1,
            decay_half_life_days=30,
            indicators={},
            definition={},
        )


def test_trend_forecast_horizon_rejects_fixed_date_with_relative_fields() -> None:
    with pytest.raises(ValidationError, match="Fixed-date horizons cannot set"):
        TrendForecastHorizon.model_validate(
            {
                "kind": "fixed_date",
                "fixed_date": "2030-12-31",
                "value": 10,
                "unit": "years",
            }
        )


def test_trend_forecast_horizon_rejects_incomplete_rolling_window() -> None:
    with pytest.raises(ValidationError, match="Rolling-window horizons require"):
        TrendForecastHorizon.model_validate({"kind": "rolling_window", "value": 10})


def test_trend_forecast_horizon_rejects_fixed_date_on_rolling_window() -> None:
    with pytest.raises(ValidationError, match="cannot set fixed_date"):
        TrendForecastHorizon.model_validate(
            {
                "kind": "rolling_window",
                "fixed_date": "2030-12-31",
                "value": 10,
                "unit": "years",
                "reference_point": "evaluation_date",
            }
        )


def test_trend_forecast_contract_rejects_missing_question_mark() -> None:
    with pytest.raises(ValidationError, match="Forecast question must end with"):
        TrendForecastContract.model_validate(
            sample_binary_forecast_contract(question="Will a test conflict occur by 2030-12-31")
        )


def test_trend_forecast_contract_rejects_missing_binary_definitions() -> None:
    with pytest.raises(ValidationError, match="Binary-event forecast contracts require"):
        TrendForecastContract.model_validate(
            sample_binary_forecast_contract(occurrence_definition=None)
        )


def test_normalize_forecast_contract_payload_handles_none_and_invalid_types() -> None:
    assert normalize_forecast_contract_payload(None) is None
    assert TrendForecastContract._strip_text_fields(123) == 123

    with pytest.raises(ValueError, match="must be a mapping"):
        normalize_forecast_contract_payload("bad-input")  # type: ignore[arg-type]
