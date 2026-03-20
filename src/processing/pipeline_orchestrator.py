"""
Processing pipeline orchestration for pending raw items.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import (
    record_processing_corroboration_path,
    record_processing_event_suppression,
    record_processing_ingested_language,
    record_processing_tier1_language_outcome,
    record_processing_tier2_language_usage,
    record_taxonomy_gap,
    set_llm_degraded_mode,
)
from src.core.risk import get_risk_level
from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_config import index_trends_by_runtime_id, trend_runtime_id_for_record
from src.core.trend_engine import (
    TrendEngine,
    calculate_evidence_delta,
    calculate_recency_novelty,
    logodds_to_prob,
)
from src.processing.cost_tracker import BudgetExceededError
from src.processing.deduplication_service import DeduplicationService
from src.processing.embedding_service import EmbeddingService
from src.processing.event_clusterer import ClusterResult, EventClusterer
from src.processing.pipeline_retry import build_retryable_pipeline_error
from src.processing.pipeline_types import (
    PipelineItemResult,
    PipelineRunResult,
    PipelineUsage,
    _ItemExecution,
    _PreparedItem,
)
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Classifier
from src.processing.trend_impact_mapping import (
    iter_unresolved_mapping_gaps,
    taxonomy_gap_reason_for_mapping,
)
from src.processing.trend_impact_reconciliation import (
    event_age_days,
    impact_reasoning,
    parse_trend_impact,
    reconcile_event_trend_impacts,
    resolve_indicator_decay_half_life,
    resolve_indicator_weight,
)
from src.storage.event_state import (
    FALLBACK_CORROBORATION_MODE,
    PROVENANCE_AWARE_CORROBORATION_MODE,
    resolved_corroboration_mode,
    resolved_corroboration_score,
)
from src.storage.models import (
    Event,
    LLMReplayQueueItem,
    ProcessingStatus,
    RawItem,
    Source,
    TaxonomyGap,
    TaxonomyGapReason,
    Trend,
    TrendEvidence,
)
from src.storage.restatement_models import HumanFeedback

if TYPE_CHECKING:
    from src.processing.degraded_llm_tracker import DegradedLLMStatus, DegradedLLMTracker

logger = structlog.get_logger(__name__)


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
        degraded_llm_tracker: DegradedLLMTracker | None = None,
    ) -> None:
        self.session = session
        self.deduplication_service = deduplication_service or DeduplicationService(session=session)
        self.embedding_service = embedding_service or EmbeddingService(session=session)
        self.event_clusterer = event_clusterer or EventClusterer(session=session)
        self.tier1_classifier = tier1_classifier or Tier1Classifier(session=session)
        self.tier2_classifier = tier2_classifier or Tier2Classifier(session=session)
        self.trend_engine = trend_engine or TrendEngine(session=session)
        self.degraded_llm_tracker = degraded_llm_tracker

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
        self._index_trends_by_runtime_id(active_trends)

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
        if execution.result.degraded_llm_hold:
            run_result.degraded_llm = True
            run_result.degraded_holds += 1
        if execution.result.replay_enqueued:
            run_result.replay_enqueued += 1

    @staticmethod
    def _reset_item_for_retry(item: RawItem) -> None:
        item.processing_status = ProcessingStatus.PENDING
        item.processing_started_at = None
        item.error_message = None

    def _raise_retryable_failure_if_needed(
        self,
        *,
        item: RawItem | None,
        stage: str,
        exc: Exception,
    ) -> None:
        retryable_error = build_retryable_pipeline_error(
            item_id=getattr(item, "id", None),
            stage=stage,
            exc=exc,
        )
        if retryable_error is None:
            return
        if item is not None:
            self._reset_item_for_retry(item)
        logger.warning(
            "Retryable pipeline failure will be requeued at task level",
            item_id=str(retryable_error.item_id) if retryable_error.item_id is not None else None,
            stage=stage,
            reason=retryable_error.reason,
            error=str(exc),
        )
        raise retryable_error from exc

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
            self._raise_retryable_failure_if_needed(item=item, stage="prepare", exc=exc)
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
            retryable_error = build_retryable_pipeline_error(
                item_id=None,
                stage="tier1_batch",
                exc=exc,
            )
            if retryable_error is not None:
                for prepared in prepared_items:
                    self._reset_item_for_retry(prepared.item)
                logger.warning(
                    "Retryable Tier 1 batch failure will be requeued at task level",
                    prepared_items=len(prepared_items),
                    reason=retryable_error.reason,
                    error=str(exc),
                )
                raise retryable_error from exc
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
                self._raise_retryable_failure_if_needed(item=prepared.item, stage="tier1", exc=exc)
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
                embedding_audit = None
                embed_with_contexts = getattr(
                    self.embedding_service, "embed_texts_with_contexts", None
                )
                if callable(embed_with_contexts):
                    (
                        vectors,
                        audits,
                        _cache_hits,
                        embedding_api_calls,
                    ) = await embed_with_contexts(
                        [prepared.raw_content],
                        entity_type="raw_item",
                        entity_ids=[prepared.item_id],
                    )
                    embedding_audit = audits[0] if audits else None
                else:
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
                if embedding_audit is not None:
                    item.embedding_input_tokens = embedding_audit.original_tokens
                    item.embedding_retained_tokens = embedding_audit.retained_tokens
                    item.embedding_was_truncated = embedding_audit.was_truncated
                    item.embedding_truncation_strategy = (
                        embedding_audit.strategy if embedding_audit.was_cut else None
                    )
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
                record_processing_event_suppression(
                    action=suppression_action,
                    stage="pipeline_post_cluster",
                )
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
            await self._capture_unresolved_trend_mapping(event=event)
            degraded_hold = False
            replay_enqueued = False
            trend_impacts_seen = 0
            trend_updates = 0
            if self.degraded_llm_tracker is not None:
                # Avoid inflating the rolling window with semantic-cache hits (no actual API call).
                if int(tier2_usage.api_calls) > 0:
                    await asyncio.to_thread(
                        self.degraded_llm_tracker.record_invocation,
                        used_secondary_route=bool(tier2_usage.used_secondary_route),
                    )
                degraded_status = await asyncio.to_thread(self.degraded_llm_tracker.evaluate)
                set_llm_degraded_mode(
                    stage=degraded_status.stage,
                    is_degraded=bool(degraded_status.is_degraded),
                )
                degraded_hold = bool(degraded_status.is_degraded)
                if degraded_hold:
                    claims = (
                        event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
                    )
                    policy_meta = {
                        "degraded_llm": True,
                        "availability_degraded": bool(degraded_status.availability_degraded),
                        "quality_degraded": bool(degraded_status.quality_degraded),
                        "degraded_since_epoch": degraded_status.degraded_since_epoch,
                        "window_total_calls": degraded_status.window.total_calls,
                        "window_secondary_calls": degraded_status.window.secondary_calls,
                        "window_failover_ratio": round(degraded_status.window.failover_ratio, 6),
                        "tier2_active_provider": tier2_usage.active_provider,
                        "tier2_active_model": tier2_usage.active_model,
                        "tier2_active_reasoning_effort": tier2_usage.active_reasoning_effort,
                        "tier2_used_secondary_route": bool(tier2_usage.used_secondary_route),
                    }
                    claims["_llm_policy"] = policy_meta
                    event.extracted_claims = claims
                    replay_enqueued = await self._maybe_enqueue_replay(
                        event=event,
                        trends=trends,
                        degraded_status=degraded_status,
                        tier2_usage=tier2_usage,
                    )

            if not degraded_hold:
                trend_impacts_seen, trend_updates = await self._apply_trend_impacts(
                    event=event,
                    trends=trends,
                )
            else:
                # Preserve extraction fields, but hold probability semantics until replay.
                claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
                impacts_payload = claims.get("trend_impacts", [])
                if isinstance(impacts_payload, list):
                    trend_impacts_seen = len(impacts_payload)

            item.processing_status = ProcessingStatus.CLASSIFIED
            item.processing_started_at = None
            await self.session.flush()
            return _ItemExecution(
                result=self._build_item_result(
                    item_id=prepared.item_id,
                    status=item.processing_status,
                    cluster_result=cluster_result,
                    embedded=embedded,
                    tier2_applied=not degraded_hold,
                    degraded_llm_hold=degraded_hold,
                    replay_enqueued=replay_enqueued,
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
            self._raise_retryable_failure_if_needed(item=item, stage="post_tier1", exc=exc)
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
        if not isinstance(action, str):
            return None
        normalized_action = action.strip()
        if normalized_action not in {"mark_noise", "invalidate"}:
            return None
        return normalized_action

    async def _apply_trend_impacts(
        self,
        *,
        event: Event,
        trends: list[Trend],
    ) -> tuple[int, int]:
        return await reconcile_event_trend_impacts(
            session=self.session,
            trend_engine=self.trend_engine,
            event=event,
            trends=trends,
            load_event_source_credibility=self._load_event_source_credibility,
            load_corroboration_score=self._corroboration_score,
            load_novelty_score=self._novelty_score,
            capture_taxonomy_gap=self._capture_taxonomy_gap,
        )

    async def _maybe_enqueue_replay(
        self,
        *,
        event: Event,
        trends: list[Trend],
        degraded_status: DegradedLLMStatus,
        tier2_usage: Any,
    ) -> bool:
        if not settings.LLM_DEGRADED_REPLAY_ENABLED:
            return False
        if event.id is None:
            return False

        high_impact, max_abs_delta, risk_level_crossing = await self._is_high_impact_event(
            event=event,
            trends=trends,
        )
        if not high_impact:
            return False

        pending_count = await self.session.scalar(
            select(func.count())
            .select_from(LLMReplayQueueItem)
            .where(LLMReplayQueueItem.status == "pending")
        )
        if int(pending_count or 0) >= int(settings.LLM_DEGRADED_REPLAY_MAX_QUEUE):
            logger.warning(
                "Replay queue full; skipping enqueue",
                event_id=str(event.id),
                pending_count=int(pending_count or 0),
                max_queue=int(settings.LLM_DEGRADED_REPLAY_MAX_QUEUE),
            )
            return False

        priority = int(min(1000, round(max_abs_delta * 1000)))
        details = {
            "reason": "degraded_llm_high_impact",
            "max_abs_delta": round(max_abs_delta, 6),
            "risk_level_crossing": bool(risk_level_crossing),
            "degraded_since_epoch": degraded_status.degraded_since_epoch,
            "window": {
                "total_calls": degraded_status.window.total_calls,
                "secondary_calls": degraded_status.window.secondary_calls,
                "failover_ratio": round(degraded_status.window.failover_ratio, 6),
            },
            "tier2_route": {
                "active_provider": getattr(tier2_usage, "active_provider", None),
                "active_model": getattr(tier2_usage, "active_model", None),
                "active_reasoning_effort": getattr(tier2_usage, "active_reasoning_effort", None),
                "used_secondary_route": bool(getattr(tier2_usage, "used_secondary_route", False)),
            },
        }
        try:
            async with self.session.begin_nested():
                self.session.add(
                    LLMReplayQueueItem(
                        stage="tier2",
                        event_id=event.id,
                        priority=priority,
                        details=details,
                    )
                )
                await self.session.flush()
            logger.info(
                "Enqueued event for post-recovery Tier-2 replay",
                event_id=str(event.id),
                priority=priority,
                max_abs_delta=round(max_abs_delta, 6),
                risk_level_crossing=bool(risk_level_crossing),
            )
            return True
        except IntegrityError:
            # Another worker already queued it (or the event was queued earlier).
            return False

    async def _is_high_impact_event(
        self,
        *,
        event: Event,
        trends: list[Trend],
    ) -> tuple[bool, float, bool]:
        claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        impacts_payload = claims.get("trend_impacts", [])
        if not isinstance(impacts_payload, list) or not impacts_payload:
            return (False, 0.0, False)

        trend_by_id = index_trends_by_runtime_id(trends)
        source_credibility = await self._load_event_source_credibility(event)
        corroboration_score = await self._corroboration_score(event)

        max_abs_delta = 0.0
        any_risk_crossing = False
        min_abs_delta = float(settings.LLM_DEGRADED_REPLAY_MIN_ABS_DELTA)

        high_impact = False
        for payload in impacts_payload:
            impact = parse_trend_impact(payload)
            if impact is None:
                continue

            trend = trend_by_id.get(impact.trend_id)
            if trend is None or trend.id is None:
                continue

            signal_type = impact.signal_type
            indicator_weight = resolve_indicator_weight(trend=trend, signal_type=signal_type)
            if indicator_weight is None:
                continue
            indicator_decay_half_life_days = resolve_indicator_decay_half_life(
                trend=trend, signal_type=signal_type
            )
            evidence_age_days = event_age_days(event)
            novelty_score = await self._novelty_score(
                trend_id=trend.id,
                signal_type=signal_type,
                event_id=event.id,
            )

            delta, _factors = calculate_evidence_delta(
                signal_type=signal_type,
                indicator_weight=indicator_weight,
                source_credibility=source_credibility,
                corroboration_count=corroboration_score,
                novelty_score=novelty_score,
                direction=impact.direction,
                severity=impact.severity,
                confidence=impact.confidence,
                evidence_age_days=evidence_age_days,
                indicator_decay_half_life_days=indicator_decay_half_life_days,
            )
            abs_delta = abs(float(delta))
            if abs_delta > max_abs_delta:
                max_abs_delta = abs_delta

            old_prob = logodds_to_prob(float(trend.current_log_odds))
            new_prob = logodds_to_prob(float(trend.current_log_odds) + float(delta))
            if get_risk_level(old_prob) != get_risk_level(new_prob):
                any_risk_crossing = True

            if abs_delta >= min_abs_delta or any_risk_crossing:
                high_impact = True

        return (high_impact, max_abs_delta, any_risk_crossing)

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

    async def _capture_unresolved_trend_mapping(self, *, event: Event) -> None:
        if event.id is None:
            return
        for diagnostic in iter_unresolved_mapping_gaps(event):
            reason_value = diagnostic.get("reason")
            if not isinstance(reason_value, str) or not reason_value.strip():
                continue
            trend_id = diagnostic.get("trend_id")
            signal_type = diagnostic.get("signal_type")
            details = diagnostic.get("details")
            if not isinstance(trend_id, str) or not trend_id.strip():
                continue
            if not isinstance(signal_type, str) or not signal_type.strip():
                continue
            if not isinstance(details, dict):
                details = {}
            await self._capture_taxonomy_gap(
                event_id=event.id,
                trend_id=trend_id.strip(),
                signal_type=signal_type.strip(),
                reason=taxonomy_gap_reason_for_mapping(reason_value.strip()),
                details={
                    **details,
                    "event_claim_key": diagnostic.get("event_claim_key"),
                    "event_claim_text": diagnostic.get("event_claim_text"),
                },
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
            .where(TrendEvidence.is_invalidated.is_(False))
        )
        last_seen_at: datetime | None = await self.session.scalar(query)
        return calculate_recency_novelty(last_seen_at=last_seen_at)

    async def _corroboration_score(self, event: Event) -> float:
        base_score = resolved_corroboration_score(event)
        corroboration_mode = resolved_corroboration_mode(event)
        if corroboration_mode == PROVENANCE_AWARE_CORROBORATION_MODE:
            self._record_corroboration_path(
                event=event,
                mode=PROVENANCE_AWARE_CORROBORATION_MODE,
                reason="persisted_event_provenance",
            )
        else:
            self._record_corroboration_path(
                event=event,
                mode=FALLBACK_CORROBORATION_MODE,
                reason="missing_event_provenance",
            )
        return max(0.1, base_score * self._contradiction_penalty(event))

    @staticmethod
    def _fallback_corroboration_score(event: Event) -> float:
        if event.independent_evidence_count and event.independent_evidence_count > 0:
            return float(event.independent_evidence_count)
        if event.unique_source_count and event.unique_source_count > 0:
            return float(event.unique_source_count)
        if event.source_count and event.source_count > 0:
            return float(event.source_count)
        return 1.0

    @staticmethod
    def _record_corroboration_path(
        *,
        event: Event,
        mode: str,
        reason: str,
        rows_total: int | None = None,
        rows_parsed: int | None = None,
    ) -> None:
        record_processing_corroboration_path(mode=mode, reason=reason)
        if mode == "fallback":
            logger.info(
                "Corroboration scoring used fallback path",
                event_id=str(event.id) if event.id is not None else None,
                reason=reason,
                rows_total=rows_total,
                rows_parsed=rows_parsed,
            )

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

    _trend_identifier = staticmethod(trend_runtime_id_for_record)
    _index_trends_by_runtime_id = classmethod(
        lambda _cls, trends: index_trends_by_runtime_id(trends)
    )
    _resolve_indicator_weight = staticmethod(resolve_indicator_weight)
    _resolve_indicator_decay_half_life = staticmethod(resolve_indicator_decay_half_life)
    _event_age_days = staticmethod(event_age_days)

    @staticmethod
    def _parse_trend_impact(payload: Any) -> dict[str, Any] | None:
        parsed = parse_trend_impact(payload)
        if parsed is None:
            return None
        return {
            "trend_id": parsed.trend_id,
            "signal_type": parsed.signal_type,
            "direction": parsed.direction,
            "severity": parsed.severity,
            "confidence": parsed.confidence,
            "rationale": parsed.rationale,
        }

    @staticmethod
    def _impact_reasoning(impact: dict[str, Any]) -> str:
        parsed = parse_trend_impact(impact)
        if parsed is not None:
            return impact_reasoning(parsed)
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
        degraded_llm_hold: bool = False,
        replay_enqueued: bool = False,
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
            degraded_llm_hold=degraded_llm_hold,
            replay_enqueued=replay_enqueued,
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
            "degraded_llm": bool(result.degraded_llm),
            "degraded_holds": result.degraded_holds,
            "replay_enqueued": result.replay_enqueued,
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
