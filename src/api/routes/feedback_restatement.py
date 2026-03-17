"""Restatement-target validation helpers for feedback routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

if TYPE_CHECKING:
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
