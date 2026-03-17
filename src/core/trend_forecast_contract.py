"""Canonical forecast-contract schema for trend probabilities."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TrendForecastHorizon(BaseModel):
    """Explicit horizon semantics for a forecast question."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["fixed_date", "rolling_window"]
    fixed_date: date | None = None
    value: int | None = Field(default=None, ge=1)
    unit: Literal["days", "months", "years"] | None = None
    reference_point: Literal["evaluation_date"] | None = None

    @model_validator(mode="after")
    def _validate_horizon_shape(self) -> TrendForecastHorizon:
        if self.kind == "fixed_date":
            if self.fixed_date is None:
                msg = "Fixed-date horizons require fixed_date"
                raise ValueError(msg)
            if self.value is not None or self.unit is not None or self.reference_point is not None:
                msg = "Fixed-date horizons cannot set value, unit, or reference_point"
                raise ValueError(msg)
            return self

        if self.value is None or self.unit is None or self.reference_point is None:
            msg = "Rolling-window horizons require value, unit, and reference_point"
            raise ValueError(msg)
        if self.fixed_date is not None:
            msg = "Rolling-window horizons cannot set fixed_date"
            raise ValueError(msg)
        return self


class TrendForecastContract(BaseModel):
    """Explicit contract describing what a trend probability forecasts."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=10)
    horizon: TrendForecastHorizon
    resolution_basis: str = Field(..., min_length=1)
    resolver_source: str = Field(..., min_length=1)
    resolver_basis: str = Field(..., min_length=1)
    closure_rule: Literal["binary_event_by_horizon", "threshold_state_at_horizon"]
    occurrence_definition: str | None = Field(default=None, min_length=1)
    non_occurrence_definition: str | None = Field(default=None, min_length=1)

    @field_validator(
        "question",
        "resolution_basis",
        "resolver_source",
        "resolver_basis",
        "occurrence_definition",
        "non_occurrence_definition",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("question")
    @classmethod
    def _require_question_mark(cls, value: str) -> str:
        if not value.endswith("?"):
            msg = "Forecast question must end with '?'"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_closure_rule_requirements(self) -> TrendForecastContract:
        if self.closure_rule == "binary_event_by_horizon":
            if self.occurrence_definition is None or self.non_occurrence_definition is None:
                msg = (
                    "Binary-event forecast contracts require both occurrence_definition "
                    "and non_occurrence_definition"
                )
                raise ValueError(msg)
            return self

        if self.occurrence_definition is not None or self.non_occurrence_definition is not None:
            msg = (
                "Threshold-at-horizon forecast contracts must encode the measurable state "
                "in resolution_basis instead of occurrence_definition/non_occurrence_definition"
            )
            raise ValueError(msg)
        return self


def normalize_forecast_contract_payload(
    forecast_contract: TrendForecastContract | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a normalized JSON-safe forecast-contract payload."""

    if forecast_contract is None:
        return None

    if isinstance(forecast_contract, TrendForecastContract):
        normalized = forecast_contract
    elif isinstance(forecast_contract, dict):
        normalized = TrendForecastContract.model_validate(forecast_contract)
    else:
        msg = "forecast_contract must be a mapping"
        raise ValueError(msg)

    return normalized.model_dump(mode="json", exclude_none=True)
