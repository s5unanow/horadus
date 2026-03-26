from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.processing.cost_tracker import BudgetExceededError
from src.processing.tier1_classifier import Tier1ItemResult, TrendRelevanceScore
from src.processing.tier2_candidate_processor import (
    _build_tier2_trend_signals,
    load_item_source_credibility,
    stage_tier2_candidate,
)
from src.storage.models import ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _raw_item(*, with_id: bool = True) -> RawItem:
    return RawItem(
        id=uuid4() if with_id else None,
        source_id=uuid4(),
        external_id=f"external-{uuid4()}",
        url=f"https://example.test/{uuid4()}",
        title="Candidate processor item",
        raw_content="Troops moved near the border",
        content_hash="abc123",
        fetched_at=datetime.now(tz=UTC),
        processing_status=ProcessingStatus.PROCESSING,
    )


@pytest.mark.asyncio
async def test_stage_tier2_candidate_returns_pending_execution_on_budget_exceeded(
    mock_db_session,
) -> None:
    item = _raw_item()
    prepared = SimpleNamespace(item=item, item_id=item.id, raw_content=item.raw_content)
    owner = SimpleNamespace(
        session=mock_db_session,
        embedding_service=SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1]], 0, 1))),
        event_clusterer=SimpleNamespace(
            cluster_item=AsyncMock(side_effect=BudgetExceededError("budget denied"))
        ),
        _load_event=AsyncMock(),
        _event_suppression_action=AsyncMock(),
        _build_item_result=lambda **kwargs: SimpleNamespace(**kwargs),
        _raise_retryable_failure_if_needed=lambda **_: None,
        record_processing_event_suppression=lambda **_: None,
    )

    staged, execution = await stage_tier2_candidate(
        owner=owner,
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
    )

    assert staged is None
    assert execution is not None
    assert execution.result.status == ProcessingStatus.PENDING


@pytest.mark.asyncio
async def test_load_item_source_credibility_returns_empty_when_no_item_ids(mock_db_session) -> None:
    owner = SimpleNamespace(session=mock_db_session)

    result = await load_item_source_credibility(owner=owner, items=[_raw_item(with_id=False)])

    assert result == {}


@pytest.mark.asyncio
async def test_load_item_source_credibility_handles_async_all_and_invalid_values(
    mock_db_session,
) -> None:
    item = _raw_item()

    class _AsyncRows:
        async def all(self):
            return [(item.source_id, "bad-value")]

    owner = SimpleNamespace(session=SimpleNamespace(execute=AsyncMock(return_value=_AsyncRows())))

    result = await load_item_source_credibility(owner=owner, items=[item])

    assert result[item.id] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_load_item_source_credibility_ignores_non_iterable_row_payloads() -> None:
    item = _raw_item()
    owner = SimpleNamespace(
        session=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: None)))
    )

    result = await load_item_source_credibility(owner=owner, items=[item])

    assert result[item.id] == pytest.approx(0.5)


def test_build_tier2_trend_signals_ignores_non_dict_indicators_and_bad_weights() -> None:
    trend = SimpleNamespace(
        indicators={
            "good": {"weight": 0.04},
            "bad_type": [],
            "bad_weight": {"weight": "oops"},
        }
    )
    tier1_result = Tier1ItemResult(
        item_id=uuid4(),
        max_relevance=8,
        should_queue_tier2=True,
        trend_scores=[TrendRelevanceScore("trend-one", 8)],
    )

    signals = _build_tier2_trend_signals(
        tier1_result=tier1_result,
        trend_by_runtime_id={"trend-one": trend},
    )

    assert signals[0].max_indicator_weight == pytest.approx(0.04)
