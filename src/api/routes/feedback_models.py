"""Pydantic models shared by feedback routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from src.storage.models import TaxonomyGap
    from src.storage.restatement_models import HumanFeedback


class FeedbackResponse(BaseModel):
    """Serialized feedback record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    action: str
    original_value: dict[str, Any] | None
    corrected_value: dict[str, Any] | None
    notes: str | None
    created_by: str | None
    created_at: datetime


class EventRestatementTarget(BaseModel):
    """One evidence-targeted compensating restatement."""

    evidence_id: UUID
    compensation_delta_log_odds: float = Field(
        ...,
        description="Signed compensating delta applied to the trend projection.",
    )
    notes: str | None = None


class EventFeedbackRequest(BaseModel):
    """Feedback actions supported for an event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "invalidate",
                "notes": "Conflicting source narratives and analyst override.",
                "created_by": "analyst@horadus",
            }
        }
    )

    action: Literal["pin", "mark_noise", "invalidate", "restate"]
    notes: str | None = None
    created_by: str | None = None
    restatement_targets: list[EventRestatementTarget] = Field(default_factory=list)


class TrendOverrideRequest(BaseModel):
    """Manual trend delta override request."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "delta_log_odds": -0.12,
                "notes": "Manual correction after source invalidation.",
                "created_by": "analyst@horadus",
            }
        }
    )

    delta_log_odds: float = Field(..., description="Manual adjustment in log-odds space")
    notes: str | None = None
    created_by: str | None = None


class ReviewQueueTrendImpact(BaseModel):
    """Trend-impact summary included in review queue items."""

    trend_id: UUID
    trend_name: str
    signal_type: str
    delta_log_odds: float
    confidence_score: float | None


class ReviewQueueItem(BaseModel):
    """Ranked event candidate for analyst review."""

    event_id: UUID
    summary: str
    epistemic_state: str
    activity_state: str
    lifecycle_status: str
    last_mention_at: datetime
    source_count: int
    unique_source_count: int
    has_contradictions: bool
    contradiction_notes: str | None
    evidence_count: int
    projected_delta: float
    uncertainty_score: float
    contradiction_risk: float
    ranking_score: float
    feedback_count: int
    feedback_actions: list[str]
    requires_human_verification: bool
    trend_impacts: list[ReviewQueueTrendImpact]


class TaxonomyGapResponse(BaseModel):
    """Serialized taxonomy-gap record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID | None
    trend_id: str
    signal_type: str
    reason: str
    source: str
    details: dict[str, Any]
    status: str
    resolution_notes: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    observed_at: datetime


class TaxonomyGapSummaryRow(BaseModel):
    """Grouped unknown signal-type count by trend+signal."""

    trend_id: str
    signal_type: str
    count: int


class TaxonomyGapListResponse(BaseModel):
    """Taxonomy-gap list and summary payload."""

    total_count: int
    open_count: int
    resolved_count: int
    rejected_count: int
    unknown_trend_count: int
    unknown_signal_count: int
    top_unknown_signal_keys_by_trend: list[TaxonomyGapSummaryRow]
    items: list[TaxonomyGapResponse]


class TaxonomyGapUpdateRequest(BaseModel):
    """Analyst update payload for taxonomy-gap triage."""

    status: Literal["open", "resolved", "rejected"]
    resolution_notes: str | None = None
    resolved_by: str | None = None


def to_feedback_response(feedback: HumanFeedback) -> FeedbackResponse:
    """Normalize a feedback row into the API contract."""

    feedback_id = feedback.id if feedback.id is not None else uuid4()
    created_at = feedback.created_at if feedback.created_at is not None else datetime.now(tz=UTC)
    return FeedbackResponse(
        id=feedback_id,
        target_type=feedback.target_type,
        target_id=feedback.target_id,
        action=feedback.action,
        original_value=feedback.original_value,
        corrected_value=feedback.corrected_value,
        notes=feedback.notes,
        created_by=feedback.created_by,
        created_at=created_at,
    )


def to_taxonomy_gap_response(gap: TaxonomyGap) -> TaxonomyGapResponse:
    """Normalize a taxonomy-gap row into the API contract."""

    gap_id = gap.id if gap.id is not None else uuid4()
    observed_at = gap.observed_at if gap.observed_at is not None else datetime.now(tz=UTC)
    return TaxonomyGapResponse(
        id=gap_id,
        event_id=gap.event_id,
        trend_id=gap.trend_id,
        signal_type=gap.signal_type,
        reason=str(gap.reason),
        source=gap.source or "pipeline",
        details=gap.details if isinstance(gap.details, dict) else {},
        status=str(gap.status),
        resolution_notes=gap.resolution_notes,
        resolved_by=gap.resolved_by,
        resolved_at=gap.resolved_at,
        observed_at=observed_at,
    )
