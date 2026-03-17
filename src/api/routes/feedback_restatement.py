"""Restatement-target validation helpers for feedback routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from src.core.trend_restatement import (
    remaining_evidence_delta,
    restatement_compensation_totals_by_evidence_id,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.api.routes.feedback_models import EventRestatementTarget
    from src.storage.models import TrendEvidence


def validate_restatement_targets(
    *,
    evidences: list[TrendEvidence],
    targets: list[EventRestatementTarget] | None,
) -> tuple[list[TrendEvidence], dict[UUID, EventRestatementTarget]]:
    """Return filtered evidence and unique targets or raise HTTP 400."""

    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="restate requires at least one restatement_targets entry",
        )

    target_by_evidence_id: dict[UUID, EventRestatementTarget] = {}
    for target in targets:
        if target.evidence_id in target_by_evidence_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="restatement_targets must not contain duplicate evidence_id values",
            )
        target_by_evidence_id[target.evidence_id] = target

    evidence_ids = {evidence.id for evidence in evidences if evidence.id is not None}
    if any(target_id not in evidence_ids for target_id in target_by_evidence_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="restatement_targets must reference active evidence for the event",
        )

    filtered_evidence = [
        evidence
        for evidence in evidences
        if evidence.id is not None and evidence.id in target_by_evidence_id
    ]
    return (filtered_evidence, target_by_evidence_id)


def invalidation_compensation_delta(
    *,
    evidence: TrendEvidence,
    prior_compensation_by_evidence_id: dict[UUID, float],
) -> float:
    """Return the remaining net evidence contribution that invalidation must reverse."""

    prior_compensation_delta = (
        prior_compensation_by_evidence_id.get(evidence.id, 0.0) if evidence.id is not None else 0.0
    )
    return -remaining_evidence_delta(
        evidence=evidence,
        prior_compensation_delta=prior_compensation_delta,
    )


async def load_prior_compensation_by_evidence_id(
    *,
    session: AsyncSession,
    evidences: list[TrendEvidence],
) -> dict[UUID, float]:
    """Load cumulative compensation totals for active evidence rows."""

    evidence_ids = tuple(evidence.id for evidence in evidences if evidence.id is not None)
    return await restatement_compensation_totals_by_evidence_id(
        session=session,
        evidence_ids=evidence_ids,
    )
