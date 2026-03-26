from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.processing.pipeline_orchestrator as orchestrator_module
from src.processing.cost_tracker import CostTracker, TierBudgetSnapshot
from src.processing.deduplication_service import DeduplicationResult
from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage, TrendRelevanceScore
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage
from src.storage.models import Event, ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _build_item_with_title(title: str) -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"external-{uuid4()}",
        url=f"https://example.test/{uuid4()}",
        title=title,
        raw_content="Troops moved near the border",
        content_hash="abc123",
        fetched_at=datetime.now(tz=UTC),
    )


def _build_trend_with_runtime_id(runtime_id: str, *, weight: float) -> object:
    return SimpleNamespace(
        id=uuid4(),
        name=runtime_id,
        runtime_trend_id=runtime_id,
        definition={"id": runtime_id},
        indicators={
            "military_movement": {
                "weight": weight,
                "direction": "escalatory",
                "keywords": ["troops"],
            }
        },
    )


def _tier2_budget_snapshot(*, remaining_calls: int | None, headroom_ratio: float = 0.05):
    return TierBudgetSnapshot(
        tier="tier2",
        calls_used=4,
        call_limit=5,
        remaining_calls=remaining_calls,
        cost_usd=1.0,
        average_cost_per_call_usd=0.25,
        budget_remaining_usd=0.5,
        daily_cost_limit_usd=2.0,
        headroom_ratio=headroom_ratio,
        estimated_remaining_calls_from_budget=2,
    )


def _build_basic_pipeline(mock_db_session) -> ProcessingPipeline:
    return ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=SimpleNamespace(
            find_duplicate=AsyncMock(return_value=DeduplicationResult(False))
        ),
        embedding_service=SimpleNamespace(
            embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1))
        ),
        event_clusterer=SimpleNamespace(cluster_item=AsyncMock()),
        tier1_classifier=SimpleNamespace(classify_items=AsyncMock()),
        tier2_classifier=SimpleNamespace(classify_event=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_process_items_reorders_tier2_calls_by_voi_under_budget_pressure(
    mock_db_session,
) -> None:
    item_low = _build_item_with_title("Low urgency item")
    item_high = _build_item_with_title("High urgency item")
    event_low = Event(
        id=uuid4(), canonical_summary="Low event", source_count=4, unique_source_count=4
    )
    event_high = Event(
        id=uuid4(),
        canonical_summary="High event",
        source_count=1,
        unique_source_count=1,
        has_contradictions=True,
    )

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            side_effect=[
                ClusterResult(
                    item_id=item_low.id, event_id=event_low.id, created=False, merged=True
                ),
                ClusterResult(
                    item_id=item_high.id, event_id=event_high.id, created=True, merged=False
                ),
            ]
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [
                    Tier1ItemResult(
                        item_id=item_low.id,
                        max_relevance=6,
                        should_queue_tier2=True,
                        trend_scores=[TrendRelevanceScore("trend-low", 6)],
                    ),
                    Tier1ItemResult(
                        item_id=item_high.id,
                        max_relevance=9,
                        should_queue_tier2=True,
                        trend_scores=[
                            TrendRelevanceScore("trend-high", 9),
                            TrendRelevanceScore("trend-low", 8),
                        ],
                    ),
                ],
                Tier1Usage(prompt_tokens=20, completion_tokens=8, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(event_id=event_low.id, categories_count=1, trend_impacts_count=0),
                Tier2Usage(prompt_tokens=15, completion_tokens=5, api_calls=1),
            )
        ),
        cost_tracker=CostTracker(session=mock_db_session),
    )
    tier2.cost_tracker.get_tier_budget_snapshot = AsyncMock(
        return_value=_tier2_budget_snapshot(remaining_calls=1)
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event_low, None, event_high, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )
    pipeline._apply_trend_impacts = AsyncMock(return_value=(0, 0))
    pipeline._capture_unresolved_trend_mapping = AsyncMock()
    pipeline._capture_event_novelty_candidate = AsyncMock()

    await pipeline.process_items(
        [item_low, item_high],
        trends=[
            _build_trend_with_runtime_id("trend-low", weight=0.02),
            _build_trend_with_runtime_id("trend-high", weight=0.08),
        ],
    )

    assert [call.kwargs["event"].id for call in tier2.classify_event.await_args_list] == [
        event_high.id,
        event_low.id,
    ]


@pytest.mark.asyncio
async def test_process_items_keeps_tier2_order_when_budget_is_not_under_pressure(
    mock_db_session,
) -> None:
    item_one = _build_item_with_title("First queued item")
    item_two = _build_item_with_title("Second queued item")
    event_one = Event(
        id=uuid4(), canonical_summary="Event one", source_count=1, unique_source_count=1
    )
    event_two = Event(
        id=uuid4(), canonical_summary="Event two", source_count=1, unique_source_count=1
    )

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            side_effect=[
                ClusterResult(
                    item_id=item_one.id, event_id=event_one.id, created=True, merged=False
                ),
                ClusterResult(
                    item_id=item_two.id, event_id=event_two.id, created=True, merged=False
                ),
            ]
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [
                    Tier1ItemResult(
                        item_id=item_one.id,
                        max_relevance=6,
                        should_queue_tier2=True,
                        trend_scores=[TrendRelevanceScore("trend-one", 6)],
                    ),
                    Tier1ItemResult(
                        item_id=item_two.id,
                        max_relevance=9,
                        should_queue_tier2=True,
                        trend_scores=[TrendRelevanceScore("trend-two", 9)],
                    ),
                ],
                Tier1Usage(prompt_tokens=20, completion_tokens=8, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(event_id=event_one.id, categories_count=1, trend_impacts_count=0),
                Tier2Usage(prompt_tokens=15, completion_tokens=5, api_calls=1),
            )
        ),
        cost_tracker=CostTracker(session=mock_db_session),
    )
    tier2.cost_tracker.get_tier_budget_snapshot = AsyncMock(
        return_value=_tier2_budget_snapshot(remaining_calls=5, headroom_ratio=0.8)
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event_one, None, event_two, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )
    pipeline._apply_trend_impacts = AsyncMock(return_value=(0, 0))
    pipeline._capture_unresolved_trend_mapping = AsyncMock()
    pipeline._capture_event_novelty_candidate = AsyncMock()

    await pipeline.process_items(
        [item_one, item_two],
        trends=[
            _build_trend_with_runtime_id("trend-one", weight=0.04),
            _build_trend_with_runtime_id("trend-two", weight=0.08),
        ],
    )

    assert [call.kwargs["event"].id for call in tier2.classify_event.await_args_list] == [
        event_one.id,
        event_two.id,
    ]


@pytest.mark.asyncio
async def test_process_after_tier1_marks_error_when_stage_helper_returns_no_result(
    mock_db_session, monkeypatch
) -> None:
    item = _build_item_with_title("Queued item")
    pipeline = _build_basic_pipeline(mock_db_session)
    prepared = SimpleNamespace(item=item, item_id=item.id, raw_content=item.raw_content)
    tier1_result = Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)

    async def _stage_none(**_: object):
        return (None, None)

    monkeypatch.setattr(orchestrator_module, "stage_tier2_candidate", _stage_none)

    result = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=tier1_result,
        trends=[_build_trend_with_runtime_id("trend-one", weight=0.04)],
    )

    assert result.result.final_status == ProcessingStatus.ERROR
    assert (
        item.error_message
        == "Tier-2 candidate staging returned neither a candidate nor an execution"
    )


@pytest.mark.asyncio
async def test_process_after_tier1_keeps_item_pending_when_stage_helper_raises_budget_exceeded(
    mock_db_session, monkeypatch
) -> None:
    item = _build_item_with_title("Queued item")
    pipeline = _build_basic_pipeline(mock_db_session)
    prepared = SimpleNamespace(item=item, item_id=item.id, raw_content=item.raw_content)
    tier1_result = Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)

    async def _raise_budget(**_: object):
        raise orchestrator_module.BudgetExceededError("tier2 budget denied")

    monkeypatch.setattr(orchestrator_module, "stage_tier2_candidate", _raise_budget)

    result = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=tier1_result,
        trends=[_build_trend_with_runtime_id("trend-one", weight=0.04)],
    )

    assert result.result.final_status == ProcessingStatus.PENDING
    assert item.processing_status == ProcessingStatus.PENDING
