"""Feedback API endpoints for human corrections and annotations."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_privileged_access
from src.api.routes._feedback_write_mutations import (
    apply_event_feedback_mutation,
    apply_trend_override_mutation,
)
from src.api.routes._privileged_write_contract import (
    event_revision_token,
    normalize_request_intent,
    privileged_write,
    record_privileged_write_rejection,
    request_dependency,
    taxonomy_gap_revision_token,
    trend_revision_token,
)
from src.api.routes.feedback_event_helpers import build_review_queue_item
from src.api.routes.feedback_models import (
    EventFeedbackRequest,
    FeedbackResponse,
    NoveltyQueueItem,
    ReviewQueueItem,
    TaxonomyGapListResponse,
    TaxonomyGapResponse,
    TaxonomyGapSummaryRow,
    TaxonomyGapUpdateRequest,
    TrendOverrideRequest,
    to_feedback_response,
    to_novelty_queue_item,
    to_taxonomy_gap_response,
)
from src.storage.database import get_session
from src.storage.models import (
    Event,
    TaxonomyGap,
    TaxonomyGapReason,
    TaxonomyGapStatus,
    Trend,
    TrendEvidence,
)
from src.storage.novelty_models import NoveltyCandidate
from src.storage.restatement_models import HumanFeedback

router = APIRouter()


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
        items=[
            to_taxonomy_gap_response(
                record,
                revision_token=taxonomy_gap_revision_token(record),
            )
            for record in records
        ],
    )


@router.patch(
    "/taxonomy-gaps/{gap_id}",
    response_model=TaxonomyGapResponse,
    dependencies=[Depends(require_privileged_access("feedback.taxonomy_gap_update"))],
)
async def update_taxonomy_gap(
    gap_id: UUID,
    payload: TaxonomyGapUpdateRequest,
    request: Request = Depends(request_dependency),
    session: AsyncSession = Depends(get_session),
) -> TaxonomyGapResponse:
    """
    Update taxonomy-gap triage status and optional resolution metadata.
    """
    gap = await session.get(TaxonomyGap, gap_id)
    if gap is None:
        await record_privileged_write_rejection(
            route_session=session,
            request=request,
            action="feedback.taxonomy_gap_update",
            target_type="taxonomy_gap",
            target_identifier=str(gap_id),
            intent=normalize_request_intent(payload.model_dump(mode="json", exclude_none=True)),
            outcome="not_found",
            detail=f"Taxonomy gap '{gap_id}' not found",
            operator_identity=payload.resolved_by,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Taxonomy gap '{gap_id}' not found",
        )
    current_revision_token = taxonomy_gap_revision_token(gap)
    intent = normalize_request_intent(payload.model_dump(mode="json", exclude_none=True))
    async with privileged_write(
        route_session=session,
        request=request,
        action="feedback.taxonomy_gap_update",
        target_type="taxonomy_gap",
        target_identifier=str(gap_id),
        intent=intent,
        operator_identity=payload.resolved_by,
        require_revision=True,
        observed_revision_token=current_revision_token,
    ) as audit_guard:
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
        response = to_taxonomy_gap_response(
            gap,
            revision_token=taxonomy_gap_revision_token(gap),
        )
        await audit_guard.succeed(
            observed_revision_token=response.revision_token,
            result_links={"taxonomy_gap_id": str(gap_id), "status": response.status},
        )
        return response


@router.post(
    "/events/{event_id}/feedback",
    response_model=FeedbackResponse,
    dependencies=[Depends(require_privileged_access("feedback.event_feedback"))],
)
async def create_event_feedback(
    event_id: UUID,
    payload: EventFeedbackRequest,
    request: Request = Depends(request_dependency),
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """Record event feedback; `invalidate` reverses evidence and `restate` adds compensation."""
    event = await session.get(Event, event_id)
    if event is None:
        await record_privileged_write_rejection(
            route_session=session,
            request=request,
            action="feedback.event_feedback",
            target_type="event",
            target_identifier=str(event_id),
            intent=normalize_request_intent(payload.model_dump(mode="json", exclude_none=True)),
            outcome="not_found",
            detail=f"Event '{event_id}' not found",
            operator_identity=payload.created_by,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )
    current_revision_token = event_revision_token(event)
    intent = normalize_request_intent(payload.model_dump(mode="json", exclude_none=True))
    async with privileged_write(
        route_session=session,
        request=request,
        action="feedback.event_feedback",
        target_type="event",
        target_identifier=str(event_id),
        intent=intent,
        operator_identity=payload.created_by,
        require_revision=True,
        observed_revision_token=current_revision_token,
    ) as audit_guard:
        result = await apply_event_feedback_mutation(
            session=session,
            event_id=event_id,
            event=event,
            payload=payload,
        )
        response = to_feedback_response(
            result.feedback,
            target_revision_token=result.target_revision_token,
        )
        await audit_guard.succeed(
            observed_revision_token=result.target_revision_token,
            result_links=result.result_links,
        )
        return response


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

        if sum(abs(float(row[4])) for row in event_evidence) <= 0:
            continue
        queue_items.append(
            build_review_queue_item(
                event=event,
                event_evidence=event_evidence,
                feedback_actions=feedback_actions,
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


@router.get("/novelty-queue", response_model=list[NoveltyQueueItem])
async def list_novelty_queue(
    days: int = Query(default=14, ge=1, le=30),
    limit: int = Query(default=50, ge=1, le=200),
    candidate_kind: Literal["near_threshold_item", "event_gap"] | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[NoveltyQueueItem]:
    """Return ranked novelty candidates outside the active trend lane."""

    since = datetime.now(tz=UTC) - timedelta(days=days if isinstance(days, int) else 14)
    limit_value = limit if isinstance(limit, int) else 50

    query = (
        select(NoveltyCandidate)
        .where(NoveltyCandidate.last_seen_at >= since)
        .order_by(
            NoveltyCandidate.ranking_score.desc(),
            NoveltyCandidate.last_seen_at.desc(),
            NoveltyCandidate.created_at.desc(),
        )
        .limit(limit_value)
    )
    if candidate_kind is not None:
        query = query.where(NoveltyCandidate.candidate_kind == candidate_kind)

    candidates = list((await session.scalars(query)).all())
    return [to_novelty_queue_item(candidate) for candidate in candidates]


@router.post(
    "/trends/{trend_id}/override",
    response_model=FeedbackResponse,
    dependencies=[Depends(require_privileged_access("feedback.trend_override"))],
)
async def create_trend_override(
    trend_id: UUID,
    payload: TrendOverrideRequest,
    request: Request = Depends(request_dependency),
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """
    Apply a manual trend delta override and record feedback audit trail.
    """
    trend = await session.get(Trend, trend_id)
    if trend is None:
        await record_privileged_write_rejection(
            route_session=session,
            request=request,
            action="feedback.trend_override",
            target_type="trend",
            target_identifier=str(trend_id),
            intent=normalize_request_intent(payload.model_dump(mode="json", exclude_none=True)),
            outcome="not_found",
            detail=f"Trend '{trend_id}' not found",
            operator_identity=payload.created_by,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trend '{trend_id}' not found",
        )
    current_revision_token = trend_revision_token(trend)
    intent = normalize_request_intent(payload.model_dump(mode="json", exclude_none=True))
    async with privileged_write(
        route_session=session,
        request=request,
        action="feedback.trend_override",
        target_type="trend",
        target_identifier=str(trend_id),
        intent=intent,
        operator_identity=payload.created_by,
        require_revision=True,
        observed_revision_token=current_revision_token,
    ) as audit_guard:
        result = await apply_trend_override_mutation(
            session=session,
            trend_id=trend_id,
            trend=trend,
            payload=payload,
        )
        response = to_feedback_response(
            result.feedback,
            target_revision_token=result.target_revision_token,
        )
        await audit_guard.succeed(
            observed_revision_token=result.target_revision_token,
            result_links=result.result_links,
        )
        return response
