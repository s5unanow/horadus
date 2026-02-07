"""
Processing pipeline orchestration for pending raw items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_engine import TrendEngine, calculate_evidence_delta
from src.processing.deduplication_service import DeduplicationService
from src.processing.embedding_service import EmbeddingService
from src.processing.event_clusterer import ClusterResult, EventClusterer
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event, ProcessingStatus, RawItem, Source, Trend, TrendEvidence

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
    trend_impacts_seen: int = 0
    trend_updates: int = 0
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
    trend_impacts_seen: int = 0
    trend_updates: int = 0
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
        trend_engine: TrendEngine | None = None,
    ) -> None:
        self.session = session
        self.deduplication_service = deduplication_service or DeduplicationService(session=session)
        self.embedding_service = embedding_service or EmbeddingService(session=session)
        self.event_clusterer = event_clusterer or EventClusterer(session=session)
        self.tier1_classifier = tier1_classifier or Tier1Classifier(session=session)
        self.tier2_classifier = tier2_classifier or Tier2Classifier(session=session)
        self.trend_engine = trend_engine or TrendEngine(session=session)

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
            run_result.trend_impacts_seen += execution.result.trend_impacts_seen
            run_result.trend_updates += execution.result.trend_updates

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
            trend_impacts_seen, trend_updates = await self._apply_trend_impacts(
                event=event,
                trends=trends,
            )

            item.processing_status = ProcessingStatus.CLASSIFIED
            await self.session.flush()
            return _ItemExecution(
                result=self._build_item_result(
                    item_id=item_id,
                    status=item.processing_status,
                    cluster_result=cluster_result,
                    embedded=embedded,
                    tier2_applied=True,
                    trend_impacts_seen=trend_impacts_seen,
                    trend_updates=trend_updates,
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

    async def _apply_trend_impacts(
        self,
        *,
        event: Event,
        trends: list[Trend],
    ) -> tuple[int, int]:
        if event.id is None:
            msg = "Event must have an id before applying trend impacts"
            raise ValueError(msg)

        claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        impacts_payload = claims.get("trend_impacts", [])
        if not isinstance(impacts_payload, list) or not impacts_payload:
            return (0, 0)

        trend_by_id = {self._trend_identifier(trend): trend for trend in trends}
        source_credibility = await self._load_event_source_credibility(event)
        corroboration_count = self._corroboration_count(event)

        impacts_seen = 0
        updates_applied = 0
        for payload in impacts_payload:
            impact = self._parse_trend_impact(payload)
            if impact is None:
                logger.warning("Skipping malformed trend impact payload", event_id=str(event.id))
                continue

            impacts_seen += 1
            trend = trend_by_id.get(impact["trend_id"])
            if trend is None:
                logger.warning(
                    "Skipping unknown trend impact",
                    event_id=str(event.id),
                    trend_id=impact["trend_id"],
                )
                continue

            signal_type = impact["signal_type"]
            indicator_weight = self._resolve_indicator_weight(trend=trend, signal_type=signal_type)
            if indicator_weight is None:
                logger.warning(
                    "Skipping trend impact with unknown indicator weight",
                    event_id=str(event.id),
                    trend_id=str(trend.id),
                    signal_type=signal_type,
                )
                continue

            trend_id = trend.id
            if trend_id is None:
                logger.warning(
                    "Skipping trend impact because trend id is missing",
                    event_id=str(event.id),
                    trend_name=trend.name,
                    signal_type=signal_type,
                )
                continue

            novelty_score = await self._novelty_score(
                trend_id=trend_id,
                signal_type=signal_type,
                event_id=event.id,
            )
            delta, factors = calculate_evidence_delta(
                signal_type=signal_type,
                indicator_weight=indicator_weight,
                source_credibility=source_credibility,
                corroboration_count=corroboration_count,
                novelty_score=novelty_score,
                direction=impact["direction"],
                severity=impact["severity"],
                confidence=impact["confidence"],
            )
            update = await self.trend_engine.apply_evidence(
                trend=trend,
                delta=delta,
                event_id=event.id,
                signal_type=signal_type,
                factors=factors,
                reasoning=self._impact_reasoning(impact),
            )
            if abs(update.delta_applied) > 0.0:
                updates_applied += 1

        return (impacts_seen, updates_applied)

    async def _load_event_source_credibility(self, event: Event) -> float:
        if event.primary_item_id is None:
            return DEFAULT_SOURCE_CREDIBILITY

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
            .where(RawItem.id == event.primary_item_id)
            .limit(1)
        )
        credibility = await self.session.scalar(query)
        try:
            return float(credibility) if credibility is not None else DEFAULT_SOURCE_CREDIBILITY
        except (TypeError, ValueError):
            return DEFAULT_SOURCE_CREDIBILITY

    async def _novelty_score(
        self,
        *,
        trend_id: UUID,
        signal_type: str,
        event_id: UUID,
    ) -> float:
        recent_window_start = datetime.now(tz=UTC) - timedelta(days=7)
        query = (
            select(TrendEvidence.id)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.signal_type == signal_type)
            .where(TrendEvidence.event_id != event_id)
            .where(TrendEvidence.created_at >= recent_window_start)
            .limit(1)
        )
        prior_evidence_id: UUID | None = await self.session.scalar(query)
        return 0.3 if prior_evidence_id is not None else 1.0

    @staticmethod
    def _corroboration_count(event: Event) -> int:
        if event.unique_source_count and event.unique_source_count > 0:
            return int(event.unique_source_count)
        if event.source_count and event.source_count > 0:
            return int(event.source_count)
        return 1

    @staticmethod
    def _trend_identifier(trend: Trend) -> str:
        definition = trend.definition if isinstance(trend.definition, dict) else {}
        definition_id = definition.get("id")
        if isinstance(definition_id, str) and definition_id.strip():
            return definition_id.strip()
        return str(trend.id)

    @staticmethod
    def _resolve_indicator_weight(*, trend: Trend, signal_type: str) -> float | None:
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        indicator_config = indicators.get(signal_type)
        if not isinstance(indicator_config, dict):
            return None

        raw_weight = indicator_config.get("weight")
        if raw_weight is None:
            return None
        if not isinstance(raw_weight, str | int | float):
            return None
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            return None

        if weight <= 0:
            return None
        return weight

    @staticmethod
    def _parse_trend_impact(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        trend_id = payload.get("trend_id")
        signal_type = payload.get("signal_type")
        direction = payload.get("direction")
        if not isinstance(trend_id, str) or not trend_id.strip():
            return None
        if not isinstance(signal_type, str) or not signal_type.strip():
            return None
        if direction not in ("escalatory", "de_escalatory"):
            return None

        try:
            severity = float(payload.get("severity", 1.0))
            confidence = float(payload.get("confidence", 1.0))
        except (TypeError, ValueError):
            return None

        rationale = payload.get("rationale")
        rationale_text = (
            rationale.strip() if isinstance(rationale, str) and rationale.strip() else None
        )

        return {
            "trend_id": trend_id.strip(),
            "signal_type": signal_type.strip(),
            "direction": direction,
            "severity": max(0.0, min(1.0, severity)),
            "confidence": max(0.0, min(1.0, confidence)),
            "rationale": rationale_text,
        }

    @staticmethod
    def _impact_reasoning(impact: dict[str, Any]) -> str:
        rationale = impact.get("rationale")
        if isinstance(rationale, str) and rationale:
            return rationale
        return f"Tier 2 classified {impact['signal_type']} as {impact['direction']}"

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
        trend_impacts_seen: int = 0,
        trend_updates: int = 0,
    ) -> PipelineItemResult:
        return PipelineItemResult(
            item_id=item_id,
            final_status=status,
            event_id=cluster_result.event_id,
            embedded=embedded,
            event_created=cluster_result.created,
            event_merged=cluster_result.merged and not cluster_result.created,
            tier2_applied=tier2_applied,
            trend_impacts_seen=trend_impacts_seen,
            trend_updates=trend_updates,
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
            "trend_impacts_seen": result.trend_impacts_seen,
            "trend_updates": result.trend_updates,
            "embedding_api_calls": result.usage.embedding_api_calls,
            "tier1_prompt_tokens": result.usage.tier1_prompt_tokens,
            "tier1_completion_tokens": result.usage.tier1_completion_tokens,
            "tier1_api_calls": result.usage.tier1_api_calls,
            "tier2_prompt_tokens": result.usage.tier2_prompt_tokens,
            "tier2_completion_tokens": result.usage.tier2_completion_tokens,
            "tier2_api_calls": result.usage.tier2_api_calls,
        }
