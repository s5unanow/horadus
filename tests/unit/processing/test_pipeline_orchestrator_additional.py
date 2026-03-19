from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

import src.processing.pipeline_orchestrator as orchestrator_module
from src.core.trend_engine import prob_to_logodds
from src.processing.cost_tracker import BudgetExceededError
from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_orchestrator import (
    PipelineRunResult,
    PipelineUsage,
    ProcessingPipeline,
    _PreparedItem,
)
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Usage
from src.processing.trend_impact_mapping import TREND_IMPACT_MAPPING_KEY
from src.storage.models import Event, ProcessingStatus, RawItem, TaxonomyGapReason

pytestmark = pytest.mark.unit


def _item(*, language: str | None = None) -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"ext-{uuid4()}",
        url=f"https://example.test/{uuid4()}",
        title="title",
        raw_content="content",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
        language=language,
    )


def _trend(
    *,
    trend_id=None,
    signal_type: str = "military_movement",
    weight=0.04,
    trend_half_life: object | None = 30,
):
    return SimpleNamespace(
        id=trend_id if trend_id is not None else uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        current_log_odds=0.0,
        decay_half_life_days=trend_half_life,
        definition={"id": "eu-russia"},
        indicators={signal_type: {"weight": weight, "decay_half_life_days": 7}},
    )


def _pipeline(mock_db_session, **kwargs) -> ProcessingPipeline:
    return ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=kwargs.pop(
            "deduplication_service",
            SimpleNamespace(
                find_duplicate=AsyncMock(return_value=SimpleNamespace(is_duplicate=False))
            ),
        ),
        embedding_service=kwargs.pop(
            "embedding_service",
            SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1]], 0, 1))),
        ),
        event_clusterer=kwargs.pop(
            "event_clusterer",
            SimpleNamespace(
                cluster_item=AsyncMock(
                    return_value=ClusterResult(
                        item_id=uuid4(), event_id=uuid4(), created=True, merged=False
                    )
                )
            ),
        ),
        tier1_classifier=kwargs.pop(
            "tier1_classifier",
            SimpleNamespace(
                classify_items=AsyncMock(
                    return_value=(
                        [
                            Tier1ItemResult(
                                item_id=uuid4(), max_relevance=8, should_queue_tier2=True
                            )
                        ],
                        Tier1Usage(api_calls=1),
                    )
                )
            ),
        ),
        tier2_classifier=kwargs.pop(
            "tier2_classifier",
            SimpleNamespace(
                classify_event=AsyncMock(
                    return_value=(
                        SimpleNamespace(
                            event_id=uuid4(), categories_count=0, trend_impacts_count=0
                        ),
                        Tier2Usage(api_calls=1),
                    )
                )
            ),
        ),
        trend_engine=kwargs.pop("trend_engine", SimpleNamespace(apply_evidence=AsyncMock())),
        degraded_llm_tracker=kwargs.pop("degraded_llm_tracker", None),
    )


@pytest.mark.asyncio
async def test_process_pending_and_process_items_cover_empty_and_missing_result_paths(
    mock_db_session,
) -> None:
    pipeline = _pipeline(mock_db_session)
    pipeline._load_pending_items = AsyncMock(return_value=[])
    assert (await pipeline.process_pending_items(limit=5)).scanned == 0
    assert (await pipeline.process_items([], trends=[_trend()])).scanned == 0

    pipeline._load_active_trends = AsyncMock(return_value=[])
    with pytest.raises(ValueError, match="No active trends"):
        await pipeline.process_items([_item()], trends=None)

    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    pipeline._load_active_trends = AsyncMock(return_value=[_trend()])
    pipeline._prepare_item_for_tier1 = AsyncMock(
        return_value=(prepared, SimpleNamespace(usage=PipelineUsage(embedding_api_calls=1)))
    )
    pipeline._classify_tier1_prepared_items = AsyncMock(return_value=({}, {}, PipelineUsage()))

    result = await pipeline.process_items([item], trends=None)
    assert result.errors == 1
    assert item.processing_status == ProcessingStatus.ERROR
    assert result.usage.embedding_api_calls == 1


@pytest.mark.asyncio
async def test_process_items_marks_missing_execution_as_error(mock_db_session) -> None:
    item = _item()
    pipeline = _pipeline(mock_db_session)
    pipeline._prepare_item_for_tier1 = AsyncMock(return_value=(None, None))

    result = await pipeline.process_items([item], trends=[_trend()])

    assert result.errors == 1
    assert result.results[0].error_message == "Pipeline execution result missing"


@pytest.mark.asyncio
async def test_process_items_rejects_duplicate_active_runtime_trend_ids(mock_db_session) -> None:
    pipeline = _pipeline(mock_db_session)

    duplicate_a = SimpleNamespace(
        id=uuid4(),
        name="Trend A",
        runtime_trend_id="duplicate-runtime-id",
        definition={"id": "duplicate-runtime-id"},
        indicators={},
    )
    duplicate_b = SimpleNamespace(
        id=uuid4(),
        name="Trend B",
        runtime_trend_id="duplicate-runtime-id",
        definition={"id": "duplicate-runtime-id"},
        indicators={},
    )

    with pytest.raises(
        ValueError, match="Duplicate active runtime_trend_id 'duplicate-runtime-id'"
    ):
        await pipeline.process_items([_item()], trends=[duplicate_a, duplicate_b])


def test_pipeline_usage_and_result_counter_helpers_cover_pending_and_flags() -> None:
    run_result = PipelineRunResult()
    ProcessingPipeline._accumulate_usage(
        run_result=run_result,
        usage=PipelineUsage(
            embedding_api_calls=1,
            embedding_estimated_cost_usd=0.1,
            tier1_prompt_tokens=2,
            tier1_completion_tokens=3,
            tier1_api_calls=4,
            tier1_estimated_cost_usd=0.2,
            tier2_prompt_tokens=5,
            tier2_completion_tokens=6,
            tier2_api_calls=7,
            tier2_estimated_cost_usd=0.3,
        ),
    )
    assert run_result.usage.tier2_estimated_cost_usd == pytest.approx(0.3)

    pending = SimpleNamespace(result=SimpleNamespace(final_status=ProcessingStatus.PENDING))
    ProcessingPipeline._accumulate_result_counters(run_result=run_result, execution=pending)
    assert run_result.processed == 0

    classified = SimpleNamespace(
        result=SimpleNamespace(
            final_status=ProcessingStatus.CLASSIFIED,
            duplicate=True,
            embedded=True,
            event_created=True,
            event_merged=True,
            degraded_llm_hold=True,
            replay_enqueued=True,
            trend_impacts_seen=2,
            trend_updates=1,
        )
    )
    ProcessingPipeline._accumulate_result_counters(run_result=run_result, execution=classified)
    assert run_result.processed == 1
    assert run_result.degraded_llm is True
    assert run_result.replay_enqueued == 1


@pytest.mark.asyncio
async def test_prepare_item_for_tier1_covers_empty_budget_and_exception_paths(
    mock_db_session,
) -> None:
    item = _item()
    item.raw_content = "   "
    pipeline = _pipeline(mock_db_session)

    prepared, execution = await pipeline._prepare_item_for_tier1(item=item)
    assert prepared is None
    assert execution is not None
    assert item.processing_status == ProcessingStatus.ERROR

    item_budget = _item()
    pipeline.deduplication_service.find_duplicate = AsyncMock(
        side_effect=BudgetExceededError("cap")
    )
    prepared, execution = await pipeline._prepare_item_for_tier1(item=item_budget)
    assert prepared is None
    assert execution is not None
    assert execution.result.final_status == ProcessingStatus.PENDING

    item_exc = _item()
    pipeline.deduplication_service.find_duplicate = AsyncMock(side_effect=RuntimeError("boom"))
    prepared, execution = await pipeline._prepare_item_for_tier1(item=item_exc)
    assert prepared is None
    assert execution is not None
    assert execution.result.final_status == ProcessingStatus.ERROR


@pytest.mark.asyncio
async def test_classify_tier1_prepared_items_covers_per_item_budget_and_error_paths(
    mock_db_session,
) -> None:
    item_one = _item()
    item_two = _item()
    prepared_items = [
        _PreparedItem(item=item_one, item_id=item_one.id, raw_content=item_one.raw_content),
        _PreparedItem(item=item_two, item_id=item_two.id, raw_content=item_two.raw_content),
    ]
    tier1 = SimpleNamespace(classify_items=AsyncMock(side_effect=RuntimeError("batch failed")))
    pipeline = _pipeline(mock_db_session, tier1_classifier=tier1)

    async def fake_single(*, item, trends):
        _ = trends
        if item.id == item_one.id:
            raise BudgetExceededError("budget")
        raise RuntimeError("bad item")

    pipeline._classify_tier1 = AsyncMock(side_effect=fake_single)

    _, failed, _ = await pipeline._classify_tier1_prepared_items(
        prepared_items=prepared_items,
        trends=[_trend()],
    )

    assert failed[item_one.id].result.final_status == ProcessingStatus.PENDING
    assert failed[item_two.id].result.final_status == ProcessingStatus.ERROR


@pytest.mark.asyncio
async def test_process_after_tier1_covers_existing_embedding_degraded_hold_budget_and_error_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item(language="uk")
    item.embedding = [0.1]
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="summary",
        extracted_claims={"trend_impacts": [{"trend_id": "eu-russia"}]},
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )
    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(
            classify_event=AsyncMock(
                return_value=(
                    SimpleNamespace(event_id=event.id),
                    Tier2Usage(api_calls=1, active_provider="openai", active_model="gpt"),
                )
            )
        ),
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=True)
    pipeline._apply_trend_impacts = AsyncMock(return_value=(5, 0))
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=False, merged=True)
    )
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )
    assert execution.result.degraded_llm_hold is True
    assert execution.result.replay_enqueued is True
    assert execution.result.tier2_applied is False
    pipeline._apply_trend_impacts.assert_not_called()

    healthy_item = _item()
    healthy_prepared = _PreparedItem(
        item=healthy_item,
        item_id=healthy_item.id,
        raw_content=healthy_item.raw_content,
    )
    healthy_event = Event(id=uuid4(), canonical_summary="summary", extracted_claims="bad")
    healthy_tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=False,
                availability_degraded=False,
                quality_degraded=False,
                degraded_since_epoch=None,
                window=SimpleNamespace(total_calls=1, secondary_calls=0, failover_ratio=0.0),
            )
        ),
    )
    pipeline_healthy = _pipeline(
        mock_db_session,
        degraded_llm_tracker=healthy_tracker,
        tier2_classifier=SimpleNamespace(
            classify_event=AsyncMock(
                return_value=(SimpleNamespace(event_id=healthy_event.id), Tier2Usage(api_calls=0))
            )
        ),
    )
    pipeline_healthy.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(
            item_id=healthy_item.id,
            event_id=healthy_event.id,
            created=True,
            merged=False,
        )
    )
    pipeline_healthy._load_event = AsyncMock(return_value=healthy_event)
    pipeline_healthy._apply_trend_impacts = AsyncMock(return_value=(1, 1))
    healthy_execution = await pipeline_healthy._process_after_tier1(
        prepared=healthy_prepared,
        tier1_result=Tier1ItemResult(
            item_id=healthy_item.id,
            max_relevance=8,
            should_queue_tier2=True,
        ),
        trends=[_trend()],
    )
    assert healthy_execution.result.tier2_applied is True
    healthy_tracker.record_invocation.assert_not_called()

    degraded_nonlist_item = _item()
    degraded_nonlist_prepared = _PreparedItem(
        item=degraded_nonlist_item,
        item_id=degraded_nonlist_item.id,
        raw_content=degraded_nonlist_item.raw_content,
    )
    degraded_nonlist_event = Event(
        id=uuid4(),
        canonical_summary="summary",
        extracted_claims={"trend_impacts": "bad"},
    )
    pipeline_nonlist = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(
            classify_event=AsyncMock(
                return_value=(
                    SimpleNamespace(event_id=degraded_nonlist_event.id),
                    Tier2Usage(api_calls=1),
                )
            )
        ),
    )
    pipeline_nonlist.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(
            item_id=degraded_nonlist_item.id,
            event_id=degraded_nonlist_event.id,
            created=True,
            merged=False,
        )
    )
    pipeline_nonlist._load_event = AsyncMock(return_value=degraded_nonlist_event)
    pipeline_nonlist._maybe_enqueue_replay = AsyncMock(return_value=False)
    pipeline_nonlist._apply_trend_impacts = AsyncMock(return_value=(9, 9))
    execution_nonlist = await pipeline_nonlist._process_after_tier1(
        prepared=degraded_nonlist_prepared,
        tier1_result=Tier1ItemResult(
            item_id=degraded_nonlist_item.id,
            max_relevance=8,
            should_queue_tier2=True,
        ),
        trends=[_trend()],
    )
    assert execution_nonlist.result.trend_impacts_seen == 0

    pending_item = _item()
    pending_prepared = _PreparedItem(
        item=pending_item, item_id=pending_item.id, raw_content=pending_item.raw_content
    )
    pipeline_budget = _pipeline(mock_db_session)
    pipeline_budget.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(
            item_id=pending_item.id, event_id=uuid4(), created=True, merged=False
        )
    )
    pipeline_budget._load_event = AsyncMock(
        return_value=Event(id=uuid4(), canonical_summary="summary")
    )
    pipeline_budget.tier2_classifier.classify_event = AsyncMock(
        side_effect=BudgetExceededError("tier2")
    )
    pending_execution = await pipeline_budget._process_after_tier1(
        prepared=pending_prepared,
        tier1_result=Tier1ItemResult(
            item_id=pending_item.id, max_relevance=8, should_queue_tier2=True
        ),
        trends=[_trend()],
    )
    assert pending_execution.result.final_status == ProcessingStatus.PENDING

    error_item = _item()
    error_prepared = _PreparedItem(
        item=error_item, item_id=error_item.id, raw_content=error_item.raw_content
    )
    pipeline_error = _pipeline(mock_db_session)
    pipeline_error.event_clusterer.cluster_item = AsyncMock(side_effect=RuntimeError("boom"))
    error_execution = await pipeline_error._process_after_tier1(
        prepared=error_prepared,
        tier1_result=Tier1ItemResult(
            item_id=error_item.id, max_relevance=8, should_queue_tier2=True
        ),
        trends=[_trend()],
    )
    assert error_execution.result.final_status == ProcessingStatus.ERROR


@pytest.mark.asyncio
async def test_pipeline_query_and_language_helpers_cover_remaining_paths(mock_db_session) -> None:
    pipeline = _pipeline(mock_db_session)
    item = _item()
    pipeline.tier1_classifier.classify_items = AsyncMock(return_value=([], Tier1Usage()))
    with pytest.raises(ValueError, match="exactly one result"):
        await pipeline._classify_tier1(item=item, trends=[_trend()])

    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [item])
    pending_items = await pipeline._load_pending_items(limit=5)
    active_trends = await pipeline._load_active_trends()
    assert pending_items == [item]
    assert active_trends == [item]
    assert ProcessingPipeline._normalize_language_code(" ") is None
    assert ProcessingPipeline._normalize_language_code("english") == "en"
    assert ProcessingPipeline._normalize_language_code("x") == "x"
    assert ProcessingPipeline._normalize_language_code(" EN ") == "en"
    assert ProcessingPipeline._normalize_language_code("bad-code") == "ba"
    assert ProcessingPipeline._language_metric_label(None) == "unknown"
    assert ProcessingPipeline._is_unsupported_language("fr") is True


@pytest.mark.asyncio
async def test_event_and_trend_helper_methods_cover_remaining_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _pipeline(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="summary", source_count=2, unique_source_count=1)
    mock_db_session.scalar = AsyncMock(side_effect=[event, 1, None, "bad", "invalidate"])
    assert await pipeline._load_event(event.id) is event
    assert await pipeline._event_suppression_action(event_id=event.id) is None
    assert await pipeline._event_suppression_action(event_id=event.id) is None
    assert await pipeline._event_suppression_action(event_id=event.id) is None
    assert await pipeline._event_suppression_action(event_id=event.id) == "invalidate"

    with pytest.raises(ValueError, match="Event must have an id"):
        await pipeline._apply_trend_impacts(event=Event(id=None), trends=[_trend()])

    assert await pipeline._apply_trend_impacts(
        event=Event(id=uuid4(), extracted_claims={}), trends=[_trend()]
    ) == (0, 0)
    assert await pipeline._apply_trend_impacts(
        event=Event(id=uuid4(), extracted_claims={"trend_impacts": ["bad"]}),
        trends=[_trend()],
    ) == (0, 0)

    trend_no_id = _trend(trend_id=None)
    trend_no_id.id = None
    event.extracted_claims = {
        "trend_impacts": [
            {
                "trend_id": "eu-russia",
                "signal_type": "military_movement",
                "direction": "escalatory",
                "severity": 0.5,
                "confidence": 0.5,
            },
            {
                "trend_id": "unknown",
                "signal_type": "military_movement",
                "direction": "escalatory",
                "severity": 0.5,
                "confidence": 0.5,
            },
            {
                "trend_id": "eu-russia",
                "signal_type": "unknown",
                "direction": "escalatory",
                "severity": 0.5,
                "confidence": 0.5,
            },
        ]
    }
    pipeline._load_event_source_credibility = AsyncMock(return_value=0.5)
    pipeline._corroboration_score = AsyncMock(return_value=1.0)
    pipeline._capture_taxonomy_gap = AsyncMock(return_value=None)
    pipeline._novelty_score = AsyncMock(return_value=1.0)
    pipeline.trend_engine.apply_evidence = AsyncMock(
        return_value=SimpleNamespace(delta_applied=0.0)
    )
    seen, updates = await pipeline._apply_trend_impacts(event=event, trends=[trend_no_id])
    assert seen == 3
    assert updates == 0

    valid_trend = _trend()
    multi_event = Event(
        id=uuid4(),
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.5,
                    "confidence": 0.5,
                },
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.6,
                    "confidence": 0.6,
                },
            ]
        },
    )
    pipeline._load_event_source_credibility = AsyncMock(return_value=0.5)
    pipeline._corroboration_score = AsyncMock(return_value=1.0)
    pipeline._novelty_score = AsyncMock(return_value=1.0)
    pipeline.trend_engine.apply_evidence = AsyncMock(
        side_effect=[SimpleNamespace(delta_applied=0.0), SimpleNamespace(delta_applied=0.1)]
    )
    seen, updates = await pipeline._apply_trend_impacts(event=multi_event, trends=[valid_trend])
    assert seen == 2
    assert updates == 0

    monkeypatch.setattr(orchestrator_module.settings, "LLM_DEGRADED_REPLAY_ENABLED", False)
    assert (
        await pipeline._maybe_enqueue_replay(
            event=event,
            trends=[_trend()],
            degraded_status=SimpleNamespace(
                window=SimpleNamespace(total_calls=1, secondary_calls=0, failover_ratio=0.0),
                degraded_since_epoch=1,
            ),
            tier2_usage=SimpleNamespace(),
        )
        is False
    )

    monkeypatch.setattr(orchestrator_module.settings, "LLM_DEGRADED_REPLAY_ENABLED", True)
    assert (
        await pipeline._maybe_enqueue_replay(
            event=Event(id=None),
            trends=[_trend()],
            degraded_status=SimpleNamespace(
                window=SimpleNamespace(total_calls=1, secondary_calls=0, failover_ratio=0.0),
                degraded_since_epoch=1,
            ),
            tier2_usage=SimpleNamespace(),
        )
        is False
    )


@pytest.mark.asyncio
async def test_capture_unresolved_trend_mapping_records_taxonomy_gaps(mock_db_session) -> None:
    pipeline = _pipeline(mock_db_session)
    pipeline._capture_taxonomy_gap = AsyncMock(return_value=None)
    event = Event(
        id=uuid4(),
        extracted_claims={
            TREND_IMPACT_MAPPING_KEY: {
                "unresolved": [
                    {
                        "reason": "ambiguous_mapping",
                        "trend_id": "__ambiguous__",
                        "signal_type": "__ambiguous__",
                        "event_claim_key": "claim-key",
                        "event_claim_text": "Claim text",
                        "details": {"candidate_count": 2},
                    }
                ]
            }
        },
    )

    await pipeline._capture_unresolved_trend_mapping(event=event)

    pipeline._capture_taxonomy_gap.assert_awaited_once()
    assert (
        pipeline._capture_taxonomy_gap.await_args.kwargs["reason"]
        == TaxonomyGapReason.AMBIGUOUS_MAPPING
    )


@pytest.mark.asyncio
async def test_replay_and_impact_helpers_cover_queue_and_prediction_logic(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _pipeline(mock_db_session)
    event = Event(
        id=uuid4(),
        canonical_summary="summary",
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.9,
                    "confidence": 0.9,
                }
            ]
        },
    )
    trend = _trend()
    monkeypatch.setattr(orchestrator_module.settings, "LLM_DEGRADED_REPLAY_MIN_ABS_DELTA", 0.0001)
    pipeline._load_event_source_credibility = AsyncMock(return_value=0.9)
    pipeline._corroboration_score = AsyncMock(return_value=2.0)
    pipeline._novelty_score = AsyncMock(return_value=1.0)

    high_impact, max_abs_delta, risk_crossing = await pipeline._is_high_impact_event(
        event=event,
        trends=[trend],
    )
    assert high_impact is True
    assert max_abs_delta > 0.0
    assert isinstance(risk_crossing, bool)

    crossing_trend = _trend()
    crossing_trend.current_log_odds = prob_to_logodds(0.24)
    monkeypatch.setattr(
        orchestrator_module,
        "calculate_evidence_delta",
        lambda **_kwargs: (1.0, SimpleNamespace()),
    )
    high_impact, _max_abs_delta, risk_crossing = await pipeline._is_high_impact_event(
        event=event,
        trends=[crossing_trend],
    )
    assert high_impact is True
    assert risk_crossing is True

    assert await pipeline._is_high_impact_event(
        event=Event(extracted_claims={}), trends=[trend]
    ) == (
        False,
        0.0,
        False,
    )
    assert await pipeline._is_high_impact_event(
        event=Event(
            extracted_claims={
                "trend_impacts": [
                    "bad",
                    {
                        "trend_id": "missing",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.5,
                        "confidence": 0.5,
                    },
                    {
                        "trend_id": "eu-russia",
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.5,
                        "confidence": 0.5,
                    },
                ]
            }
        ),
        trends=[_trend(weight=None)],
    ) == (False, 0.0, False)

    monkeypatch.setattr(orchestrator_module.settings, "LLM_DEGRADED_REPLAY_MIN_ABS_DELTA", 10.0)
    low_impact_event = Event(
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.1,
                    "confidence": 0.1,
                },
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.05,
                    "confidence": 0.05,
                },
            ]
        },
    )
    high_impact, max_abs_delta, risk_crossing = await pipeline._is_high_impact_event(
        event=low_impact_event,
        trends=[trend],
    )
    assert high_impact is False
    assert max_abs_delta > 0.0
    assert risk_crossing is False

    pipeline._is_high_impact_event = AsyncMock(return_value=(False, 0.0, False))
    assert (
        await pipeline._maybe_enqueue_replay(
            event=event,
            trends=[trend],
            degraded_status=SimpleNamespace(
                degraded_since_epoch=123,
                window=SimpleNamespace(total_calls=4, secondary_calls=2, failover_ratio=0.5),
            ),
            tier2_usage=SimpleNamespace(),
        )
        is False
    )

    pipeline._is_high_impact_event = AsyncMock(return_value=(True, 0.8, True))
    mock_db_session.scalar = AsyncMock(return_value=9999)
    monkeypatch.setattr(orchestrator_module.settings, "LLM_DEGRADED_REPLAY_MAX_QUEUE", 1)
    assert (
        await pipeline._maybe_enqueue_replay(
            event=event,
            trends=[trend],
            degraded_status=SimpleNamespace(
                degraded_since_epoch=123,
                window=SimpleNamespace(total_calls=4, secondary_calls=2, failover_ratio=0.5),
            ),
            tier2_usage=SimpleNamespace(
                active_provider="openai",
                active_model="gpt",
                active_reasoning_effort="low",
                used_secondary_route=True,
            ),
        )
        is False
    )

    mock_db_session.scalar = AsyncMock(return_value=0)
    mock_db_session.begin_nested = MagicMock()

    class _Begin:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    mock_db_session.begin_nested.return_value = _Begin()
    assert (
        await pipeline._maybe_enqueue_replay(
            event=event,
            trends=[trend],
            degraded_status=SimpleNamespace(
                degraded_since_epoch=123,
                window=SimpleNamespace(total_calls=4, secondary_calls=2, failover_ratio=0.5),
            ),
            tier2_usage=SimpleNamespace(
                active_provider="openai",
                active_model="gpt",
                active_reasoning_effort="low",
                used_secondary_route=True,
            ),
        )
        is True
    )

    class _FailingBegin:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            raise IntegrityError("insert", {}, Exception("duplicate"))

    mock_db_session.begin_nested.return_value = _FailingBegin()
    assert (
        await pipeline._maybe_enqueue_replay(
            event=event,
            trends=[trend],
            degraded_status=SimpleNamespace(
                degraded_since_epoch=123,
                window=SimpleNamespace(total_calls=4, secondary_calls=2, failover_ratio=0.5),
            ),
            tier2_usage=SimpleNamespace(
                active_provider="openai",
                active_model="gpt",
                active_reasoning_effort="low",
                used_secondary_route=True,
            ),
        )
        is False
    )


@pytest.mark.asyncio
async def test_pipeline_domain_helpers_cover_fallbacks_and_parsers(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _pipeline(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="summary", source_count=2, unique_source_count=1)
    assert await pipeline._load_event_source_credibility(
        Event(primary_item_id=None)
    ) == pytest.approx(0.5)
    mock_db_session.scalar = AsyncMock(side_effect=["bad", datetime.now(tz=UTC)])
    assert await pipeline._load_event_source_credibility(
        Event(primary_item_id=uuid4())
    ) == pytest.approx(0.5)
    assert (
        await pipeline._novelty_score(trend_id=uuid4(), signal_type="sig", event_id=uuid4()) <= 1.0
    )

    pipeline._record_corroboration_path = MagicMock()
    assert (
        await pipeline._corroboration_score(Event(id=None, source_count=2, unique_source_count=1))
        >= 0.1
    )

    mock_db_session.execute = AsyncMock(side_effect=RuntimeError("db"))
    assert await pipeline._corroboration_score(event) >= 0.1

    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=list))
    assert await pipeline._corroboration_score(event) >= 0.1

    row_mapping = SimpleNamespace(
        _mapping={"source_id": "src-1", "source_tier": "official", "reporting_type": "secondary"}
    )
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [row_mapping]))
    assert await pipeline._corroboration_score(event) >= 0.1

    assert ProcessingPipeline._fallback_corroboration_score(Event(unique_source_count=2)) == 2.0
    assert ProcessingPipeline._fallback_corroboration_score(Event(source_count=3)) == 3.0
    assert ProcessingPipeline._fallback_corroboration_score(Event()) == 1.0
    assert (
        ProcessingPipeline._source_cluster_key(
            source_id="a", source_tier="official", reporting_type="firsthand"
        )
        == "firsthand:a"
    )
    assert (
        ProcessingPipeline._source_cluster_key(
            source_id="a", source_tier="official", reporting_type="secondary"
        )
        == "official:secondary"
    )
    assert ProcessingPipeline._parse_corroboration_row((None, "a", "b")) is None
    assert ProcessingPipeline._parse_corroboration_row((1, 2, 3)) == (1, "2", "3")
    assert ProcessingPipeline._parse_corroboration_row(SimpleNamespace(_mapping={"id": "x"})) == (
        "x",
        None,
        None,
    )
    assert ProcessingPipeline._parse_corroboration_row(object()) is None
    ProcessingPipeline._record_corroboration_path(event=event, mode="cluster_aware", reason="ok")
    assert ProcessingPipeline._reporting_type_weight("firsthand") == pytest.approx(1.0)
    assert ProcessingPipeline._reporting_type_weight("secondary") == pytest.approx(0.6)
    assert ProcessingPipeline._reporting_type_weight("aggregator") == pytest.approx(0.35)
    assert ProcessingPipeline._reporting_type_weight("other") == pytest.approx(0.5)

    contradiction_event = Event(
        extracted_claims={
            "claim_graph": {"links": [{"relation": "contradict"}, {"relation": "contradict"}]}
        },
        has_contradictions=True,
    )
    assert ProcessingPipeline._contradiction_penalty(contradiction_event) == pytest.approx(0.7)
    assert ProcessingPipeline._contradiction_penalty(
        Event(extracted_claims={"claim_graph": {"links": "bad"}})
    ) == pytest.approx(1.0)
    assert ProcessingPipeline._contradiction_penalty(
        Event(has_contradictions=True)
    ) == pytest.approx(0.7)
    assert (
        ProcessingPipeline._resolve_indicator_weight(
            trend=SimpleNamespace(indicators={"military_movement": {}}),
            signal_type="military_movement",
        )
        is None
    )
    assert (
        ProcessingPipeline._resolve_indicator_weight(
            trend=SimpleNamespace(indicators={"military_movement": {"weight": object()}}),
            signal_type="military_movement",
        )
        is None
    )
    assert (
        ProcessingPipeline._resolve_indicator_weight(
            trend=_trend(weight="bad"), signal_type="military_movement"
        )
        is None
    )
    assert (
        ProcessingPipeline._resolve_indicator_weight(
            trend=_trend(weight=0), signal_type="military_movement"
        )
        is None
    )
    assert (
        ProcessingPipeline._resolve_indicator_decay_half_life(
            trend=_trend(trend_half_life="bad"), signal_type="military_movement"
        )
        == 7.0
    )
    trend_decay = _trend()
    trend_decay.indicators["military_movement"]["decay_half_life_days"] = "bad"
    assert (
        ProcessingPipeline._resolve_indicator_decay_half_life(
            trend=trend_decay, signal_type="military_movement"
        )
        == 30.0
    )
    no_trend_decay = _trend(trend_half_life="bad")
    no_trend_decay.indicators["military_movement"] = {}
    assert (
        ProcessingPipeline._resolve_indicator_decay_half_life(
            trend=no_trend_decay, signal_type="military_movement"
        )
        is None
    )
    assert (
        ProcessingPipeline._resolve_indicator_decay_half_life(
            trend=SimpleNamespace(indicators={"military_movement": "bad"}, decay_half_life_days=5),
            signal_type="military_movement",
        )
        == 5.0
    )
    assert (
        ProcessingPipeline._resolve_indicator_decay_half_life(
            trend=SimpleNamespace(indicators={"military_movement": {}}, decay_half_life_days=0),
            signal_type="military_movement",
        )
        is None
    )
    assert ProcessingPipeline._event_age_days(Event()) == 0.0
    assert (
        ProcessingPipeline._event_age_days(
            Event(extracted_when=datetime.now(tz=UTC).replace(tzinfo=None))
        )
        >= 0.0
    )
    assert ProcessingPipeline._parse_trend_impact("bad") is None
    assert (
        ProcessingPipeline._parse_trend_impact(
            {"trend_id": "", "signal_type": "x", "direction": "escalatory"}
        )
        is None
    )
    assert (
        ProcessingPipeline._parse_trend_impact(
            {"trend_id": "a", "signal_type": "", "direction": "escalatory"}
        )
        is None
    )


def test_runtime_trend_identifier_helper_paths() -> None:
    assert (
        ProcessingPipeline._trend_identifier(SimpleNamespace(runtime_trend_id="runtime-id"))
        == "runtime-id"
    )
    with pytest.raises(ValueError, match="missing runtime_trend_id"):
        ProcessingPipeline._trend_identifier(SimpleNamespace(name="Missing", definition={}))
    assert (
        ProcessingPipeline._parse_trend_impact(
            {"trend_id": "a", "signal_type": "x", "direction": "bad"}
        )
        is None
    )
    assert (
        ProcessingPipeline._parse_trend_impact(
            {"trend_id": "a", "signal_type": "x", "direction": "escalatory", "severity": "bad"}
        )
        is None
    )
    parsed = ProcessingPipeline._parse_trend_impact(
        {
            "trend_id": " a ",
            "signal_type": " x ",
            "direction": "escalatory",
            "severity": 2,
            "confidence": -1,
            "rationale": " note ",
        }
    )
    assert parsed == {
        "trend_id": "a",
        "signal_type": "x",
        "direction": "escalatory",
        "severity": 1.0,
        "confidence": 0.0,
        "rationale": "note",
    }
    assert (
        ProcessingPipeline._impact_reasoning({"signal_type": "x", "direction": "escalatory"})
        == "Tier 2 classified x as escalatory"
    )
    assert (
        ProcessingPipeline._impact_reasoning(
            {"trend_id": "a", "signal_type": "x", "direction": "escalatory"}
        )
        == "Tier 2 classified x as escalatory"
    )
    assert (
        ProcessingPipeline._impact_reasoning(
            {"signal_type": "x", "direction": "escalatory", "rationale": "given"}
        )
        == "given"
    )
    with pytest.raises(ValueError, match="must have an id"):
        ProcessingPipeline._item_id(RawItem(id=None))
    cluster = ClusterResult(item_id=uuid4(), event_id=uuid4(), created=False, merged=True)
    built = ProcessingPipeline._build_item_result(
        item_id=uuid4(),
        status=ProcessingStatus.CLASSIFIED,
        cluster_result=cluster,
        embedded=True,
        tier2_applied=True,
        degraded_llm_hold=True,
        replay_enqueued=True,
        trend_impacts_seen=2,
        trend_updates=1,
        error_message="err",
    )
    assert built.event_merged is True
    assert built.event_created is False


@pytest.mark.asyncio
async def test_capture_taxonomy_gap_logs_and_swallows_failures(
    mock_db_session, monkeypatch
) -> None:
    pipeline = _pipeline(mock_db_session)
    monkeypatch.setattr(orchestrator_module, "record_taxonomy_gap", lambda **_: None)

    await pipeline._capture_taxonomy_gap(
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="military_movement",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        details={},
    )

    mock_db_session.flush = AsyncMock(side_effect=RuntimeError("db"))
    await pipeline._capture_taxonomy_gap(
        event_id=uuid4(),
        trend_id="eu-russia",
        signal_type="military_movement",
        reason=TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE,
        details={},
    )
