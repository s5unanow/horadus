"""Atomic evidence-invalidation claim owned by event lineage repair."""

from __future__ import annotations

from datetime import datetime
from inspect import isawaitable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import TrendEvidence


async def claim_evidence_invalidation(
    session: AsyncSession,
    evidence: TrendEvidence,
    invalidated_at: datetime,
) -> bool:
    """Claim one active evidence row before lineage repair compensates it."""
    stmt = (
        update(TrendEvidence)
        .where(TrendEvidence.id == evidence.id)
        .where(TrendEvidence.is_invalidated.is_(False))
        .values(is_invalidated=True, invalidated_at=invalidated_at)
        .returning(TrendEvidence.id)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    claimed_id = result.scalar_one_or_none()
    if isawaitable(claimed_id):
        claimed_id = await claimed_id
    if claimed_id is None:
        return False
    evidence.is_invalidated = True
    evidence.invalidated_at = invalidated_at
    return True


async def claim_evidence_invalidations(
    session: AsyncSession,
    evidences: list[TrendEvidence],
    invalidated_at: datetime,
) -> list[TrendEvidence]:
    """Return only evidence rows this lineage-repair transaction claimed."""
    claimed: list[TrendEvidence] = []
    for evidence in evidences:
        if await claim_evidence_invalidation(session, evidence, invalidated_at):
            claimed.append(evidence)
    return claimed
