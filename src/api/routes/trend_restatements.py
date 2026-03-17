"""Trend restatement lineage and projection verification routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.trend_restatement import (
    HISTORICAL_ARTIFACT_POLICY,
    build_trend_projection_check,
)
from src.storage.database import get_session
from src.storage.models import Trend, TrendEvidence
from src.storage.restatement_models import TrendRestatement

router = APIRouter()


class TrendRestatementResponse(BaseModel):
    id: UUID
    trend_id: UUID
    event_id: UUID | None
    event_claim_id: UUID | None
    trend_evidence_id: UUID | None
    feedback_id: UUID | None
    restatement_kind: str
    source: str
    signal_type: str | None
    original_evidence_delta_log_odds: float | None
    compensation_delta_log_odds: float
    net_evidence_delta_log_odds: float | None
    notes: str | None
    details: dict[str, object] | None
    historical_artifact_policy: str
    recorded_at: datetime


class TrendProjectionResponse(BaseModel):
    as_of: datetime
    stored_log_odds: float
    projected_log_odds: float
    drift_log_odds: float
    matches_projection: bool
    evidence_count: int
    restatement_count: int
    entry_count: int
    historical_artifact_policy: str


async def _get_trend_or_404(session: AsyncSession, trend_id: UUID) -> Trend:
    trend = await session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trend '{trend_id}' not found",
        )
    return trend


@router.get("/{trend_id}/restatements", response_model=list[TrendRestatementResponse])
async def list_trend_restatements(
    trend_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[TrendRestatementResponse]:
    """List append-only restatement rows for one trend, newest first."""
    await _get_trend_or_404(session, trend_id)

    rows = list(
        (
            await session.scalars(
                select(TrendRestatement)
                .where(TrendRestatement.trend_id == trend_id)
                .order_by(TrendRestatement.recorded_at.asc(), TrendRestatement.id.asc())
            )
        ).all()
    )
    evidence_ids = tuple(row.trend_evidence_id for row in rows if row.trend_evidence_id is not None)
    evidence_by_id = {}
    if evidence_ids:
        evidence_rows = list(
            (
                await session.scalars(
                    select(TrendEvidence).where(TrendEvidence.id.in_(evidence_ids))
                )
            ).all()
        )
        evidence_by_id = {row.id: row for row in evidence_rows if row.id is not None}

    cumulative_by_evidence: dict[UUID, float] = {}
    responses: list[TrendRestatementResponse] = []
    for row in rows:
        net_delta: float | None = None
        signal_type: str | None = None
        if row.trend_evidence_id is not None:
            evidence = evidence_by_id.get(row.trend_evidence_id)
            signal_type = evidence.signal_type if evidence is not None else None
            cumulative = cumulative_by_evidence.get(row.trend_evidence_id, 0.0) + float(
                row.compensation_delta_log_odds
            )
            cumulative_by_evidence[row.trend_evidence_id] = cumulative
            if row.original_evidence_delta_log_odds is not None:
                net_delta = float(row.original_evidence_delta_log_odds) + cumulative

        responses.append(
            TrendRestatementResponse(
                id=row.id,
                trend_id=row.trend_id,
                event_id=row.event_id,
                event_claim_id=row.event_claim_id,
                trend_evidence_id=row.trend_evidence_id,
                feedback_id=row.feedback_id,
                restatement_kind=row.restatement_kind,
                source=row.source,
                signal_type=signal_type,
                original_evidence_delta_log_odds=(
                    float(row.original_evidence_delta_log_odds)
                    if row.original_evidence_delta_log_odds is not None
                    else None
                ),
                compensation_delta_log_odds=float(row.compensation_delta_log_odds),
                net_evidence_delta_log_odds=net_delta,
                notes=row.notes,
                details=row.details if isinstance(row.details, dict) else None,
                historical_artifact_policy=HISTORICAL_ARTIFACT_POLICY,
                recorded_at=row.recorded_at,
            )
        )

    responses = responses[-limit:]
    responses.reverse()
    return responses


@router.get("/{trend_id}/projection", response_model=TrendProjectionResponse)
async def get_trend_projection(
    trend_id: UUID,
    as_of: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> TrendProjectionResponse:
    """Verify or rebuild one trend projection from chronological evidence and restatements."""
    trend = await _get_trend_or_404(session, trend_id)
    projection = await build_trend_projection_check(
        session=session,
        trend=trend,
        as_of=as_of if as_of is not None else trend.updated_at or datetime.now(tz=UTC),
    )
    return TrendProjectionResponse(
        as_of=projection.as_of,
        stored_log_odds=projection.stored_log_odds,
        projected_log_odds=projection.projected_log_odds,
        drift_log_odds=projection.drift_log_odds,
        matches_projection=projection.matches_projection,
        evidence_count=projection.evidence_count,
        restatement_count=projection.restatement_count,
        entry_count=projection.entry_count,
        historical_artifact_policy=HISTORICAL_ARTIFACT_POLICY,
    )
