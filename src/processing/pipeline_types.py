"""Ownership-local types for processing pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.storage.models import ProcessingStatus, RawItem


@dataclass(slots=True)
class PipelineUsage:
    """Usage and API call metrics across one pipeline run."""

    embedding_api_calls: int = 0
    embedding_estimated_cost_usd: float = 0.0
    tier1_prompt_tokens: int = 0
    tier1_completion_tokens: int = 0
    tier1_api_calls: int = 0
    tier1_estimated_cost_usd: float = 0.0
    tier2_prompt_tokens: int = 0
    tier2_completion_tokens: int = 0
    tier2_api_calls: int = 0
    tier2_estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class PipelineItemResult:
    """Result of processing one raw item."""

    item_id: UUID
    final_status: ProcessingStatus
    event_id: UUID | None = None
    duplicate: bool = False
    embedded: bool = False
    event_created: bool = False
    event_merged: bool = False
    tier2_applied: bool = False
    degraded_llm_hold: bool = False
    replay_enqueued: bool = False
    trend_impacts_seen: int = 0
    trend_updates: int = 0
    error_message: str | None = None


@dataclass(slots=True)
class PipelineRunResult:
    """Summary metrics for one pipeline run."""

    scanned: int = 0
    processed: int = 0
    classified: int = 0
    noise: int = 0
    duplicates: int = 0
    errors: int = 0
    embedded: int = 0
    events_created: int = 0
    events_merged: int = 0
    trend_impacts_seen: int = 0
    trend_updates: int = 0
    degraded_llm: bool = False
    degraded_holds: int = 0
    replay_enqueued: int = 0
    results: list[PipelineItemResult] = field(default_factory=list)
    usage: PipelineUsage = field(default_factory=PipelineUsage)


@dataclass(slots=True)
class _ItemExecution:
    """Internal execution details for one processed item."""

    result: PipelineItemResult
    usage: PipelineUsage = field(default_factory=PipelineUsage)


@dataclass(slots=True)
class _PreparedItem:
    """Item state prepared for Tier-1 batch classification."""

    item: RawItem
    item_id: UUID
    raw_content: str
