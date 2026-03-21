"""Shared response models used by trend routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrendConfigLoadResponse(BaseModel):
    """Summary for loading trends from YAML config files."""

    loaded_files: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class TrendDefinitionVersionResponse(BaseModel):
    """Response body for one trend-definition history row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trend_id: UUID
    definition_hash: str
    definition: dict[str, Any]
    actor: str | None
    context: str | None
    recorded_at: datetime


class TrendEvidenceResponse(BaseModel):
    """Response body for one evidence record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "event_claim_id": "5b1fdf8a-327d-4b3f-82e0-1f53dfcccf63",
                "signal_type": "military_movement",
                "trend_definition_hash": "definition-hash-example-v1",
                "scoring_math_version": "trend-scoring-v1",
                "scoring_parameter_set": "stable-default-v1",
                "credibility_score": 0.9,
                "corroboration_factor": 0.67,
                "novelty_score": 1.0,
                "evidence_age_days": 2.4,
                "temporal_decay_factor": 0.91,
                "severity_score": 0.8,
                "confidence_score": 0.95,
                "delta_log_odds": 0.021,
                "reasoning": "Multiple corroborated force-movement reports.",
                "is_invalidated": False,
                "invalidated_at": None,
                "invalidation_feedback_id": None,
                "created_at": "2026-02-07T18:00:00Z",
            }
        },
    )

    id: UUID
    trend_id: UUID
    event_id: UUID
    event_claim_id: UUID
    signal_type: str
    trend_definition_hash: str | None
    scoring_math_version: str
    scoring_parameter_set: str
    credibility_score: float | None
    corroboration_factor: float | None
    novelty_score: float | None
    evidence_age_days: float | None
    temporal_decay_factor: float | None
    severity_score: float | None
    confidence_score: float | None
    delta_log_odds: float
    reasoning: str | None
    is_invalidated: bool
    invalidated_at: datetime | None
    invalidation_feedback_id: UUID | None
    created_at: datetime


class TrendHistoryPoint(BaseModel):
    """Response body for one historical trend snapshot."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-02-07T18:00:00Z",
                "log_odds": -1.65,
                "probability": 0.161,
            }
        }
    )

    timestamp: datetime
    log_odds: float
    probability: float
