"""
Trend configuration schema validation for YAML files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrendDisqualifier(BaseModel):
    """Condition that invalidates or resets a trend estimate."""

    signal: str = Field(..., min_length=1)
    effect: Literal["reset_to_baseline", "reassess", "invalidate"]
    description: str = Field(..., min_length=1)


class TrendFalsificationCriteria(BaseModel):
    """Human-readable criteria that would change confidence in the model."""

    decrease_confidence: list[str] = Field(default_factory=list)
    increase_confidence: list[str] = Field(default_factory=list)
    would_invalidate_model: list[str] = Field(default_factory=list)


class TrendIndicatorConfig(BaseModel):
    """Indicator configuration for one signal type."""

    weight: float = Field(..., ge=0.0, le=1.0)
    direction: Literal["escalatory", "de_escalatory"]
    type: Literal["leading", "lagging"] = "leading"
    keywords: list[str] = Field(default_factory=list)


class TrendConfig(BaseModel):
    """Validated shape for `config/trends/*.yaml` files."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str = Field(..., min_length=1)
    description: str | None = None
    baseline_probability: float = Field(..., ge=0.0, le=1.0)
    decay_half_life_days: int = Field(default=30, ge=1)
    indicators: dict[str, TrendIndicatorConfig] = Field(default_factory=dict)
    disqualifiers: list[TrendDisqualifier] = Field(default_factory=list)
    falsification_criteria: TrendFalsificationCriteria = Field(
        default_factory=TrendFalsificationCriteria
    )
