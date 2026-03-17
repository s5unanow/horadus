"""Pydantic request/response models for trend routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

import src.core.risk as risk_module  # noqa: TC001
import src.core.trend_forecast_contract as trend_forecast_contract_module  # noqa: TC001
import src.storage.models as storage_models  # noqa: TC001


class TrendCreate(BaseModel):
    """Request body for creating a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "EU-Russia Military Conflict",
                "description": "Probability of direct military confrontation.",
                "definition": {"region": "Europe"},
                "forecast_contract": {
                    "question": (
                        "Will direct military conflict involving Russia and one or more "
                        "European NATO states occur by 2030-12-31?"
                    ),
                    "horizon": {"kind": "fixed_date", "fixed_date": "2030-12-31"},
                    "resolution_basis": (
                        "Binary event question resolved against attributable direct "
                        "state-on-state hostilities, excluding proxy-only confrontation."
                    ),
                    "resolver_source": (
                        "Official state/alliance statements plus multi-source "
                        "corroborated reporting."
                    ),
                    "resolver_basis": (
                        "Resolve yes on confirmed direct hostilities; resolve no if "
                        "none occur by the horizon date."
                    ),
                    "closure_rule": "binary_event_by_horizon",
                    "occurrence_definition": (
                        "Confirmed direct combat engagement between Russian forces and "
                        "one or more European NATO member-state forces."
                    ),
                    "non_occurrence_definition": (
                        "No confirmed direct combat engagement between Russian forces "
                        "and one or more European NATO member-state forces by the "
                        "horizon date."
                    ),
                },
                "baseline_probability": 0.08,
                "current_probability": 0.10,
                "indicators": {
                    "military_movement": {"direction": "escalatory", "weight": 0.04},
                    "diplomatic_talks": {"direction": "de_escalatory", "weight": 0.03},
                },
                "decay_half_life_days": 30,
                "is_active": True,
            }
        }
    )

    name: str = Field(..., min_length=1)
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    forecast_contract: trend_forecast_contract_module.TrendForecastContract
    baseline_probability: float = Field(..., ge=0, le=1)
    current_probability: float | None = Field(default=None, ge=0, le=1)
    indicators: dict[str, Any] = Field(default_factory=dict)
    decay_half_life_days: int = Field(default=30, ge=1)
    is_active: bool = True


class TrendUpdate(BaseModel):
    """Request body for updating a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_probability": 0.18,
                "decay_half_life_days": 45,
                "forecast_contract": {
                    "question": (
                        "Will direct military conflict involving Russia and one or more "
                        "European NATO states occur by 2030-12-31?"
                    ),
                    "horizon": {"kind": "fixed_date", "fixed_date": "2030-12-31"},
                    "resolution_basis": (
                        "Binary event question resolved against attributable direct "
                        "state-on-state hostilities, excluding proxy-only confrontation."
                    ),
                    "resolver_source": (
                        "Official state/alliance statements plus multi-source "
                        "corroborated reporting."
                    ),
                    "resolver_basis": (
                        "Resolve yes on confirmed direct hostilities; resolve no if "
                        "none occur by the horizon date."
                    ),
                    "closure_rule": "binary_event_by_horizon",
                    "occurrence_definition": (
                        "Confirmed direct combat engagement between Russian forces and "
                        "one or more European NATO member-state forces."
                    ),
                    "non_occurrence_definition": (
                        "No confirmed direct combat engagement between Russian forces "
                        "and one or more European NATO member-state forces by the "
                        "horizon date."
                    ),
                },
                "is_active": True,
            }
        }
    )

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    definition: dict[str, Any] | None = None
    forecast_contract: trend_forecast_contract_module.TrendForecastContract | None = None
    baseline_probability: float | None = Field(default=None, ge=0, le=1)
    current_probability: float | None = Field(default=None, ge=0, le=1)
    indicators: dict[str, Any] | None = None
    decay_half_life_days: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class TrendResponse(BaseModel):
    """Response body for a trend."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "name": "EU-Russia Military Conflict",
                "description": "Probability of direct military confrontation.",
                "definition": {"id": "eu-russia-military-conflict"},
                "forecast_contract": {
                    "question": (
                        "Will direct military conflict involving Russia and one or more "
                        "European NATO states occur by 2030-12-31?"
                    ),
                    "horizon": {"kind": "fixed_date", "fixed_date": "2030-12-31"},
                    "resolution_basis": (
                        "Binary event question resolved against attributable direct "
                        "state-on-state hostilities, excluding proxy-only confrontation."
                    ),
                    "resolver_source": (
                        "Official state/alliance statements plus multi-source "
                        "corroborated reporting."
                    ),
                    "resolver_basis": (
                        "Resolve yes on confirmed direct hostilities; resolve no if "
                        "none occur by the horizon date."
                    ),
                    "closure_rule": "binary_event_by_horizon",
                    "occurrence_definition": (
                        "Confirmed direct combat engagement between Russian forces and "
                        "one or more European NATO member-state forces."
                    ),
                    "non_occurrence_definition": (
                        "No confirmed direct combat engagement between Russian forces "
                        "and one or more European NATO member-state forces by the "
                        "horizon date."
                    ),
                },
                "baseline_probability": 0.08,
                "current_probability": 0.18,
                "risk_level": "guarded",
                "probability_band": [0.11, 0.25],
                "confidence": "medium",
                "top_movers_7d": [
                    "Multiple sources corroborate force-movement reports.",
                    "Diplomatic talks were suspended after border incident.",
                ],
                "indicators": {"military_movement": {"direction": "escalatory", "weight": 0.04}},
                "decay_half_life_days": 30,
                "is_active": True,
                "updated_at": "2026-02-07T19:56:00Z",
            }
        },
    )

    id: UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    forecast_contract: trend_forecast_contract_module.TrendForecastContract | None
    baseline_probability: float
    current_probability: float
    risk_level: str
    probability_band: tuple[float, float]
    confidence: risk_module.ConfidenceRating
    top_movers_7d: list[str]
    indicators: dict[str, Any]
    decay_half_life_days: int
    is_active: bool
    updated_at: datetime


class RemoveEventImpactSimulationRequest(BaseModel):
    """Simulation payload for removing historical event impact from a trend."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "remove_event_impact",
                "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "signal_type": "military_movement",
            }
        }
    )

    mode: Literal["remove_event_impact"]
    event_id: UUID
    signal_type: str | None = Field(default=None, min_length=1)


class InjectHypotheticalSignalSimulationRequest(BaseModel):
    """Simulation payload for injecting a hypothetical signal impact."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "inject_hypothetical_signal",
                "signal_type": "military_movement",
                "indicator_weight": 0.04,
                "source_credibility": 0.9,
                "corroboration_count": 3,
                "novelty_score": 1.0,
                "direction": "escalatory",
                "severity": 0.8,
                "confidence": 0.95,
            }
        }
    )

    mode: Literal["inject_hypothetical_signal"]
    signal_type: str = Field(..., min_length=1)
    indicator_weight: float = Field(..., gt=0)
    source_credibility: float = Field(..., ge=0, le=1)
    corroboration_count: int = Field(..., ge=1)
    novelty_score: float = Field(..., ge=0, le=1)
    direction: Literal["escalatory", "de_escalatory"]
    severity: float = Field(default=1.0, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)


TrendSimulationRequest = Annotated[
    RemoveEventImpactSimulationRequest | InjectHypotheticalSignalSimulationRequest,
    Field(discriminator="mode"),
]


class TrendSimulationResponse(BaseModel):
    """Response payload for counterfactual trend simulations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "inject_hypothetical_signal",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "current_probability": 0.18,
                "projected_probability": 0.204,
                "delta_probability": 0.024,
                "delta_log_odds": 0.15,
                "factor_breakdown": {
                    "base_weight": 0.04,
                    "severity": 0.8,
                    "confidence": 0.95,
                    "credibility": 0.9,
                    "corroboration": 0.577,
                    "novelty": 1.0,
                    "direction_multiplier": 1.0,
                    "raw_delta": 0.0158,
                    "clamped_delta": 0.0158,
                },
            }
        }
    )

    mode: Literal["remove_event_impact", "inject_hypothetical_signal"]
    trend_id: UUID
    current_probability: float
    projected_probability: float
    delta_probability: float
    delta_log_odds: float
    factor_breakdown: dict[str, Any]


class TrendOutcomeCreate(BaseModel):
    """Request body for recording a trend outcome."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outcome": "occurred",
                "outcome_date": "2026-02-07T00:00:00Z",
                "outcome_notes": "Frontline engagements confirmed by multiple sources.",
                "outcome_evidence": {"report_ids": ["abc-123", "def-456"]},
                "recorded_by": "analyst@horadus",
            }
        }
    )

    outcome: storage_models.OutcomeType
    outcome_date: datetime
    outcome_notes: str | None = None
    outcome_evidence: dict[str, Any] | None = None
    recorded_by: str | None = None


class TrendOutcomeResponse(BaseModel):
    """Response body for one recorded trend outcome."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "f4f9f95b-82f7-42f0-a628-f44ca8d50f55",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "prediction_date": "2026-02-07T00:00:00Z",
                "predicted_probability": 0.31,
                "predicted_risk_level": "elevated",
                "probability_band_low": 0.21,
                "probability_band_high": 0.41,
                "outcome_date": "2026-02-07T00:00:00Z",
                "outcome": "occurred",
                "outcome_notes": "Confirmed military engagement.",
                "outcome_evidence": {"report_ids": ["abc-123"]},
                "brier_score": 0.4761,
                "recorded_by": "analyst@horadus",
                "created_at": "2026-02-07T00:05:00Z",
            }
        },
    )

    id: UUID
    trend_id: UUID
    prediction_date: datetime
    predicted_probability: float
    predicted_risk_level: str
    probability_band_low: float
    probability_band_high: float
    outcome_date: datetime | None
    outcome: str | None
    outcome_notes: str | None
    outcome_evidence: dict[str, Any] | None
    brier_score: float | None
    recorded_by: str | None
    created_at: datetime


class CalibrationBucketResponse(BaseModel):
    """One bucket in a calibration report."""

    bucket_start: float
    bucket_end: float
    prediction_count: int
    occurred_count: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


class TrendCalibrationResponse(BaseModel):
    """Calibration report response payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "total_predictions": 14,
                "resolved_predictions": 10,
                "mean_brier_score": 0.18,
                "overconfident": False,
                "underconfident": False,
                "buckets": [
                    {
                        "bucket_start": 0.2,
                        "bucket_end": 0.3,
                        "prediction_count": 4,
                        "occurred_count": 1,
                        "actual_rate": 0.25,
                        "expected_rate": 0.25,
                        "calibration_error": 0.0,
                    }
                ],
            }
        }
    )

    trend_id: UUID
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float | None
    overconfident: bool
    underconfident: bool
    buckets: list[CalibrationBucketResponse]


class RetrospectiveEvent(BaseModel):
    """One pivotal event in retrospective analysis."""

    event_id: UUID
    summary: str
    categories: list[str]
    evidence_count: int
    net_delta_log_odds: float
    abs_delta_log_odds: float
    direction: Literal["up", "down", "mixed"]


class RetrospectiveSignal(BaseModel):
    """One predictive signal summary in retrospective analysis."""

    signal_type: str
    evidence_count: int
    net_delta_log_odds: float
    abs_delta_log_odds: float


class TrendRetrospectiveResponse(BaseModel):
    """Trend retrospective analysis response payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "trend_name": "EU-Russia Military Conflict",
                "period_start": "2026-01-08T00:00:00Z",
                "period_end": "2026-02-07T00:00:00Z",
                "pivotal_events": [
                    {
                        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                        "summary": "Large troop repositioning near border sectors.",
                        "categories": ["military"],
                        "evidence_count": 4,
                        "net_delta_log_odds": 0.132,
                        "abs_delta_log_odds": 0.132,
                        "direction": "up",
                    }
                ],
                "category_breakdown": {"military": 3, "diplomacy": 1},
                "predictive_signals": [
                    {
                        "signal_type": "military_movement",
                        "evidence_count": 5,
                        "net_delta_log_odds": 0.201,
                        "abs_delta_log_odds": 0.201,
                    }
                ],
                "accuracy_assessment": {
                    "outcome_count": 2,
                    "resolved_outcomes": 1,
                    "scored_outcomes": 1,
                    "mean_brier_score": 0.18,
                    "resolved_rate": 0.5,
                },
                "narrative": "Military movement signals were most predictive in this window.",
                "grounding_status": "grounded",
                "grounding_violation_count": 0,
                "grounding_references": None,
            }
        }
    )

    trend_id: UUID
    trend_name: str
    period_start: datetime
    period_end: datetime
    pivotal_events: list[RetrospectiveEvent]
    category_breakdown: dict[str, int]
    predictive_signals: list[RetrospectiveSignal]
    accuracy_assessment: dict[str, int | float | None]
    narrative: str
    grounding_status: str
    grounding_violation_count: int
    grounding_references: dict[str, Any] | None
