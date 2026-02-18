"""
Event clustering service for grouping similar raw items into events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import record_processing_event_suppression
from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.processing.event_lifecycle import EventLifecycleManager
from src.processing.vector_similarity import max_distance_for_similarity
from src.storage.models import Event, EventItem, HumanFeedback, RawItem, Source

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ClusterResult:
    """Result of clustering one raw item."""

    item_id: UUID
    event_id: UUID
    created: bool
    merged: bool
    similarity: float | None = None


class EventClusterer:
    """Cluster raw items into events using embedding similarity and time windows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lifecycle_manager = EventLifecycleManager(session)

    async def cluster_item(self, item: RawItem) -> ClusterResult:
        """Cluster a single raw item into an existing or new event."""
        item_id = item.id
        if item_id is None:
            msg = "RawItem must have an id before clustering"
            raise ValueError(msg)

        already_event_id = await self._find_existing_event_id_for_item(item_id)
        if already_event_id is not None:
            return ClusterResult(
                item_id=item_id,
                event_id=already_event_id,
                created=False,
                merged=True,
            )

        if item.embedding is None:
            event = await self._create_event(item)
            await self._add_event_link(event.id, item_id)
            return ClusterResult(item_id=item_id, event_id=event.id, created=True, merged=False)

        item_embedding_model = item.embedding_model.strip() if item.embedding_model else None
        if not item_embedding_model:
            event = await self._create_event(item)
            await self._add_event_link(event.id, item_id)
            return ClusterResult(item_id=item_id, event_id=event.id, created=True, merged=False)

        matched = await self._find_matching_event(
            item.embedding,
            item_embedding_model,
            self._item_timestamp(item),
        )
        if matched is None:
            event = await self._create_event(item)
            await self._add_event_link(event.id, item_id)
            return ClusterResult(item_id=item_id, event_id=event.id, created=True, merged=False)

        event, similarity = matched
        suppression_action = await self._event_suppression_action(event_id=event.id)
        if suppression_action is not None:
            record_processing_event_suppression(
                action=suppression_action,
                stage="clusterer_pre_merge",
            )
            logger.info(
                "Skipping suppressed event before merge",
                event_id=str(event.id),
                item_id=str(item_id),
                action=suppression_action,
            )
            return ClusterResult(
                item_id=item_id,
                event_id=event.id,
                created=False,
                merged=False,
                similarity=similarity,
            )
        link_added = await self._add_event_link(event.id, item_id)
        if not link_added:
            resolved_event_id = await self._find_existing_event_id_for_item(item_id)
            if resolved_event_id is not None and resolved_event_id != event.id:
                logger.info(
                    "Item already linked to a different event; using existing linkage",
                    item_id=str(item_id),
                    requested_event_id=str(event.id),
                    existing_event_id=str(resolved_event_id),
                )
                return ClusterResult(
                    item_id=item_id,
                    event_id=resolved_event_id,
                    created=False,
                    merged=True,
                    similarity=similarity,
                )
            logger.info(
                "Skipping merge metadata update because item was already linked",
                event_id=str(event.id),
                item_id=str(item_id),
            )
            return ClusterResult(
                item_id=item_id,
                event_id=event.id,
                created=False,
                merged=True,
                similarity=similarity,
            )
        await self._merge_into_event(event, item)
        return ClusterResult(
            item_id=item_id,
            event_id=event.id,
            created=False,
            merged=True,
            similarity=similarity,
        )

    async def cluster_unlinked_items(self, limit: int = 100) -> list[ClusterResult]:
        """Cluster raw items not yet attached to an event."""
        query = (
            select(RawItem)
            .outerjoin(EventItem, EventItem.item_id == RawItem.id)
            .where(EventItem.item_id.is_(None))
            .order_by(RawItem.fetched_at.asc())
            .limit(limit)
        )
        items = (await self.session.scalars(query)).all()
        results = [await self.cluster_item(item) for item in items]
        await self.session.flush()
        return results

    async def _create_event(self, item: RawItem) -> Event:
        timestamp = self._item_timestamp(item)
        event = Event(
            canonical_summary=self._build_canonical_summary(item),
            embedding=item.embedding,
            embedding_model=item.embedding_model,
            embedding_generated_at=item.embedding_generated_at,
            source_count=1,
            unique_source_count=1,
            first_seen_at=timestamp,
            last_mention_at=timestamp,
            primary_item_id=item.id,
        )
        if event.id is None:
            event.id = uuid4()
        self.session.add(event)
        await self.session.flush()
        return event

    async def _merge_into_event(self, event: Event, item: RawItem) -> None:
        event.source_count += 1
        event.canonical_summary = self._build_canonical_summary(item)
        mention_time = self._item_timestamp(item)
        event.last_mention_at = mention_time
        if event.embedding is None and item.embedding is not None:
            event.embedding = item.embedding
            event.embedding_model = item.embedding_model
            event.embedding_generated_at = item.embedding_generated_at

        await self._update_primary_item(event, item.id)
        event.unique_source_count = await self._count_unique_sources(event.id, item.source_id)
        self.lifecycle_manager.on_event_mention(event, mentioned_at=mention_time)
        await self.session.flush()

    async def _find_matching_event(
        self,
        item_embedding: list[float],
        embedding_model: str,
        reference_time: datetime,
    ) -> tuple[Event, float] | None:
        window_start = reference_time - timedelta(hours=settings.CLUSTER_TIME_WINDOW_HOURS)
        max_distance = max_distance_for_similarity(settings.CLUSTER_SIMILARITY_THRESHOLD)
        distance_expr = Event.embedding.cosine_distance(item_embedding)

        query = (
            select(Event, distance_expr.label("distance"))
            .where(Event.last_mention_at >= window_start)
            .where(Event.embedding.is_not(None))
            .where(Event.embedding_model == embedding_model)
            .where(distance_expr <= max_distance)
            .order_by(distance_expr.asc())
            .limit(1)
        )
        row = (await self.session.execute(query)).first()
        if row is None:
            return None

        event = cast("Event", row[0])
        distance = float(row[1])
        similarity = 1.0 - distance
        return (event, similarity)

    async def _find_existing_event_id_for_item(self, item_id: UUID) -> UUID | None:
        query = select(EventItem.event_id).where(EventItem.item_id == item_id).limit(1)
        event_id: UUID | None = await self.session.scalar(query)
        return event_id

    async def _event_suppression_action(self, *, event_id: UUID) -> str | None:
        query = (
            select(HumanFeedback.action)
            .where(HumanFeedback.target_type == "event")
            .where(HumanFeedback.target_id == event_id)
            .where(HumanFeedback.action.in_(("mark_noise", "invalidate")))
            .order_by(HumanFeedback.created_at.desc())
            .limit(1)
        )
        action: str | None = await self.session.scalar(query)
        if not isinstance(action, str):
            return None
        normalized_action = action.strip()
        if normalized_action not in {"mark_noise", "invalidate"}:
            return None
        return normalized_action

    async def _add_event_link(self, event_id: UUID, item_id: UUID) -> bool:
        link = EventItem(event_id=event_id, item_id=item_id)
        try:
            async with self.session.begin_nested():
                self.session.add(link)
                await self.session.flush()
            return True
        except IntegrityError:
            return False

    async def _count_unique_sources(self, event_id: UUID, fallback_source_id: UUID) -> int:
        count_query = (
            select(func.count(func.distinct(RawItem.source_id)))
            .join(EventItem, EventItem.item_id == RawItem.id)
            .where(EventItem.event_id == event_id)
        )
        count = await self.session.scalar(count_query)
        if count is None or count == 0:
            return 1 if fallback_source_id else 0
        return int(count)

    async def _update_primary_item(self, event: Event, candidate_item_id: UUID) -> None:
        current_primary_item_id = event.primary_item_id
        if current_primary_item_id is None:
            event.primary_item_id = candidate_item_id
            return

        candidate_credibility = await self._source_credibility_for_item(candidate_item_id)
        current_credibility = await self._source_credibility_for_item(current_primary_item_id)

        if candidate_credibility > current_credibility:
            event.primary_item_id = candidate_item_id

    async def _source_credibility_for_item(self, item_id: UUID) -> float:
        query = (
            select(
                (
                    func.coalesce(Source.credibility_score, DEFAULT_SOURCE_CREDIBILITY)
                    * source_multiplier_expression(
                        source_tier_col=Source.source_tier,
                        reporting_type_col=Source.reporting_type,
                    )
                ).label("effective_credibility")
            )
            .join(RawItem, RawItem.source_id == Source.id)
            .where(RawItem.id == item_id)
            .limit(1)
        )
        credibility = await self.session.scalar(query)
        try:
            return float(credibility) if credibility is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _build_canonical_summary(item: RawItem) -> str:
        if item.title and item.title.strip():
            return item.title.strip()
        content = item.raw_content.strip()
        return content[:400] if len(content) > 400 else content

    @staticmethod
    def _item_timestamp(item: RawItem) -> datetime:
        if item.published_at is not None:
            return item.published_at
        if item.fetched_at is not None:
            return item.fetched_at
        return datetime.now(tz=UTC)
