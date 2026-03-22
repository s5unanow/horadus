"""Shared mutation helpers for privileged feedback and override writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes._privileged_write_contract import event_revision_token, trend_revision_token
from src.api.routes.feedback_event_helpers import (
    event_feedback_corrected_value,
    event_feedback_original_value,
)
from src.api.routes.feedback_restatement import (
    apply_compensation_without_trend,
    invalidation_compensation_delta,
    load_prior_compensation_by_evidence_id,
    validate_restatement_targets,
)
from src.core.trend_engine import TrendEngine
from src.core.trend_restatement import HISTORICAL_ARTIFACT_POLICY, apply_compensating_restatement
from src.storage.event_state import (
    EventActivityState,
    EventEpistemicState,
    apply_event_state_update,
    event_state_snapshot,
    resolved_event_activity_state,
)
from src.storage.models import Event, Trend, TrendEvidence
from src.storage.restatement_models import HumanFeedback

if TYPE_CHECKING:
    from src.api.routes.feedback_models import (
        EventFeedbackRequest,
        EventRestatementTarget,
        TrendOverrideRequest,
    )


@dataclass(slots=True)
class FeedbackMutationResult:
    """Feedback write result plus linkage data for auditing."""

    feedback: HumanFeedback
    target_revision_token: str
    result_links: dict[str, Any]


async def _active_event_evidence(*, session: AsyncSession, event_id: UUID) -> list[TrendEvidence]:
    return list(
        (
            await session.scalars(
                select(TrendEvidence)
                .where(TrendEvidence.event_id == event_id)
                .where(TrendEvidence.is_invalidated.is_(False))
                .order_by(TrendEvidence.created_at.asc())
            )
        ).all()
    )


async def _trend_map(
    *,
    session: AsyncSession,
    trend_ids: set[UUID],
) -> dict[UUID, Trend]:
    if not trend_ids:
        return {}
    trends = list(
        (await session.scalars(select(Trend).where(Trend.id.in_(tuple(trend_ids))))).all()
    )
    return {trend.id: trend for trend in trends if trend.id is not None}


async def _apply_event_feedback_restatements(
    *,
    session: AsyncSession,
    event: Event,
    feedback: HumanFeedback,
    evidences: list[TrendEvidence],
    action: str,
    notes: str | None,
    invalidate_evidence: bool,
    target_by_evidence_id: dict[UUID, EventRestatementTarget] | None = None,
    changed_axes: tuple[str, ...] = (),
    axis_reasons: dict[str, str] | None = None,
) -> list[str]:
    trend_engine = TrendEngine(session=session)
    trend_by_id = await _trend_map(
        session=session, trend_ids={evidence.trend_id for evidence in evidences}
    )
    prior_compensation_by_evidence_id = await load_prior_compensation_by_evidence_id(
        session=session, evidences=evidences
    )
    recorded_at = datetime.now(tz=UTC)
    total_compensation_delta = 0.0
    restatement_ids: list[str] = []
    trend_adjustments: dict[str, dict[str, float]] = {}
    for evidence in evidences:
        if invalidate_evidence:
            evidence.is_invalidated = True
            evidence.invalidated_at = recorded_at
            evidence.invalidation_feedback_id = feedback.id
        target = (
            target_by_evidence_id.get(evidence.id)
            if target_by_evidence_id and evidence.id is not None
            else None
        )
        compensation_delta = (
            invalidation_compensation_delta(
                evidence=evidence,
                prior_compensation_by_evidence_id=prior_compensation_by_evidence_id,
            )
            if invalidate_evidence
            else float(target.compensation_delta_log_odds if target is not None else 0.0)
        )
        trend = trend_by_id.get(evidence.trend_id)
        if trend is None:
            trend_adjustment = await apply_compensation_without_trend(
                trend_engine=trend_engine,
                evidence=evidence,
                compensation_delta=compensation_delta,
                invalidate_evidence=invalidate_evidence,
            )
            if trend_adjustment is None:
                continue
            previous_log_odds, new_log_odds = trend_adjustment
            trend_adjustments[str(evidence.trend_id)] = {
                "previous_log_odds": previous_log_odds,
                "new_log_odds": new_log_odds,
                "delta_applied": compensation_delta,
            }
            total_compensation_delta += compensation_delta
            continue
        previous_log_odds = float(trend.current_log_odds)
        restatement = await apply_compensating_restatement(
            trend_engine=trend_engine,
            trend=trend,
            compensation_delta_log_odds=compensation_delta,
            restatement_kind=(
                "full_invalidation" if invalidate_evidence else "partial_restatement"
            ),
            source="event_feedback",
            recorded_at=recorded_at,
            trend_evidence=evidence,
            feedback_id=feedback.id,
            original_evidence_delta_log_odds=float(evidence.delta_log_odds),
            notes=target.notes if target is not None and target.notes is not None else notes,
            details={"event_action": action},
        )
        if restatement.id is not None:
            restatement_ids.append(str(restatement.id))
        trend_key = str(trend.id)
        adjustment = trend_adjustments.get(
            trend_key,
            {
                "previous_log_odds": previous_log_odds,
                "new_log_odds": float(trend.current_log_odds),
                "delta_applied": 0.0,
            },
        )
        adjustment["new_log_odds"] = float(trend.current_log_odds)
        adjustment["delta_applied"] += compensation_delta
        trend_adjustments[trend_key] = adjustment
        total_compensation_delta += compensation_delta
    corrected_value = event_feedback_corrected_value(
        action=action,
        event_id=feedback.target_id,
        at=recorded_at,
        evidences=evidences,
        total_compensation_delta=total_compensation_delta,
        trend_adjustments=trend_adjustments,
        event=event,
        changed_axes=changed_axes,
        axis_reasons=axis_reasons,
    )
    corrected_value["restatement_ids"] = restatement_ids
    feedback.corrected_value = corrected_value
    return restatement_ids


async def apply_event_feedback_mutation(
    *,
    session: AsyncSession,
    event_id: UUID,
    event: Event,
    payload: EventFeedbackRequest,
) -> FeedbackMutationResult:
    """Apply an event feedback mutation and return audit linkage metadata."""

    original_value: dict[str, Any] | None = None
    corrected_value: dict[str, Any] | None = None
    evidences: list[TrendEvidence] = []
    restatement_targets: dict[UUID, EventRestatementTarget] | None = None
    changed_axes: tuple[str, ...] = ()
    axis_reasons: dict[str, str] | None = None
    if payload.action == "mark_noise":
        original_value = event_state_snapshot(event)
        apply_event_state_update(
            event,
            epistemic_state=EventEpistemicState.RETRACTED.value,
            activity_state=EventActivityState.CLOSED.value,
        )
        corrected_value = {
            **event_state_snapshot(event),
            "changed_axes": ["epistemic", "activity"],
            "axis_reasons": {
                "epistemic": "operator_mark_noise",
                "activity": "operator_mark_noise",
            },
        }
    elif payload.action in {"invalidate", "restate"}:
        evidences = await _active_event_evidence(session=session, event_id=event_id)
        if payload.action == "restate":
            evidences, restatement_targets = validate_restatement_targets(
                evidences=evidences,
                targets=payload.restatement_targets,
            )
        original_value = event_feedback_original_value(evidences, event=event)
        if payload.action == "invalidate":
            apply_event_state_update(
                event,
                epistemic_state=EventEpistemicState.RETRACTED.value,
                activity_state=resolved_event_activity_state(event),
            )
            changed_axes = ("epistemic",)
            axis_reasons = {"epistemic": "operator_invalidation"}
        corrected_value = event_feedback_corrected_value(
            action=payload.action,
            event_id=event_id,
            at=datetime.now(tz=UTC),
            evidences=evidences,
            total_compensation_delta=(
                -sum(float(evidence.delta_log_odds) for evidence in evidences)
                if payload.action == "invalidate"
                else sum(
                    target.compensation_delta_log_odds for target in payload.restatement_targets
                )
            ),
            event=event,
            changed_axes=changed_axes,
            axis_reasons=axis_reasons,
        )
    feedback = HumanFeedback(
        target_type="event",
        target_id=event_id,
        action=payload.action,
        original_value=original_value,
        corrected_value=corrected_value,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    session.add(feedback)
    await session.flush()
    restatement_ids: list[str] = []
    if payload.action in {"invalidate", "restate"} and evidences:
        restatement_ids = await _apply_event_feedback_restatements(
            session=session,
            event=event,
            feedback=feedback,
            evidences=evidences,
            action=payload.action,
            notes=payload.notes,
            invalidate_evidence=payload.action == "invalidate",
            target_by_evidence_id=restatement_targets,
            changed_axes=changed_axes,
            axis_reasons=axis_reasons,
        )
    else:
        feedback.corrected_value = corrected_value
    await session.flush()
    await session.refresh(
        event,
        attribute_names=[
            "canonical_summary",
            "epistemic_state",
            "activity_state",
            "lifecycle_status",
            "has_contradictions",
            "contradiction_notes",
            "source_count",
            "unique_source_count",
            "independent_evidence_count",
            "last_mention_at",
            "last_updated_at",
        ],
    )
    target_revision = event_revision_token(event)
    result_links: dict[str, Any] = {
        "event_id": str(event_id),
        "feedback_id": str(feedback.id),
    }
    if restatement_ids:
        result_links["restatement_ids"] = restatement_ids
    return FeedbackMutationResult(
        feedback=feedback,
        target_revision_token=target_revision,
        result_links=result_links,
    )


async def apply_trend_override_mutation(
    *,
    session: AsyncSession,
    trend_id: UUID,
    trend: Trend,
    payload: TrendOverrideRequest,
) -> FeedbackMutationResult:
    """Apply a manual trend override and return audit linkage metadata."""

    previous_log_odds = float(trend.current_log_odds)
    compensation_delta = float(payload.delta_log_odds)
    feedback = HumanFeedback(
        target_type="trend",
        target_id=trend_id,
        action="override_delta",
        original_value={"current_log_odds": previous_log_odds},
        corrected_value={
            "delta_log_odds": compensation_delta,
            "new_log_odds": previous_log_odds + compensation_delta,
            "historical_artifact_policy": HISTORICAL_ARTIFACT_POLICY,
        },
        notes=payload.notes,
        created_by=payload.created_by,
    )
    session.add(feedback)
    await session.flush()
    restatement = await apply_compensating_restatement(
        trend_engine=TrendEngine(session=session),
        trend=trend,
        compensation_delta_log_odds=compensation_delta,
        restatement_kind="manual_compensation",
        source="trend_override",
        feedback_id=feedback.id,
        notes=payload.notes,
        details={"feedback_action": "override_delta"},
    )
    corrected_value = feedback.corrected_value if isinstance(feedback.corrected_value, dict) else {}
    corrected_value["new_log_odds"] = float(trend.current_log_odds)
    restatement_ids = [str(restatement.id)] if restatement.id is not None else []
    if restatement_ids:
        corrected_value["restatement_ids"] = restatement_ids
    feedback.corrected_value = corrected_value
    await session.flush()
    return FeedbackMutationResult(
        feedback=feedback,
        target_revision_token=trend_revision_token(trend),
        result_links={
            "trend_id": str(trend_id),
            "feedback_id": str(feedback.id),
            "restatement_ids": restatement_ids,
        },
    )
