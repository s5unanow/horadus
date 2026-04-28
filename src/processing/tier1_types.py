"""Tier 1 classifier data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


@dataclass(slots=True)
class TrendRelevanceScore:
    """Per-trend relevance score for one item."""

    trend_id: str
    relevance_score: int
    rationale: str | None = None


@dataclass(slots=True)
class Tier1ItemResult:
    """Tier 1 classification decision for one raw item."""

    item_id: UUID
    max_relevance: int
    should_queue_tier2: bool
    trend_scores: list[TrendRelevanceScore] = field(default_factory=list)


@dataclass(slots=True)
class Tier1Usage:
    """Usage and cost metrics for one classifier run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    active_provider: str | None = None
    active_model: str | None = None
    active_reasoning_effort: str | None = None
    used_secondary_route: bool = False


@dataclass(slots=True)
class Tier1RunResult:
    """Summary of classifying pending items."""

    scanned: int = 0
    noise_count: int = 0
    queued_count: int = 0
    queued_item_ids: list[UUID] = field(default_factory=list)
    results: list[Tier1ItemResult] = field(default_factory=list)
    usage: Tier1Usage = field(default_factory=Tier1Usage)


class TrendScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_id: str = Field(min_length=1)
    relevance_score: int = Field(ge=0, le=10)
    rationale: str | None = None


class ItemOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    trend_scores: list[TrendScoreOutput] = Field()


class Tier1Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ItemOutput] = Field(min_length=1)
