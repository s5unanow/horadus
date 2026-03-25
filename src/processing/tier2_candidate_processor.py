"""Tier-2 candidate staging, ordering, and finalization helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from inspect import signature
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import func, select

from src.core.config import settings
from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    source_multiplier_expression,
)
from src.core.trend_config import index_trends_by_runtime_id
from src.processing.cost_tracker import TIER2, BudgetExceededError, CostTracker
from src.processing.pipeline_types import (
    PipelineItemResult,
    PipelineUsage,
    _ItemExecution,
    _PreparedItem,
    _StagedTier2Candidate,
)
from src.processing.tier2_voi_scheduler import (
    Tier2TrendSignal,
    Tier2VOICandidate,
    build_tier2_voi_plan,
)
from src.storage.event_extraction import capture_canonical_extraction
from src.storage.models import ProcessingStatus, RawItem, Source, Trend

if TYPE_CHECKING:
    from src.processing.event_clusterer import ClusterResult
    from src.processing.tier1_classifier import Tier1ItemResult

logger = structlog.get_logger(__name__)


async def stage_tier2_candidate(
    *,
    owner: Any,
    prepared: _PreparedItem,
    tier1_result: Tier1ItemResult,
) -> tuple[_StagedTier2Candidate | None, _ItemExecution | None]:
    usage = PipelineUsage()
    item = prepared.item
    embedded = False
    cluster_result: ClusterResult | None = None
    try:
        if item.embedding is None:
            embedded, embedding_api_calls = await ensure_item_embedding(
                owner=owner, prepared=prepared
            )
            usage.embedding_api_calls += embedding_api_calls

        cluster_result = await owner.event_clusterer.cluster_item(item)
        event = await owner._load_event(cluster_result.event_id)
        if event is None:
            msg = f"Event {cluster_result.event_id} not found after clustering"
            raise ValueError(msg)

        suppression_action = await owner._event_suppression_action(event_id=cluster_result.event_id)
        if suppression_action is not None:
            item.processing_status = ProcessingStatus.NOISE
            item.processing_started_at = None
            await owner.session.flush()
            owner.record_processing_event_suppression(
                action=suppression_action,
                stage="pipeline_post_cluster",
            )
            logger.info(
                "Skipping event due to human feedback suppression",
                item_id=str(prepared.item_id),
                event_id=str(cluster_result.event_id),
                action=suppression_action,
            )
            return (
                None,
                _ItemExecution(
                    result=owner._build_item_result(
                        item_id=prepared.item_id,
                        status=item.processing_status,
                        cluster_result=cluster_result,
                        embedded=embedded,
                    ),
                    usage=usage,
                ),
            )
        return (
            _StagedTier2Candidate(
                prepared=prepared,
                tier1_result=tier1_result,
                cluster_result=cluster_result,
                event=event,
                embedded=embedded,
                usage=usage,
            ),
            None,
        )
    except BudgetExceededError as exc:
        return (
            None,
            await _pending_budget_execution(
                owner=owner,
                prepared=prepared,
                usage=usage,
                cluster_result=cluster_result,
                embedded=embedded,
                exc=exc,
            ),
        )
    except Exception as exc:
        return (
            None,
            await _error_execution(
                owner=owner,
                prepared=prepared,
                usage=usage,
                exc=exc,
            ),
        )


async def ensure_item_embedding(
    *,
    owner: Any,
    prepared: _PreparedItem,
) -> tuple[bool, int]:
    item = prepared.item
    embedding_audit = None
    embed_with_contexts = getattr(owner.embedding_service, "embed_texts_with_contexts", None)
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
        ) = await owner.embedding_service.embed_texts([prepared.raw_content])
    item.embedding = vectors[0]
    item.embedding_model = getattr(owner.embedding_service, "model", settings.EMBEDDING_MODEL)
    item.embedding_generated_at = datetime.now(tz=UTC)
    if embedding_audit is not None:
        item.embedding_input_tokens = embedding_audit.original_tokens
        item.embedding_retained_tokens = embedding_audit.retained_tokens
        item.embedding_was_truncated = embedding_audit.was_truncated
        item.embedding_truncation_strategy = (
            embedding_audit.strategy if embedding_audit.was_cut else None
        )
    return (True, embedding_api_calls)


async def finalize_staged_tier2_candidate(
    *,
    owner: Any,
    candidate: _StagedTier2Candidate,
    trends: list[Trend],
) -> _ItemExecution:
    usage = PipelineUsage(embedding_api_calls=candidate.usage.embedding_api_calls)
    item = candidate.prepared.item
    event = candidate.event
    try:
        tier2_usage, canonical_snapshot = await _classify_event(
            owner=owner, event=event, trends=trends, item=item
        )
        _accumulate_tier2_usage(target=usage, source=tier2_usage)
        degraded_hold, replay_enqueued = await _handle_degraded_mode(
            owner=owner,
            event=event,
            trends=trends,
            canonical_snapshot=canonical_snapshot,
            tier2_usage=tier2_usage,
        )
        trend_impacts_seen, trend_updates = await _apply_tier2_outcome(
            owner=owner,
            candidate=candidate,
            trends=trends,
            degraded_hold=degraded_hold,
            tier2_usage=tier2_usage,
        )
        item.processing_status = ProcessingStatus.CLASSIFIED
        item.processing_started_at = None
        await owner.session.flush()
        return _ItemExecution(
            result=owner._build_item_result(
                item_id=candidate.prepared.item_id,
                status=item.processing_status,
                cluster_result=candidate.cluster_result,
                embedded=candidate.embedded,
                tier2_applied=not degraded_hold,
                degraded_llm_hold=degraded_hold,
                replay_enqueued=replay_enqueued,
                trend_impacts_seen=trend_impacts_seen,
                trend_updates=trend_updates,
            ),
            usage=usage,
        )
    except BudgetExceededError as exc:
        return await _pending_budget_execution(
            owner=owner,
            prepared=candidate.prepared,
            usage=usage,
            cluster_result=candidate.cluster_result,
            embedded=candidate.embedded,
            exc=exc,
        )
    except Exception as exc:
        return await _error_execution(
            owner=owner,
            prepared=candidate.prepared,
            usage=usage,
            exc=exc,
        )


async def load_item_source_credibility(
    *,
    owner: Any,
    items: list[RawItem],
) -> dict[UUID, float]:
    source_ids = {item.source_id for item in items if item.id is not None}
    if not source_ids:
        return {}
    query = select(
        Source.id,
        (
            func.coalesce(Source.credibility_score, DEFAULT_SOURCE_CREDIBILITY)
            * source_multiplier_expression(
                source_tier_col=Source.source_tier,
                reporting_type_col=Source.reporting_type,
            )
        ).label("effective_credibility"),
    ).where(Source.id.in_(source_ids))
    execution_result = await owner.session.execute(query)
    rows = execution_result.all() if hasattr(execution_result, "all") else execution_result
    if asyncio.iscoroutine(rows):
        rows = await rows
    if not isinstance(rows, list | tuple):
        rows = []
    credibility_by_source: dict[UUID, float] = {}
    for source_id, effective_credibility in rows:
        try:
            credibility_by_source[source_id] = float(effective_credibility)
        except (TypeError, ValueError):
            credibility_by_source[source_id] = DEFAULT_SOURCE_CREDIBILITY
    return {
        item.id: credibility_by_source.get(item.source_id, DEFAULT_SOURCE_CREDIBILITY)
        for item in items
        if item.id is not None
    }


async def order_tier2_candidates(
    *,
    owner: Any,
    staged_candidates: list[_StagedTier2Candidate],
    trends: list[Trend],
    source_credibility_by_item: dict[UUID, float],
) -> list[_StagedTier2Candidate]:
    cost_tracker = getattr(owner.tier2_classifier, "cost_tracker", None)
    if not isinstance(cost_tracker, CostTracker):
        cost_tracker = CostTracker(session=owner.session)
    budget_snapshot = await cost_tracker.get_tier_budget_snapshot(TIER2)
    trend_by_runtime_id = index_trends_by_runtime_id(trends)
    voi_candidates = [
        Tier2VOICandidate(
            item_id=candidate.prepared.item_id,
            event_id=candidate.event.id,
            original_position=index,
            fetched_at=candidate.prepared.item.fetched_at,
            published_at=candidate.prepared.item.published_at,
            source_credibility=source_credibility_by_item.get(
                candidate.prepared.item_id,
                DEFAULT_SOURCE_CREDIBILITY,
            ),
            created_event=bool(candidate.cluster_result.created),
            event_first_seen_at=candidate.event.first_seen_at,
            event_source_count=max(0, int(candidate.event.source_count or 0)),
            event_unique_source_count=max(0, int(candidate.event.unique_source_count or 0)),
            event_has_contradictions=bool(candidate.event.has_contradictions),
            trend_signals=_build_tier2_trend_signals(
                tier1_result=candidate.tier1_result,
                trend_by_runtime_id=trend_by_runtime_id,
            ),
        )
        for index, candidate in enumerate(staged_candidates)
    ]
    plan = build_tier2_voi_plan(
        candidates=voi_candidates,
        budget_snapshot=budget_snapshot,
        relevance_threshold=settings.TIER1_RELEVANCE_THRESHOLD,
        low_headroom_threshold_pct=settings.PROCESSING_DISPATCH_MIN_BUDGET_HEADROOM_PCT,
    )
    if plan.pressure_reason != "not_under_pressure":
        logger.info(
            "Applied Tier-2 value-of-information scheduling",
            pressure_reason=plan.pressure_reason,
            used_fallback=plan.used_fallback,
            candidate_count=len(staged_candidates),
            ordered_candidates=[
                {
                    "item_id": str(decision.candidate.item_id),
                    "event_id": str(decision.candidate.event_id)
                    if decision.candidate.event_id is not None
                    else None,
                    "score": decision.priority_score,
                    "expected_delta": decision.expected_delta,
                    "uncertainty": decision.uncertainty,
                    "contradiction_risk": decision.contradiction_risk,
                    "novelty": decision.novelty,
                    "trend_relevance": decision.trend_relevance,
                    "fairness_age": decision.fairness_age,
                    "reserve_candidate": decision.reserve_candidate,
                    "lane": decision.applied_lane,
                    "fallback_reason": decision.fallback_reason,
                }
                for decision in plan.decisions[:12]
            ],
        )
    staged_by_item = {candidate.prepared.item_id: candidate for candidate in staged_candidates}
    ordered = [
        staged_by_item[decision.candidate.item_id]
        for decision in plan.decisions
        if decision.candidate.item_id in staged_by_item
    ]
    return ordered if len(ordered) == len(staged_candidates) else staged_candidates


def _build_tier2_trend_signals(
    *,
    tier1_result: Tier1ItemResult,
    trend_by_runtime_id: dict[str, Trend],
) -> tuple[Tier2TrendSignal, ...]:
    signals: list[Tier2TrendSignal] = []
    for score in sorted(
        tier1_result.trend_scores,
        key=lambda trend_score: trend_score.relevance_score,
        reverse=True,
    ):
        trend = trend_by_runtime_id.get(score.trend_id)
        max_indicator_weight = 0.0
        indicators = (
            trend.indicators if trend is not None and isinstance(trend.indicators, dict) else {}
        )
        for indicator in indicators.values():
            if not isinstance(indicator, dict):
                continue
            try:
                max_indicator_weight = max(
                    max_indicator_weight, float(indicator.get("weight", 0.0) or 0.0)
                )
            except (TypeError, ValueError):
                continue
        signals.append(
            Tier2TrendSignal(
                trend_id=score.trend_id,
                relevance_score=score.relevance_score,
                max_indicator_weight=max_indicator_weight,
            )
        )
    return tuple(signals)


async def _classify_event(
    *, owner: Any, event: Any, trends: list[Trend], item: RawItem
) -> tuple[Any, Any]:
    canonical_snapshot = capture_canonical_extraction(event)
    classify_kwargs: dict[str, Any] = {"event": event, "trends": trends}
    if "defer_semantic_cache_write" in signature(owner.tier2_classifier.classify_event).parameters:
        classify_kwargs["defer_semantic_cache_write"] = True
    _tier2_result, tier2_usage = await owner.tier2_classifier.classify_event(**classify_kwargs)
    owner.record_processing_tier2_language_usage(
        language=owner._language_metric_label(item.language)
    )
    return (tier2_usage, canonical_snapshot)


async def _handle_degraded_mode(
    *,
    owner: Any,
    event: Any,
    trends: list[Trend],
    canonical_snapshot: Any,
    tier2_usage: Any,
) -> tuple[bool, bool]:
    degraded_hold = False
    replay_enqueued = False
    if owner.degraded_llm_tracker is None:
        return (degraded_hold, replay_enqueued)
    if int(tier2_usage.api_calls) > 0:
        await asyncio.to_thread(
            owner.degraded_llm_tracker.record_invocation,
            used_secondary_route=bool(tier2_usage.used_secondary_route),
        )
    degraded_status = await asyncio.to_thread(owner.degraded_llm_tracker.evaluate)
    owner.set_llm_degraded_mode(
        stage=degraded_status.stage,
        is_degraded=bool(degraded_status.is_degraded),
    )
    degraded_hold = bool(degraded_status.is_degraded)
    if degraded_hold:
        replay_enqueued = await owner._hold_degraded_extraction(
            event=event,
            trends=trends,
            degraded_status=degraded_status,
            tier2_usage=tier2_usage,
            canonical_snapshot=canonical_snapshot,
        )
    return (degraded_hold, replay_enqueued)


async def _apply_tier2_outcome(
    *,
    owner: Any,
    candidate: _StagedTier2Candidate,
    trends: list[Trend],
    degraded_hold: bool,
    tier2_usage: Any,
) -> tuple[int, int]:
    event = candidate.event
    if degraded_hold:
        claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        impacts_payload = claims.get("trend_impacts", [])
        return (len(impacts_payload) if isinstance(impacts_payload, list) else 0, 0)

    await owner._persist_deferred_tier2_cache_write(tier2_usage=tier2_usage)
    await owner._capture_unresolved_trend_mapping(event=event)
    trend_impacts_seen, trend_updates = await owner._apply_trend_impacts(event=event, trends=trends)
    if trend_updates <= 0:
        await owner._capture_event_novelty_candidate(
            event=event,
            item=candidate.prepared.item,
            tier1_result=candidate.tier1_result,
            trend_impacts_seen=trend_impacts_seen,
            trend_updates=trend_updates,
        )
    return (trend_impacts_seen, trend_updates)


async def _pending_budget_execution(
    *,
    owner: Any,
    prepared: _PreparedItem,
    usage: PipelineUsage,
    cluster_result: ClusterResult | None,
    embedded: bool,
    exc: Exception,
) -> _ItemExecution:
    item = prepared.item
    item.processing_status = ProcessingStatus.PENDING
    item.processing_started_at = None
    item.error_message = None
    await owner.session.flush()
    logger.warning(
        "Budget exceeded; leaving item pending for retry",
        item_id=str(prepared.item_id),
        reason=str(exc),
    )
    return _ItemExecution(
        result=owner._build_item_result(
            item_id=prepared.item_id,
            status=item.processing_status,
            cluster_result=cluster_result,
            embedded=embedded,
            error_message=str(exc),
        ),
        usage=usage,
    )


async def _error_execution(
    *,
    owner: Any,
    prepared: _PreparedItem,
    usage: PipelineUsage,
    exc: Exception,
) -> _ItemExecution:
    item = prepared.item
    owner._raise_retryable_failure_if_needed(item=item, stage="post_tier1", exc=exc)
    item.processing_status = ProcessingStatus.ERROR
    item.processing_started_at = None
    item.error_message = str(exc)[:1000]
    await owner.session.flush()
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


def _accumulate_tier2_usage(*, target: PipelineUsage, source: Any) -> None:
    target.tier2_prompt_tokens += source.prompt_tokens
    target.tier2_completion_tokens += source.completion_tokens
    target.tier2_api_calls += source.api_calls
    target.tier2_estimated_cost_usd += source.estimated_cost_usd
