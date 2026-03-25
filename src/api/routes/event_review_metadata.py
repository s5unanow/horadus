"""Shared event review metadata loaders for queue and event read surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import TaxonomyGap, TaxonomyGapStatus
from src.storage.restatement_models import EventAdjudication


@dataclass(slots=True)
class EventReviewMetadata:
    """Derived operator-review state for one event."""

    review_status: str = "pending"
    open_taxonomy_gap_count: int = 0
    latest_adjudication_outcome: str | None = None
    latest_adjudication_at: datetime | None = None
    adjudication_count: int = 0


async def load_event_review_metadata(
    *,
    session: AsyncSession,
    event_ids: list[UUID] | tuple[UUID, ...],
) -> dict[UUID, EventReviewMetadata]:
    """Load review-status and taxonomy-gap metadata for the requested events."""

    normalized_event_ids = tuple(dict.fromkeys(event_ids))
    if not normalized_event_ids:
        return {}

    metadata_by_event_id = {event_id: EventReviewMetadata() for event_id in normalized_event_ids}
    gap_rows = (
        await session.execute(
            select(TaxonomyGap.event_id, func.count(TaxonomyGap.id))
            .where(TaxonomyGap.event_id.in_(normalized_event_ids))
            .where(TaxonomyGap.status == TaxonomyGapStatus.OPEN)
            .group_by(TaxonomyGap.event_id)
        )
    ).all()
    for event_id, gap_count in gap_rows:
        if event_id in metadata_by_event_id:
            metadata_by_event_id[event_id].open_taxonomy_gap_count = int(gap_count)

    adjudications = list(
        (
            await session.scalars(
                select(EventAdjudication)
                .where(EventAdjudication.event_id.in_(normalized_event_ids))
                .order_by(EventAdjudication.created_at.desc(), EventAdjudication.id.desc())
            )
        ).all()
    )
    for adjudication in adjudications:
        event_id = adjudication.event_id
        if event_id not in metadata_by_event_id:
            continue
        metadata = metadata_by_event_id[event_id]
        metadata.adjudication_count += 1
        if metadata.latest_adjudication_at is None:
            metadata.review_status = adjudication.review_status
            metadata.latest_adjudication_outcome = adjudication.outcome
            metadata.latest_adjudication_at = adjudication.created_at
    return metadata_by_event_id
