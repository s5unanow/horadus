"""
Processing pipeline orchestration for pending raw items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import (
    record_processing_ingested_language,
    record_processing_tier1_language_outcome,
    record_processing_tier2_language_usage,
    record_taxonomy_gap,
)
from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_engine import TrendEngine, calculate_evidence_delta, calculate_recency_novelty
from src.processing.cost_tracker import BudgetExceededError
from src.processing.deduplication_service import DeduplicationService
from src.processing.embedding_service import EmbeddingService
from src.processing.event_clusterer import ClusterResult, EventClusterer
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import (
    Event,
    EventItem,
    HumanFeedback,
    ProcessingStatus,
    RawItem,
    Source,
    TaxonomyGap,
    TaxonomyGapReason,
    Trend,
    TrendEvidence,
)

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class PipelineUsage:
    """Usage and API call metrics across one pipeline run."""

    embedding_api_calls: int = 0
    embedding_estimated_cost_usd: float = 0.0
    tier1_prompt_tokens: int = 0
    tier1_completion_tokens: int = 0
    tier1_api_calls: int = 0
    tier1_estimated_cost_usd: float = 0.0
    tier2_prompt_tokens: int = 0
    tier2_completion_tokens: int = 0
    tier2_api_calls: int = 0
    tier2_estimated_cost_usd: float = 0.0


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


@dataclass(slots=True)
class _PreparedItem:
    """Item state prepared for Tier-1 batch classification."""

    item: RawItem
    item_id: UUID
    raw_content: str


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
        execution_by_item: dict[UUID, _ItemExecution] = {}
        prepared_items: list[_PreparedItem] = []

        for item in items:
            language_label = self._language_metric_label(item.language)
            record_processing_ingested_language(language=language_label)
            prepared, execution = await self._prepare_item_for_tier1(item=item)
            if prepared is not None:
                prepared_items.append(prepared)
                if execution is not None:
                    self._accumulate_usage(run_result=run_result, usage=execution.usage)
                continue
            if execution is not None:
                execution_by_item[self._item_id(item)] = execution
                self._accumulate_usage(run_result=run_result, usage=execution.usage)
                continue

        tier1_result_by_item: dict[UUID, Tier1ItemResult] = {}
        tier1_failed_by_item: dict[UUID, _ItemExecution] = {}
        tier1_usage = PipelineUsage()
        if prepared_items:
            (
                tier1_result_by_item,
                tier1_failed_by_item,
                tier1_usage,
            ) = await self._classify_tier1_prepared_items(
                prepared_items=prepared_items, trends=active_trends
            )
            self._accumulate_usage(run_result=run_result, usage=tier1_usage)

        for prepared in prepared_items:
            if prepared.item_id in tier1_failed_by_item:
                execution_by_item[prepared.item_id] = tier1_failed_by_item[prepared.item_id]
                continue

            tier1_result = tier1_result_by_item.get(prepared.item_id)
            if tier1_result is None:
                prepared.item.processing_status = ProcessingStatus.ERROR
                prepared.item.processing_started_at = None
                prepared.item.error_message = (
                    "Tier 1 classifier returned no result for prepared pipeline item"
                )
                await self.session.flush()
                execution_by_item[prepared.item_id] = _ItemExecution(
                    result=PipelineItemResult(
                        item_id=prepared.item_id,
                        final_status=prepared.item.processing_status,
                        error_message=prepared.item.error_message,
                    )
                )
                continue

            record_processing_tier1_language_outcome(
                language=self._language_metric_label(prepared.item.language),
                outcome="pass" if tier1_result.should_queue_tier2 else "noise",
            )
            execution = await self._process_after_tier1(
                prepared=prepared,
                tier1_result=tier1_result,
                trends=active_trends,
            )
            execution_by_item[prepared.item_id] = execution
            self._accumulate_usage(run_result=run_result, usage=execution.usage)

        for item in items:
            item_id = self._item_id(item)
            execution = execution_by_item.get(item_id)
            if execution is None:
                item.processing_status = ProcessingStatus.ERROR
                item.processing_started_at = None
                item.error_message = "Pipeline execution result missing"
                await self.session.flush()
                execution = _ItemExecution(
                    result=PipelineItemResult(
                        item_id=item_id,
                        final_status=item.processing_status,
                        error_message=item.error_message,
                    )
                )
                execution_by_item[item_id] = execution
            run_result.results.append(execution.result)
            self._accumulate_result_counters(run_result=run_result, execution=execution)
        return run_result

    @staticmethod
    def _accumulate_usage(*, run_result: PipelineRunResult, usage: PipelineUsage) -> None:
        run_result.usage.embedding_api_calls += usage.embedding_api_calls
        run_result.usage.embedding_estimated_cost_usd += usage.embedding_estimated_cost_usd
        run_result.usage.tier1_prompt_tokens += usage.tier1_prompt_tokens
        run_result.usage.tier1_completion_tokens += usage.tier1_completion_tokens
        run_result.usage.tier1_api_calls += usage.tier1_api_calls
        run_result.usage.tier1_estimated_cost_usd += usage.tier1_estimated_cost_usd
        run_result.usage.tier2_prompt_tokens += usage.tier2_prompt_tokens
        run_result.usage.tier2_completion_tokens += usage.tier2_completion_tokens
        run_result.usage.tier2_api_calls += usage.tier2_api_calls
        run_result.usage.tier2_estimated_cost_usd += usage.tier2_estimated_cost_usd

    @staticmethod
    def _accumulate_result_counters(
        *,
        run_result: PipelineRunResult,
        execution: _ItemExecution,
    ) -> None:
        status = execution.result.final_status
        if status == ProcessingStatus.ERROR:
            run_result.errors += 1
            return
        if status == ProcessingStatus.PENDING:
            return

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

    async def _prepare_item_for_tier1(
        self,
        *,
        item: RawItem,
    ) -> tuple[_PreparedItem | None, _ItemExecution | None]:
        item_id = self._item_id(item)
        item.processing_status = ProcessingStatus.PROCESSING
        item.processing_started_at = datetime.now(tz=UTC)
        item.error_message = None
        await self.session.flush()

        try:
            duplicate_result = await self.deduplication_service.find_duplicate(
                external_id=item.external_id,
                url=item.url,
                content_hash=item.content_hash,
                exclude_item_id=item_id,
            )
            if duplicate_result.is_duplicate:
                item.processing_status = ProcessingStatus.NOISE
                item.processing_started_at = None
                await self.session.flush()
                return (
                    None,
                    _ItemExecution(
                        result=PipelineItemResult(
                            item_id=item_id,
                            final_status=item.processing_status,
                            duplicate=True,
                        )
                    ),
                )

            raw_content = item.raw_content.strip()
            if not raw_content:
                msg = "RawItem.raw_content must not be empty for pipeline processing"
                raise ValueError(msg)
            if self._is_unsupported_language(item.language):
                unsupported_mode = settings.LANGUAGE_POLICY_UNSUPPORTED_MODE
                item.processing_status = (
                    ProcessingStatus.PENDING
                    if unsupported_mode == "defer"
                    else ProcessingStatus.NOISE
                )
                item.processing_started_at = None
                normalized_language = self._language_metric_label(item.language)
                item.error_message = (
                    f"unsupported_language:{normalized_language}:{unsupported_mode}"
                )
                await self.session.flush()
                return (
                    None,
                    _ItemExecution(
                        result=self._build_item_result(
                            item_id=item_id,
                            status=item.processing_status,
                            cluster_result=None,
                            embedded=False,
                            error_message=item.error_message,
                        )
                    ),
                )

            return (
                _PreparedItem(
                    item=item,
                    item_id=item_id,
                    raw_content=raw_content,
                ),
                None,
            )
        except BudgetExceededError as exc:
            item.processing_status = ProcessingStatus.PENDING
            item.processing_started_at = None
            item.error_message = None
            await self.session.flush()
            logger.warning(
                "Budget exceeded; leaving item pending for retry",
                item_id=str(item_id),
                reason=str(exc),
            )
            return (
                None,
                _ItemExecution(
                    result=self._build_item_result(
                        item_id=item_id,
                        status=item.processing_status,
                        cluster_result=None,
                        embedded=False,
                        error_message=str(exc),
                    )
                ),
            )
        except Exception as exc:
            item.processing_status = ProcessingStatus.ERROR
            item.processing_started_at = None
            item.error_message = str(exc)[:1000]
            await self.session.flush()
            logger.exception(
                "Processing pipeline failed for item",
                item_id=str(item_id),
            )
            return (
                None,
                _ItemExecution(
                    result=PipelineItemResult(
                        item_id=item_id,
                        final_status=item.processing_status,
                        error_message=item.error_message,
                    )
                ),
            )

    async def _classify_tier1_prepared_items(
        self,
        *,
        prepared_items: list[_PreparedItem],
        trends: list[Trend],
    ) -> tuple[dict[UUID, Tier1ItemResult], dict[UUID, _ItemExecution], PipelineUsage]:
        items = [prepared.item for prepared in prepared_items]
        usage = PipelineUsage()
        result_by_item: dict[UUID, Tier1ItemResult] = {}
        failed_by_item: dict[UUID, _ItemExecution] = {}

        def _record_usage(tier1_usage: Tier1Usage) -> None:
            usage.tier1_prompt_tokens += tier1_usage.prompt_tokens
            usage.tier1_completion_tokens += tier1_usage.completion_tokens
            usage.tier1_api_calls += tier1_usage.api_calls
            usage.tier1_estimated_cost_usd += tier1_usage.estimated_cost_usd

        try:
            batch_results, batch_usage = await self.tier1_classifier.classify_items(items, trends)
            _record_usage(batch_usage)
            result_by_item = {result.item_id: result for result in batch_results}
            return (result_by_item, failed_by_item, usage)
        except BudgetExceededError as exc:
            for prepared in prepared_items:
                prepared.item.processing_status = ProcessingStatus.PENDING
                prepared.item.processing_started_at = None
                prepared.item.error_message = None
                failed_by_item[prepared.item_id] = _ItemExecution(
                    result=self._build_item_result(
                        item_id=prepared.item_id,
                        status=prepared.item.processing_status,
                        cluster_result=None,
                        embedded=False,
                        error_message=str(exc),
                    )
                )
            await self.session.flush()
            logger.warning(
                "Tier 1 batch classification budget exceeded; leaving prepared items pending",
                prepared_items=len(prepared_items),
                reason=str(exc),
            )
            return ({}, failed_by_item, usage)
        except Exception as exc:
            logger.warning(
                "Tier 1 batch classification failed; falling back to per-item classification",
                prepared_items=len(prepared_items),
                reason=str(exc),
            )

        for prepared in prepared_items:
            try:
                item_result, item_usage = await self._classify_tier1(
                    item=prepared.item, trends=trends
                )
                _record_usage(item_usage)
                result_by_item[prepared.item_id] = item_result
            except BudgetExceededError as exc:
                prepared.item.processing_status = ProcessingStatus.PENDING
                prepared.item.processing_started_at = None
                prepared.item.error_message = None
                failed_by_item[prepared.item_id] = _ItemExecution(
                    result=self._build_item_result(
                        item_id=prepared.item_id,
                        status=prepared.item.processing_status,
                        cluster_result=None,
                        embedded=False,
                        error_message=str(exc),
                    )
                )
            except Exception as exc:
                prepared.item.processing_status = ProcessingStatus.ERROR
                prepared.item.processing_started_at = None
                prepared.item.error_message = str(exc)[:1000]
                failed_by_item[prepared.item_id] = _ItemExecution(
                    result=PipelineItemResult(
                        item_id=prepared.item_id,
                        final_status=prepared.item.processing_status,
                        error_message=prepared.item.error_message,
                    )
                )

        await self.session.flush()
        return (result_by_item, failed_by_item, usage)

    async def _process_after_tier1(
        self,
        *,
        prepared: _PreparedItem,
        tier1_result: Tier1ItemResult,
        trends: list[Trend],
    ) -> _ItemExecution:
        usage = PipelineUsage()
        item = prepared.item
        cluster_result: ClusterResult | None = None
        embedded = False
        try:
            if not tier1_result.should_queue_tier2:
                item.processing_status = ProcessingStatus.NOISE
                item.processing_started_at = None
                await self.session.flush()
                return _ItemExecution(
                    result=self._build_item_result(
                        item_id=prepared.item_id,
                        status=item.processing_status,
                        cluster_result=None,
                        embedded=False,
                    ),
                    usage=usage,
                )

            if item.embedding is None:
                (
                    vectors,
                    _cache_hits,
                    embedding_api_calls,
                ) = await self.embedding_service.embed_texts([prepared.raw_content])
                item.embedding = vectors[0]
                item.embedding_model = getattr(
                    self.embedding_service,
                    "model",
                    settings.EMBEDDING_MODEL,
                )
                item.embedding_generated_at = datetime.now(tz=UTC)
                embedded = True
                usage.embedding_api_calls += embedding_api_calls

            cluster_result = await self.event_clusterer.cluster_item(item)
            event = await self._load_event(cluster_result.event_id)
            if event is None:
                msg = f"Event {cluster_result.event_id} not found after clustering"
                raise ValueError(msg)

            suppression_action = await self._event_suppression_action(
                event_id=cluster_result.event_id
            )
            if suppression_action is not None:
                item.processing_status = ProcessingStatus.NOISE
                item.processing_started_at = None
                await self.session.flush()
                logger.info(
                    "Skipping event due to human feedback suppression",
                    item_id=str(prepared.item_id),
                    event_id=str(cluster_result.event_id),
                    action=suppression_action,
                )
                return _ItemExecution(
                    result=self._build_item_result(
                        item_id=prepared.item_id,
                        status=item.processing_status,
                        cluster_result=cluster_result,
                        embedded=embedded,
                    ),
                    usage=usage,
                )

            _tier2_result, tier2_usage = await self.tier2_classifier.classify_event(
                event=event,
                trends=trends,
            )
            record_processing_tier2_language_usage(
                language=self._language_metric_label(item.language),
            )
            usage.tier2_prompt_tokens += tier2_usage.prompt_tokens
            usage.tier2_completion_tokens += tier2_usage.completion_tokens
            usage.tier2_api_calls += tier2_usage.api_calls
            usage.tier2_estimated_cost_usd += tier2_usage.estimated_cost_usd
            trend_impacts_seen, trend_updates = await self._apply_trend_impacts(
                event=event,
                trends=trends,
            )

            item.processing_status = ProcessingStatus.CLASSIFIED
            item.processing_started_at = None
            await self.session.flush()
            return _ItemExecution(
                result=self._build_item_result(
                    item_id=prepared.item_id,
                    status=item.processing_status,
                    cluster_result=cluster_result,
                    embedded=embedded,
                    tier2_applied=True,
                    trend_impacts_seen=trend_impacts_seen,
                    trend_updates=trend_updates,
                ),
                usage=usage,
            )
        except BudgetExceededError as exc:
            item.processing_status = ProcessingStatus.PENDING
            item.processing_started_at = None
            item.error_message = None
            await self.session.flush()
            logger.warning(
                "Budget exceeded; leaving item pending for retry",
                item_id=str(prepared.item_id),
                reason=str(exc),
            )
            return _ItemExecution(
                result=self._build_item_result(
                    item_id=prepared.item_id,
                    status=item.processing_status,
                    cluster_result=cluster_result,
                    embedded=embedded,
                    error_message=str(exc),
                ),
                usage=usage,
            )
        except Exception as exc:
            item.processing_status = ProcessingStatus.ERROR
            item.processing_started_at = None
            item.error_message = str(exc)[:1000]
            await self.session.flush()
            logger.exception(
                "Processing pipeline failed for item",
                item_id=str(prepared.item_id),
            )
            return _ItemExecution(
                result=PipelineItemResult(
                    item_id=prepared.item_id,
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

    @staticmethod
    def _normalize_language_code(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        mapping = {
            "english": "en",
            "eng": "en",
            "ukrainian": "uk",
            "ukr": "uk",
            "russian": "ru",
            "rus": "ru",
        }
        if normalized in mapping:
            return mapping[normalized]
        if len(normalized) >= 2:
            return normalized[:2]
        return normalized

    @classmethod
    def _language_metric_label(cls, value: str | None) -> str:
        normalized = cls._normalize_language_code(value)
        if normalized is None:
            return "unknown"
        return normalized

    @classmethod
    def _is_unsupported_language(cls, value: str | None) -> bool:
        normalized = cls._normalize_language_code(value)
        if normalized is None:
            return False
        supported = set(settings.LANGUAGE_POLICY_SUPPORTED_LANGUAGES)
        return normalized not in supported

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    async def _load_event(self, event_id: UUID) -> Event | None:
        query = select(Event).where(Event.id == event_id).limit(1)
        event: Event | None = await self.session.scalar(query)
        return event

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
        return action

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
        corroboration_score = await self._corroboration_score(event)

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
                await self._capture_taxonomy_gap(
                    event_id=event.id,
                    trend_id=impact["trend_id"],
                    signal_type=impact["signal_type"],
                    reason=TaxonomyGapReason.UNKNOWN_TREND_ID,
                    details={
                        "direction": impact["direction"],
                        "severity": impact["severity"],
                        "confidence": impact["confidence"],
                        "rationale": impact["rationale"],
                    },
                )
                logger.warning(
                    "Skipping unknown trend impact",
                    event_id=str(event.id),
                    trend_id=impact["trend_id"],
                )
                continue

            signal_type = impact["signal_type"]
            indicator_weight = self._resolve_indicator_weight(trend=trend, signal_type=signal_type)
            if indicator_weight is None:
                await self._capture_taxonomy_gap(
                    event_id=event.id,
                    trend_id=self._trend_identifier(trend),
                    signal_type=signal_type,
                    reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
                    details={
                        "trend_uuid": str(trend.id),
                        "direction": impact["direction"],
                        "severity": impact["severity"],
                        "confidence": impact["confidence"],
                        "rationale": impact["rationale"],
                    },
                )
                logger.warning(
                    "Skipping trend impact with unknown indicator weight",
                    event_id=str(event.id),
                    trend_id=str(trend.id),
                    signal_type=signal_type,
                )
                continue
            indicator_decay_half_life_days = self._resolve_indicator_decay_half_life(
                trend=trend, signal_type=signal_type
            )
            evidence_age_days = self._event_age_days(event)

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
                corroboration_count=corroboration_score,
                novelty_score=novelty_score,
                direction=impact["direction"],
                severity=impact["severity"],
                confidence=impact["confidence"],
                evidence_age_days=evidence_age_days,
                indicator_decay_half_life_days=indicator_decay_half_life_days,
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

    async def _capture_taxonomy_gap(
        self,
        *,
        event_id: UUID,
        trend_id: str,
        signal_type: str,
        reason: TaxonomyGapReason,
        details: dict[str, Any],
    ) -> None:
        try:
            self.session.add(
                TaxonomyGap(
                    event_id=event_id,
                    trend_id=trend_id,
                    signal_type=signal_type,
                    reason=reason,
                    source="pipeline",
                    details=details,
                )
            )
            await self.session.flush()
            record_taxonomy_gap(
                reason=reason.value,
                trend_id=trend_id,
                signal_type=signal_type,
            )
        except Exception:
            logger.exception(
                "Failed to capture taxonomy gap",
                event_id=str(event_id),
                trend_id=trend_id,
                signal_type=signal_type,
                reason=reason.value,
            )

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
        query = (
            select(func.max(TrendEvidence.created_at))
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.signal_type == signal_type)
            .where(TrendEvidence.event_id != event_id)
        )
        last_seen_at: datetime | None = await self.session.scalar(query)
        return calculate_recency_novelty(last_seen_at=last_seen_at)

    async def _corroboration_score(self, event: Event) -> float:
        base_score = self._fallback_corroboration_score(event)
        if event.id is None:
            return max(0.1, base_score * self._contradiction_penalty(event))

        try:
            query = (
                select(
                    Source.id,
                    Source.source_tier,
                    Source.reporting_type,
                )
                .join(RawItem, RawItem.source_id == Source.id)
                .join(EventItem, EventItem.item_id == RawItem.id)
                .where(EventItem.event_id == event.id)
            )
            result = await self.session.execute(query)
            rows_raw = result.all()
            if hasattr(rows_raw, "__await__"):
                rows_raw = await rows_raw
        except Exception:
            return max(0.1, base_score * self._contradiction_penalty(event))

        if not isinstance(rows_raw, list):
            return max(0.1, base_score * self._contradiction_penalty(event))
        rows = [row for row in rows_raw if isinstance(row, tuple) and len(row) >= 3]
        if not rows:
            return max(0.1, base_score * self._contradiction_penalty(event))

        cluster_weights: dict[str, float] = {}
        for source_id, source_tier, reporting_type in rows:
            cluster_key = self._source_cluster_key(
                source_id=source_id,
                source_tier=source_tier,
                reporting_type=reporting_type,
            )
            weight = self._reporting_type_weight(reporting_type)
            cluster_weights[cluster_key] = max(cluster_weights.get(cluster_key, 0.0), weight)

        independent_score = sum(cluster_weights.values())
        contradiction_penalty = self._contradiction_penalty(event)
        return max(0.1, independent_score * contradiction_penalty)

    @staticmethod
    def _fallback_corroboration_score(event: Event) -> float:
        if event.unique_source_count and event.unique_source_count > 0:
            return float(event.unique_source_count)
        if event.source_count and event.source_count > 0:
            return float(event.source_count)
        return 1.0

    @staticmethod
    def _source_cluster_key(
        *,
        source_id: UUID,
        source_tier: str | None,
        reporting_type: str | None,
    ) -> str:
        tier = (source_tier or "unknown").strip().lower()
        reporting = (reporting_type or "unknown").strip().lower()
        if reporting == "firsthand":
            return f"firsthand:{source_id}"
        return f"{tier}:{reporting}"

    @staticmethod
    def _reporting_type_weight(reporting_type: str | None) -> float:
        reporting = (reporting_type or "").strip().lower()
        if reporting == "firsthand":
            return 1.0
        if reporting == "secondary":
            return 0.6
        if reporting == "aggregator":
            return 0.35
        return 0.5

    @staticmethod
    def _contradiction_penalty(event: Event) -> float:
        claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        claim_graph = claims.get("claim_graph", {})
        links = claim_graph.get("links", []) if isinstance(claim_graph, dict) else []
        contradiction_links = 0
        if isinstance(links, list):
            contradiction_links = sum(
                1
                for link in links
                if isinstance(link, dict) and link.get("relation") == "contradict"
            )

        if contradiction_links > 0:
            return max(0.4, 1.0 - 0.15 * contradiction_links)
        if event.has_contradictions:
            return 0.7
        return 1.0

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
    def _resolve_indicator_decay_half_life(*, trend: Trend, signal_type: str) -> float | None:
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        indicator_config = indicators.get(signal_type)

        if isinstance(indicator_config, dict):
            raw_indicator_half_life = indicator_config.get("decay_half_life_days")
            if isinstance(raw_indicator_half_life, str | int | float):
                try:
                    parsed = float(raw_indicator_half_life)
                except (TypeError, ValueError):
                    parsed = 0.0
                if parsed > 0:
                    return parsed

        raw_trend_half_life = getattr(trend, "decay_half_life_days", None)
        if isinstance(raw_trend_half_life, str | int | float):
            try:
                parsed = float(raw_trend_half_life)
            except (TypeError, ValueError):
                return None
            if parsed > 0:
                return parsed
        return None

    @staticmethod
    def _event_age_days(event: Event) -> float:
        reference_time = event.extracted_when or event.last_mention_at or event.first_seen_at
        if reference_time is None:
            return 0.0
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        else:
            reference_time = reference_time.astimezone(UTC)
        return max(0.0, (datetime.now(tz=UTC) - reference_time).total_seconds() / 86400.0)

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
        cluster_result: ClusterResult | None,
        embedded: bool,
        tier2_applied: bool = False,
        trend_impacts_seen: int = 0,
        trend_updates: int = 0,
        error_message: str | None = None,
    ) -> PipelineItemResult:
        event_id = cluster_result.event_id if cluster_result is not None else None
        event_created = cluster_result.created if cluster_result is not None else False
        event_merged = (
            cluster_result.merged and not cluster_result.created
            if cluster_result is not None
            else False
        )
        return PipelineItemResult(
            item_id=item_id,
            final_status=status,
            event_id=event_id,
            embedded=embedded,
            event_created=event_created,
            event_merged=event_merged,
            tier2_applied=tier2_applied,
            trend_impacts_seen=trend_impacts_seen,
            trend_updates=trend_updates,
            error_message=error_message,
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
            "embedding_estimated_cost_usd": round(result.usage.embedding_estimated_cost_usd, 8),
            "tier1_prompt_tokens": result.usage.tier1_prompt_tokens,
            "tier1_completion_tokens": result.usage.tier1_completion_tokens,
            "tier1_api_calls": result.usage.tier1_api_calls,
            "tier1_estimated_cost_usd": round(result.usage.tier1_estimated_cost_usd, 8),
            "tier2_prompt_tokens": result.usage.tier2_prompt_tokens,
            "tier2_completion_tokens": result.usage.tier2_completion_tokens,
            "tier2_api_calls": result.usage.tier2_api_calls,
            "tier2_estimated_cost_usd": round(result.usage.tier2_estimated_cost_usd, 8),
        }
