"""Feedback API endpoints for human corrections and annotations."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_privileged_access
from src.api.routes.feedback_models import (
    EventFeedbackRequest,
    EventRestatementTarget,
    FeedbackResponse,
    ReviewQueueItem,
    ReviewQueueTrendImpact,
    TaxonomyGapListResponse,
    TaxonomyGapResponse,
    TaxonomyGapSummaryRow,
    TaxonomyGapUpdateRequest,
    TrendOverrideRequest,
    to_feedback_response,
    to_taxonomy_gap_response,
)
from src.api.routes.feedback_restatement import (
    invalidation_compensation_delta,
    load_prior_compensation_by_evidence_id,
    validate_restatement_targets,
)
from src.core.trend_engine import TrendEngine
from src.core.trend_restatement import (
    HISTORICAL_ARTIFACT_POLICY,
    apply_compensating_restatement,
)
from src.storage.database import get_session
from src.storage.models import (
    Event,
    EventLifecycle,
    TaxonomyGap,
    TaxonomyGapReason,
    TaxonomyGapStatus,
    Trend,
    TrendEvidence,
)
from src.storage.restatement_models import HumanFeedback

router = APIRouter()


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


def _event_feedback_original_value(evidences: list[TrendEvidence]) -> dict[str, Any]:
    trend_deltas: dict[str, float] = {}
    for evidence in evidences:
        trend_key = str(evidence.trend_id)
        trend_deltas[trend_key] = trend_deltas.get(trend_key, 0.0) + float(evidence.delta_log_odds)
    return {
        "evidence_count": len(evidences),
        "active_evidence_ids": [
            str(evidence.id) for evidence in evidences if evidence.id is not None
        ],
        "active_event_claim_ids": sorted({str(evidence.event_claim_id) for evidence in evidences}),
        "trend_deltas": trend_deltas,
    }


def _event_feedback_corrected_value(
    *,
    action: str,
    event_id: UUID,
    at: datetime,
    evidences: list[TrendEvidence],
    total_compensation_delta: float,
    trend_adjustments: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    evidence_ids = [str(evidence.id) for evidence in evidences if evidence.id is not None]
    event_claim_ids = sorted({str(evidence.event_claim_id) for evidence in evidences})
    payload = {
        "event_id": str(event_id),
        "action": action,
        "affected_trend_count": len({evidence.trend_id for evidence in evidences}),
        "affected_evidence_count": len(evidences),
        "affected_evidence_ids": evidence_ids,
        "affected_event_claim_ids": event_claim_ids,
        "total_compensation_delta_log_odds": total_compensation_delta,
        "historical_artifact_policy": HISTORICAL_ARTIFACT_POLICY,
        "recorded_at": at.isoformat(),
    }
    if action == "invalidate":
        payload.update(
            {
                "reverted_event_id": str(event_id),
                "invalidated_evidence_count": len(evidences),
                "invalidated_evidence_ids": evidence_ids,
                "invalidated_event_claim_ids": event_claim_ids,
                "trend_adjustments": trend_adjustments or {},
                "invalidated_at": at.isoformat(),
            }
        )
    return payload


@router.get("/feedback", response_model=list[FeedbackResponse])
async def list_feedback(
    target_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[FeedbackResponse]:
    """
    List human feedback records.

    Supports optional filtering by target type and action.
    """
    query = select(HumanFeedback).order_by(HumanFeedback.created_at.desc()).limit(limit)
    if target_type is not None:
        query = query.where(HumanFeedback.target_type == target_type)
    if action is not None:
        query = query.where(HumanFeedback.action == action)

    records = list((await session.scalars(query)).all())
    return [to_feedback_response(record) for record in records]


@router.get("/taxonomy-gaps", response_model=TaxonomyGapListResponse)
async def list_taxonomy_gaps(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=100, ge=1, le=500),
    status_filter: Literal["open", "resolved", "rejected"] | None = Query(
        default=None,
        alias="status",
    ),
    session: AsyncSession = Depends(get_session),
) -> TaxonomyGapListResponse:
    """
    List and summarize taxonomy-gap records for analyst triage.
    """
    since = datetime.now(tz=UTC) - timedelta(days=days)
    filters = [TaxonomyGap.observed_at >= since]
    normalized_status_filter = status_filter if isinstance(status_filter, str) else None
    if normalized_status_filter is not None:
        filters.append(TaxonomyGap.status == TaxonomyGapStatus(normalized_status_filter))

    records_query = select(TaxonomyGap).order_by(TaxonomyGap.observed_at.desc()).limit(limit)
    for condition in filters:
        records_query = records_query.where(condition)
    records = list((await session.scalars(records_query)).all())

    grouped_counts_query = select(
        TaxonomyGap.status,
        TaxonomyGap.reason,
        func.count(TaxonomyGap.id),
    ).group_by(TaxonomyGap.status, TaxonomyGap.reason)
    for condition in filters:
        grouped_counts_query = grouped_counts_query.where(condition)
    grouped_counts_rows = (await session.execute(grouped_counts_query)).all()

    status_counts = {"open": 0, "resolved": 0, "rejected": 0}
    reason_counts = {"unknown_trend_id": 0, "unknown_signal_type": 0}
    total_count = 0
    for row_status, row_reason, row_count in grouped_counts_rows:
        status_key = str(row_status)
        reason_key = str(row_reason)
        count_value = int(row_count)
        total_count += count_value
        if status_key in status_counts:
            status_counts[status_key] += count_value
        if reason_key in reason_counts:
            reason_counts[reason_key] += count_value

    top_unknown_query = (
        select(
            TaxonomyGap.trend_id,
            TaxonomyGap.signal_type,
            func.count(TaxonomyGap.id).label("gap_count"),
        )
        .where(TaxonomyGap.reason == TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE)
        .group_by(TaxonomyGap.trend_id, TaxonomyGap.signal_type)
        .order_by(func.count(TaxonomyGap.id).desc(), TaxonomyGap.trend_id, TaxonomyGap.signal_type)
        .limit(20)
    )
    for condition in filters:
        top_unknown_query = top_unknown_query.where(condition)
    top_unknown_rows = (await session.execute(top_unknown_query)).all()

    return TaxonomyGapListResponse(
        total_count=total_count,
        open_count=status_counts["open"],
        resolved_count=status_counts["resolved"],
        rejected_count=status_counts["rejected"],
        unknown_trend_count=reason_counts["unknown_trend_id"],
        unknown_signal_count=reason_counts["unknown_signal_type"],
        top_unknown_signal_keys_by_trend=[
            TaxonomyGapSummaryRow(
                trend_id=str(trend_id),
                signal_type=str(signal_type),
                count=int(count),
            )
            for trend_id, signal_type, count in top_unknown_rows
        ],
        items=[to_taxonomy_gap_response(record) for record in records],
    )


@router.patch(
    "/taxonomy-gaps/{gap_id}",
    response_model=TaxonomyGapResponse,
    dependencies=[Depends(require_privileged_access("feedback.taxonomy_gap_update"))],
)
async def update_taxonomy_gap(
    gap_id: UUID,
    payload: TaxonomyGapUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> TaxonomyGapResponse:
    """
    Update taxonomy-gap triage status and optional resolution metadata.
    """
    gap = await session.get(TaxonomyGap, gap_id)
    if gap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Taxonomy gap '{gap_id}' not found",
        )

    next_status = TaxonomyGapStatus(payload.status)
    gap.status = next_status
    if next_status == TaxonomyGapStatus.OPEN:
        gap.resolution_notes = None
        gap.resolved_by = None
        gap.resolved_at = None
    else:
        gap.resolution_notes = payload.resolution_notes
        gap.resolved_by = payload.resolved_by
        gap.resolved_at = datetime.now(tz=UTC)

    await session.flush()
    return to_taxonomy_gap_response(gap)


async def _apply_event_feedback_restatements(
    *,
    session: AsyncSession,
    feedback: HumanFeedback,
    evidences: list[TrendEvidence],
    action: str,
    notes: str | None,
    invalidate_evidence: bool,
    target_by_evidence_id: dict[UUID, EventRestatementTarget] | None = None,
) -> float:
    trend_engine = TrendEngine(session=session)
    trend_by_id = await _trend_map(
        session=session,
        trend_ids={evidence.trend_id for evidence in evidences},
    )
    prior_compensation_by_evidence_id = await load_prior_compensation_by_evidence_id(
        session=session,
        evidences=evidences,
    )
    recorded_at = datetime.now(tz=UTC)
    total_compensation_delta = 0.0
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
            try:
                previous_log_odds, new_log_odds = await trend_engine.apply_log_odds_delta(
                    trend_id=evidence.trend_id,
                    trend_name=None,
                    delta=compensation_delta,
                    reason=(
                        "event_invalidation" if invalidate_evidence else "event_partial_restatement"
                    ),
                    fallback_current_log_odds=None,
                )
            except ValueError:
                continue
            trend_adjustments[str(evidence.trend_id)] = {
                "previous_log_odds": previous_log_odds,
                "new_log_odds": new_log_odds,
                "delta_applied": compensation_delta,
            }
            total_compensation_delta += compensation_delta
            continue
        previous_log_odds = float(trend.current_log_odds)
        await apply_compensating_restatement(
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

    feedback.corrected_value = _event_feedback_corrected_value(
        action=action,
        event_id=feedback.target_id,
        at=recorded_at,
        evidences=evidences,
        total_compensation_delta=total_compensation_delta,
        trend_adjustments=trend_adjustments,
    )
    return total_compensation_delta


@router.post(
    "/events/{event_id}/feedback",
    response_model=FeedbackResponse,
    dependencies=[Depends(require_privileged_access("feedback.event_feedback"))],
)
async def create_event_feedback(
    event_id: UUID,
    payload: EventFeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """
    Record event-level feedback (pin, mark_noise, invalidate, restate).

    `invalidate` fully compensates active evidence and invalidates it.
    `restate` keeps evidence visible but appends signed compensating deltas.
    """
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )

    original_value: dict[str, Any] | None = None
    corrected_value: dict[str, Any] | None = None
    evidences: list[TrendEvidence] = []
    restatement_targets: dict[UUID, EventRestatementTarget] | None = None

    if payload.action == "mark_noise":
        original_value = {"lifecycle_status": event.lifecycle_status}
        event.lifecycle_status = EventLifecycle.ARCHIVED.value
        corrected_value = {"lifecycle_status": event.lifecycle_status}
    elif payload.action in {"invalidate", "restate"}:
        evidences = await _active_event_evidence(session=session, event_id=event_id)
        if payload.action == "restate":
            evidences, restatement_targets = validate_restatement_targets(
                evidences=evidences,
                targets=payload.restatement_targets,
            )

        original_value = _event_feedback_original_value(evidences)
        corrected_value = _event_feedback_corrected_value(
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

    if payload.action in {"invalidate", "restate"} and evidences:
        await _apply_event_feedback_restatements(
            session=session,
            feedback=feedback,
            evidences=evidences,
            action=payload.action,
            notes=payload.notes,
            invalidate_evidence=payload.action == "invalidate",
            target_by_evidence_id=restatement_targets,
        )
    else:
        feedback.corrected_value = corrected_value

    return to_feedback_response(feedback)


def _claim_graph_contradiction_links(event: Event) -> int:
    if not isinstance(event.extracted_claims, dict):
        return 0
    claim_graph = event.extracted_claims.get("claim_graph")
    if not isinstance(claim_graph, dict):
        return 0
    links = claim_graph.get("links")
    if not isinstance(links, list):
        return 0
    return sum(
        1
        for link in links
        if isinstance(link, dict) and str(link.get("relation", "")).strip().lower() == "contradict"
    )


def _uncertainty_score(evidence_rows: list[tuple[Any, ...]]) -> float:
    confidences = [float(row[5]) for row in evidence_rows if row[5] is not None]
    corroborations = [float(row[6]) for row in evidence_rows if row[6] is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    avg_corroboration = sum(corroborations) / len(corroborations) if corroborations else 0.33

    confidence_uncertainty = max(0.0, 1.0 - avg_confidence)
    corroboration_uncertainty = max(0.0, 1.0 - min(1.0, avg_corroboration))
    uncertainty = 0.7 * confidence_uncertainty + 0.3 * corroboration_uncertainty
    return max(0.1, min(1.0, uncertainty))


def _contradiction_risk(event: Event) -> float:
    link_count = _claim_graph_contradiction_links(event)
    risk = 1.0 + min(1.5, 0.25 * link_count)
    if event.has_contradictions:
        risk += 0.5
    return min(3.0, risk)


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def list_review_queue(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=50, ge=1, le=200),
    trend_id: UUID | None = Query(default=None),
    unreviewed_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewQueueItem]:
    """
    Return ranked analyst review candidates.

    Ranking formula:
    `uncertainty_score x projected_delta x contradiction_risk`
    """
    days_value = days if isinstance(days, int) else 7
    limit_value = limit if isinstance(limit, int) else 50
    unreviewed_only_value = unreviewed_only if isinstance(unreviewed_only, bool) else True

    since = datetime.now(tz=UTC) - timedelta(days=days_value)
    candidate_limit = min(1000, max(limit_value * 4, limit_value))

    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.last_mention_at >= since)
                .order_by(Event.last_mention_at.desc())
                .limit(candidate_limit)
            )
        ).all()
    )
    if not events:
        return []

    event_ids = [event.id for event in events if event.id is not None]
    if not event_ids:
        return []

    evidence_query = (
        select(
            TrendEvidence.event_id,
            TrendEvidence.trend_id,
            Trend.name,
            TrendEvidence.signal_type,
            TrendEvidence.delta_log_odds,
            TrendEvidence.confidence_score,
            TrendEvidence.corroboration_factor,
        )
        .join(Trend, Trend.id == TrendEvidence.trend_id)
        .where(TrendEvidence.event_id.in_(tuple(event_ids)))
        .where(TrendEvidence.is_invalidated.is_(False))
    )
    if trend_id is not None:
        evidence_query = evidence_query.where(TrendEvidence.trend_id == trend_id)
    evidence_rows = (await session.execute(evidence_query)).all()

    feedback_rows = (
        await session.execute(
            select(HumanFeedback.target_id, HumanFeedback.action)
            .where(HumanFeedback.target_type == "event")
            .where(HumanFeedback.target_id.in_(tuple(event_ids)))
            .order_by(HumanFeedback.created_at.desc())
        )
    ).all()

    evidence_by_event: dict[UUID, list[tuple[Any, ...]]] = defaultdict(list)
    for row in evidence_rows:
        event_id_value = row[0]
        if isinstance(event_id_value, UUID):
            evidence_by_event[event_id_value].append(tuple(row))

    feedback_by_event: dict[UUID, list[str]] = defaultdict(list)
    for target_id, action in feedback_rows:
        if isinstance(target_id, UUID) and isinstance(action, str):
            feedback_by_event[target_id].append(action)

    queue_items: list[ReviewQueueItem] = []
    for event in events:
        if event.id is None:
            continue
        event_evidence = evidence_by_event.get(event.id, [])
        if not event_evidence:
            continue

        feedback_actions = feedback_by_event.get(event.id, [])
        if unreviewed_only_value and feedback_actions:
            continue

        projected_delta = sum(abs(float(row[4])) for row in event_evidence)
        if projected_delta <= 0:
            continue

        uncertainty_score = _uncertainty_score(event_evidence)
        contradiction_risk = _contradiction_risk(event)
        ranking_score = uncertainty_score * projected_delta * contradiction_risk
        last_mention_at = event.last_mention_at or event.created_at or datetime.now(tz=UTC)

        impacts = sorted(
            (
                ReviewQueueTrendImpact(
                    trend_id=row[1],
                    trend_name=str(row[2]),
                    signal_type=str(row[3]),
                    delta_log_odds=float(row[4]),
                    confidence_score=float(row[5]) if row[5] is not None else None,
                )
                for row in event_evidence
            ),
            key=lambda impact: abs(impact.delta_log_odds),
            reverse=True,
        )

        queue_items.append(
            ReviewQueueItem(
                event_id=event.id,
                summary=event.canonical_summary,
                lifecycle_status=event.lifecycle_status,
                last_mention_at=last_mention_at,
                source_count=event.source_count,
                unique_source_count=event.unique_source_count,
                has_contradictions=bool(event.has_contradictions),
                contradiction_notes=event.contradiction_notes,
                evidence_count=len(event_evidence),
                projected_delta=projected_delta,
                uncertainty_score=uncertainty_score,
                contradiction_risk=contradiction_risk,
                ranking_score=ranking_score,
                feedback_count=len(feedback_actions),
                feedback_actions=feedback_actions,
                requires_human_verification=len(feedback_actions) == 0,
                trend_impacts=impacts[:3],
            )
        )

    queue_items.sort(
        key=lambda item: (
            -item.ranking_score,
            -item.projected_delta,
            -item.last_mention_at.timestamp(),
            str(item.event_id),
        )
    )
    return queue_items[:limit_value]


@router.post(
    "/trends/{trend_id}/override",
    response_model=FeedbackResponse,
    dependencies=[Depends(require_privileged_access("feedback.trend_override"))],
)
async def create_trend_override(
    trend_id: UUID,
    payload: TrendOverrideRequest,
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """
    Apply a manual trend delta override and record feedback audit trail.
    """
    trend = await session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trend '{trend_id}' not found",
        )

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
    await apply_compensating_restatement(
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
    feedback.corrected_value = corrected_value
    return to_feedback_response(feedback)
