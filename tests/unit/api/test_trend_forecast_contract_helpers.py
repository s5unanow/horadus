from __future__ import annotations

import pytest

from src.api.routes._trend_forecast_contract import (
    forecast_contract_from_definition,
    merge_forecast_contract_into_definition,
)
from tests.unit.trend_forecast_contract_fixtures import sample_binary_forecast_contract

pytestmark = pytest.mark.unit


def test_merge_forecast_contract_into_definition_returns_original_when_missing() -> None:
    definition = {"id": "trend-a"}

    assert (
        merge_forecast_contract_into_definition(
            definition=definition,
            forecast_contract=None,
        )
        == definition
    )


def test_merge_forecast_contract_into_definition_rejects_non_mapping_existing_value() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        merge_forecast_contract_into_definition(
            definition={"forecast_contract": "bad"},
            forecast_contract=sample_binary_forecast_contract(),
        )


def test_merge_forecast_contract_into_definition_rejects_mismatched_contracts() -> None:
    with pytest.raises(ValueError, match="must match"):
        merge_forecast_contract_into_definition(
            definition={"forecast_contract": sample_binary_forecast_contract()},
            forecast_contract=sample_binary_forecast_contract(
                question="Will a different event occur?"
            ),
        )


def test_forecast_contract_from_definition_handles_missing_and_invalid_shapes() -> None:
    assert forecast_contract_from_definition({"id": "trend-a"}) is None

    with pytest.raises(ValueError, match="must be a mapping"):
        forecast_contract_from_definition({"forecast_contract": "bad"})
