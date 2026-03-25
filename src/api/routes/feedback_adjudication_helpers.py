"""Typed event adjudication helpers built on top of existing feedback mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes._feedback_write_mutations import apply_event_feedback_mutation
from src.api.routes._privileged_write_contract import event_revision_token
from src.api.routes.event_review_metadata import load_event_review_metadata
from src.api.routes.feedback_models import (
    EventAdjudicationRequest,
    EventAdjudicationResponse,
    EventFeedbackRequest,
)
from src.storage.restatement_models import EventAdjudication

if TYPE_CHECKING:
    from src.storage.models import Event

FeedbackEventAction = Literal["pin", "mark_noise", "restate"]

_OUTCOME_TO_OVERRIDE_INTENT = {
    "confirm": "pin_event",
    "suppress": "suppress_event",
    "restate": "apply_restatement",
    "escalate_taxonomy_review": "taxonomy_escalation",
}
_OUTCOME_TO_REVIEW_STATUS = {
    "confirm": "resolved",
    "suppress": "resolved",
    "restate": "resolved",
    "escalate_taxonomy_review": "needs_taxonomy_review",
}
_OUTCOME_TO_FEEDBACK_ACTION: dict[str, FeedbackEventAction] = {
    "confirm": "pin",
    "suppress": "mark_noise",
    "restate": "restate",
}


@dataclass(slots=True)
class EventAdjudicationMutationResult:
    """Event adjudication write result plus audit linkage data."""

    adjudication: EventAdjudication
    target_revision_token: str
    result_links: dict[str, Any]


def _feedback_request_for_adjudication(
    payload: EventAdjudicationRequest,
) -> EventFeedbackRequest | None:
    action = _OUTCOME_TO_FEEDBACK_ACTION.get(payload.outcome)
    if action is None:
        return None
    return EventFeedbackRequest(
        action=action,
        notes=payload.notes,
        created_by=payload.created_by,
        restatement_targets=payload.restatement_targets,
    )


def to_event_adjudication_response(
    adjudication: EventAdjudication,
    *,
    target_revision_token: str | None = None,
) -> EventAdjudicationResponse:
    """Normalize an adjudication row into the API contract."""

    return EventAdjudicationResponse(
        id=adjudication.id,
        event_id=adjudication.event_id,
        feedback_id=adjudication.feedback_id,
        outcome=adjudication.outcome,
        review_status=adjudication.review_status,
        override_intent=adjudication.override_intent,
        resulting_effect=adjudication.resulting_effect,
        notes=adjudication.notes,
        created_by=adjudication.created_by,
        target_revision_token=target_revision_token,
        created_at=adjudication.created_at,
    )


async def apply_event_adjudication_mutation(
    *,
    session: AsyncSession,
    event_id: UUID,
    event: Event,
    payload: EventAdjudicationRequest,
) -> EventAdjudicationMutationResult:
    """Apply one typed event adjudication and return audit linkage metadata."""

    feedback_request = _feedback_request_for_adjudication(payload)
    feedback_result = None
    if feedback_request is not None:
        feedback_result = await apply_event_feedback_mutation(
            session=session,
            event_id=event_id,
            event=event,
            payload=feedback_request,
        )

    review_metadata = (
        await load_event_review_metadata(session=session, event_ids=(event_id,))
    ).get(event_id)
    open_taxonomy_gap_count = (
        review_metadata.open_taxonomy_gap_count if review_metadata is not None else 0
    )
    resulting_effect: dict[str, Any] = {
        "outcome": payload.outcome,
        "review_status": _OUTCOME_TO_REVIEW_STATUS[payload.outcome],
        "override_intent": _OUTCOME_TO_OVERRIDE_INTENT[payload.outcome],
        "open_taxonomy_gap_count": open_taxonomy_gap_count,
    }
    if feedback_result is not None:
        feedback = feedback_result.feedback
        resulting_effect["feedback_action"] = feedback.action
        if feedback.corrected_value is not None:
            resulting_effect["feedback_effect"] = feedback.corrected_value
        if feedback_result.result_links.get("restatement_ids"):
            resulting_effect["restatement_ids"] = feedback_result.result_links["restatement_ids"]

    adjudication = EventAdjudication(
        id=uuid4(),
        event_id=event_id,
        feedback_id=feedback_result.feedback.id if feedback_result is not None else None,
        outcome=payload.outcome,
        review_status=_OUTCOME_TO_REVIEW_STATUS[payload.outcome],
        override_intent=_OUTCOME_TO_OVERRIDE_INTENT[payload.outcome],
        resulting_effect=resulting_effect,
        notes=payload.notes,
        created_by=payload.created_by,
        created_at=datetime.now(tz=UTC),
    )
    session.add(adjudication)
    await session.flush()

    target_revision_token = (
        feedback_result.target_revision_token
        if feedback_result is not None
        else event_revision_token(event)
    )
    result_links = {
        "event_id": str(event_id),
        "adjudication_id": str(adjudication.id),
    }
    if feedback_result is not None:
        result_links["feedback_id"] = str(feedback_result.feedback.id)
        if feedback_result.result_links.get("restatement_ids"):
            result_links["restatement_ids"] = feedback_result.result_links["restatement_ids"]
    return EventAdjudicationMutationResult(
        adjudication=adjudication,
        target_revision_token=target_revision_token,
        result_links=result_links,
    )
