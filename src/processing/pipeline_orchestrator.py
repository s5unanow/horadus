"""
Processing pipeline orchestration for pending raw items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.deduplication_service import DeduplicationService
from src.processing.embedding_service import EmbeddingService
from src.processing.event_clusterer import ClusterResult, EventClusterer
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event, ProcessingStatus, RawItem, Trend

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class PipelineUsage:
    """Usage and API call metrics across one pipeline run."""

    embedding_api_calls: int = 0
    tier1_prompt_tokens: int = 0
    tier1_completion_tokens: int = 0
    tier1_api_calls: int = 0
    tier2_prompt_tokens: int = 0
    tier2_completion_tokens: int = 0
    tier2_api_calls: int = 0


@dataclass(slots=True)
class PipelineItemResult:
    """Result of processing one raw item."""

    item_id: UUID
    final_status: ProcessingStatus
    event_id: UUID | None = None
    duplicate: bool = False
    embedded: bool = False
    event_created: bool = False
    event_merged: bool = False
    tier2_applied: bool = False
    error_message: str | None = None


@dataclass(slots=True)
class PipelineRunResult:
    """Summary metrics for one pipeline run."""

    scanned: int = 0
    processed: int = 0
    classified: int = 0
    noise: int = 0
    duplicates: int = 0
    errors: int = 0
    embedded: int = 0
    events_created: int = 0
    events_merged: int = 0
    results: list[PipelineItemResult] = field(default_factory=list)
    usage: PipelineUsage = field(default_factory=PipelineUsage)


@dataclass(slots=True)
class _ItemExecution:
    """Internal execution details for one processed item."""

    result: PipelineItemResult
    usage: PipelineUsage = field(default_factory=PipelineUsage)


class ProcessingPipeline:
    """Orchestrate deduplication, embedding, clustering, and LLM classification."""

    def __init__(
        self,
        session: AsyncSession,
        deduplication_service: DeduplicationService | None = None,
        embedding_service: EmbeddingService | None = None,
        event_clusterer: EventClusterer | None = None,
        tier1_classifier: Tier1Classifier | None = None,
        tier2_classifier: Tier2Classifier | None = None,
    ) -> None:
        self.session = session
        self.deduplication_service = deduplication_service or DeduplicationService(session=session)
        self.embedding_service = embedding_service or EmbeddingService(session=session)
        self.event_clusterer = event_clusterer or EventClusterer(session=session)
        self.tier1_classifier = tier1_classifier or Tier1Classifier(session=session)
        self.tier2_classifier = tier2_classifier or Tier2Classifier(session=session)

    async def process_pending_items(
        self,
        limit: int = 100,
        trends: list[Trend] | None = None,
    ) -> PipelineRunResult:
        """Process pending raw items from the database."""
        pending_items = await self._load_pending_items(limit=limit)
        return await self.process_items(pending_items, trends=trends)

    async def process_items(
        self,
        items: list[RawItem],
        trends: list[Trend] | None = None,
    ) -> PipelineRunResult:
        """Process explicit items through the pipeline."""
        if not items:
            return PipelineRunResult(scanned=0)

        active_trends = trends or await self._load_active_trends()
        if not active_trends:
            msg = "No active trends available for processing pipeline"
            raise ValueError(msg)

        run_result = PipelineRunResult(scanned=len(items))
        for item in items:
            execution = await self._process_item(item=item, trends=active_trends)
            run_result.results.append(execution.result)
            run_result.usage.embedding_api_calls += execution.usage.embedding_api_calls
            run_result.usage.tier1_prompt_tokens += execution.usage.tier1_prompt_tokens
            run_result.usage.tier1_completion_tokens += execution.usage.tier1_completion_tokens
            run_result.usage.tier1_api_calls += execution.usage.tier1_api_calls
            run_result.usage.tier2_prompt_tokens += execution.usage.tier2_prompt_tokens
            run_result.usage.tier2_completion_tokens += execution.usage.tier2_completion_tokens
            run_result.usage.tier2_api_calls += execution.usage.tier2_api_calls

            status = execution.result.final_status
            if status == ProcessingStatus.ERROR:
                run_result.errors += 1
                continue

            run_result.processed += 1
            if status == ProcessingStatus.CLASSIFIED:
                run_result.classified += 1
            if status == ProcessingStatus.NOISE:
                run_result.noise += 1
            if execution.result.duplicate:
                run_result.duplicates += 1
            if execution.result.embedded:
                run_result.embedded += 1
            if execution.result.event_created:
                run_result.events_created += 1
            if execution.result.event_merged:
                run_result.events_merged += 1

        return run_result

    async def _process_item(self, *, item: RawItem, trends: list[Trend]) -> _ItemExecution:
        item_id = self._item_id(item)
        item.processing_status = ProcessingStatus.PROCESSING
        item.error_message = None
        await self.session.flush()

        usage = PipelineUsage()
        try:
            duplicate_result = await self.deduplication_service.find_duplicate(
                external_id=item.external_id,
                url=item.url,
                content_hash=item.content_hash,
                exclude_item_id=item_id,
            )
            if duplicate_result.is_duplicate:
                item.processing_status = ProcessingStatus.NOISE
                await self.session.flush()
                return _ItemExecution(
                    result=PipelineItemResult(
                        item_id=item_id,
                        final_status=item.processing_status,
                        duplicate=True,
                    ),
                    usage=usage,
                )

            raw_content = item.raw_content.strip()
            if not raw_content:
                msg = "RawItem.raw_content must not be empty for pipeline processing"
                raise ValueError(msg)

            embedded = False
            if item.embedding is None:
                (
                    vectors,
                    _cache_hits,
                    embedding_api_calls,
                ) = await self.embedding_service.embed_texts([raw_content])
                item.embedding = vectors[0]
                usage.embedding_api_calls += embedding_api_calls
                embedded = True

            cluster_result = await self.event_clusterer.cluster_item(item)

            tier1_result, tier1_usage = await self._classify_tier1(item=item, trends=trends)
            usage.tier1_prompt_tokens += tier1_usage.prompt_tokens
            usage.tier1_completion_tokens += tier1_usage.completion_tokens
            usage.tier1_api_calls += tier1_usage.api_calls

            if not tier1_result.should_queue_tier2:
                item.processing_status = ProcessingStatus.NOISE
                await self.session.flush()
                return _ItemExecution(
                    result=self._build_item_result(
                        item_id=item_id,
                        status=item.processing_status,
                        cluster_result=cluster_result,
                        embedded=embedded,
                    ),
                    usage=usage,
                )

            event = await self._load_event(cluster_result.event_id)
            if event is None:
                msg = f"Event {cluster_result.event_id} not found after clustering"
                raise ValueError(msg)

            _tier2_result, tier2_usage = await self.tier2_classifier.classify_event(
                event=event,
                trends=trends,
            )
            usage.tier2_prompt_tokens += tier2_usage.prompt_tokens
            usage.tier2_completion_tokens += tier2_usage.completion_tokens
            usage.tier2_api_calls += tier2_usage.api_calls

            item.processing_status = ProcessingStatus.CLASSIFIED
            await self.session.flush()
            return _ItemExecution(
                result=self._build_item_result(
                    item_id=item_id,
                    status=item.processing_status,
                    cluster_result=cluster_result,
                    embedded=embedded,
                    tier2_applied=True,
                ),
                usage=usage,
            )
        except Exception as exc:
            item.processing_status = ProcessingStatus.ERROR
            item.error_message = str(exc)[:1000]
            await self.session.flush()
            logger.exception(
                "Processing pipeline failed for item",
                item_id=str(item_id),
            )
            return _ItemExecution(
                result=PipelineItemResult(
                    item_id=item_id,
                    final_status=item.processing_status,
                    error_message=item.error_message,
                ),
                usage=usage,
            )

    async def _classify_tier1(
        self,
        *,
        item: RawItem,
        trends: list[Trend],
    ) -> tuple[Tier1ItemResult, Tier1Usage]:
        tier1_results, tier1_usage = await self.tier1_classifier.classify_items([item], trends)
        if len(tier1_results) != 1:
            msg = "Tier 1 classifier must return exactly one result for single-item calls"
            raise ValueError(msg)
        return (tier1_results[0], tier1_usage)

    async def _load_pending_items(self, limit: int) -> list[RawItem]:
        query = (
            select(RawItem)
            .where(RawItem.processing_status == ProcessingStatus.PENDING)
            .order_by(RawItem.fetched_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(query)).all())

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    async def _load_event(self, event_id: UUID) -> Event | None:
        query = select(Event).where(Event.id == event_id).limit(1)
        event: Event | None = await self.session.scalar(query)
        return event

    @staticmethod
    def _item_id(item: RawItem) -> UUID:
        if item.id is None:
            msg = "RawItem must have an id before pipeline processing"
            raise ValueError(msg)
        return item.id

    @staticmethod
    def _build_item_result(
        *,
        item_id: UUID,
        status: ProcessingStatus,
        cluster_result: ClusterResult,
        embedded: bool,
        tier2_applied: bool = False,
    ) -> PipelineItemResult:
        return PipelineItemResult(
            item_id=item_id,
            final_status=status,
            event_id=cluster_result.event_id,
            embedded=embedded,
            event_created=cluster_result.created,
            event_merged=cluster_result.merged and not cluster_result.created,
            tier2_applied=tier2_applied,
        )

    @staticmethod
    def run_result_to_dict(result: PipelineRunResult) -> dict[str, Any]:
        """Serialize pipeline result into Celery-safe primitives."""
        return {
            "scanned": result.scanned,
            "processed": result.processed,
            "classified": result.classified,
            "noise": result.noise,
            "duplicates": result.duplicates,
            "errors": result.errors,
            "embedded": result.embedded,
            "events_created": result.events_created,
            "events_merged": result.events_merged,
            "embedding_api_calls": result.usage.embedding_api_calls,
            "tier1_prompt_tokens": result.usage.tier1_prompt_tokens,
            "tier1_completion_tokens": result.usage.tier1_completion_tokens,
            "tier1_api_calls": result.usage.tier1_api_calls,
            "tier2_prompt_tokens": result.usage.tier2_prompt_tokens,
            "tier2_completion_tokens": result.usage.tier2_completion_tokens,
            "tier2_api_calls": result.usage.tier2_api_calls,
        }
