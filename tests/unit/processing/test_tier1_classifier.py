from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.processing.cost_tracker import BudgetExceededError
from src.processing.tier1_classifier import Tier1Classifier
from src.storage.models import ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class FakeChatCompletions:
    calls: list[dict[str, object]]

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs.get("messages", [])
        user_message = messages[-1]["content"] if isinstance(messages, list) and messages else "{}"
        payload = json.loads(user_message)

        trends = payload["trends"]
        items = payload["items"]
        result_items: list[dict[str, object]] = []
        for item in items:
            title = item["title"].lower()
            trend_scores: list[dict[str, object]] = []
            for trend in trends:
                score = 9 if trend["trend_id"] in title else 2
                trend_scores.append(
                    {
                        "trend_id": trend["trend_id"],
                        "relevance_score": score,
                        "rationale": "keyword overlap" if score > 5 else "weak overlap",
                    }
                )
            result_items.append({"item_id": item["item_id"], "trend_scores": trend_scores})

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({"items": result_items}))
                )
            ],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def _build_classifier(mock_db_session, *, batch_size: int = 2):
    chat = FakeChatCompletions(calls=[])
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    cost_tracker = SimpleNamespace(
        ensure_within_budget=AsyncMock(return_value=None),
        record_usage=AsyncMock(return_value=None),
    )
    classifier = Tier1Classifier(
        session=mock_db_session,
        client=client,
        model="gpt-4.1-nano",
        batch_size=batch_size,
        cost_tracker=cost_tracker,
    )
    return classifier, chat, cost_tracker


def _build_item(title: str) -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"item-{uuid4()}",
        title=title,
        raw_content=f"{title} raw content",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )


def _build_trend(trend_id: str, name: str):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        definition={"id": trend_id},
        indicators={
            "signal": {
                "keywords": [trend_id, "shared"],
            }
        },
    )


@pytest.mark.asyncio
async def test_classify_items_batches_and_tracks_usage(mock_db_session) -> None:
    classifier, chat, cost_tracker = _build_classifier(mock_db_session, batch_size=2)
    items = [
        _build_item("eu-russia update"),
        _build_item("other news"),
        _build_item("eu-russia brief"),
    ]
    trends = [_build_trend("eu-russia", "EU-Russia"), _build_trend("us-china", "US-China")]

    results, usage = await classifier.classify_items(items, trends)

    assert len(results) == 3
    assert usage.api_calls == 2
    assert usage.prompt_tokens == 200
    assert usage.completion_tokens == 40
    assert usage.estimated_cost_usd == pytest.approx(0.000036, rel=0.001)
    assert len(chat.calls) == 2
    assert cost_tracker.ensure_within_budget.await_count == 2
    assert cost_tracker.record_usage.await_count == 2


@pytest.mark.asyncio
async def test_classify_pending_items_updates_status(mock_db_session) -> None:
    classifier, _chat, _cost_tracker = _build_classifier(mock_db_session, batch_size=10)
    high_item = _build_item("eu-russia escalation")
    low_item = _build_item("sports roundup")
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [high_item, low_item]),
    ]
    trends = [_build_trend("eu-russia", "EU-Russia"), _build_trend("us-china", "US-China")]

    result = await classifier.classify_pending_items(limit=10, trends=trends)

    assert result.scanned == 2
    assert result.queued_count == 1
    assert result.noise_count == 1
    assert high_item.processing_status == ProcessingStatus.PROCESSING
    assert low_item.processing_status == ProcessingStatus.NOISE
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_classify_batch_rejects_mismatched_trend_ids(mock_db_session) -> None:
    classifier, _chat, _cost_tracker = _build_classifier(mock_db_session, batch_size=10)
    item = _build_item("eu-russia escalation")
    trends = [_build_trend("eu-russia", "EU-Russia"), _build_trend("us-china", "US-China")]

    class BadCompletions:
        async def create(self, **kwargs):
            _ = kwargs
            payload = {
                "items": [
                    {
                        "item_id": str(item.id),
                        "trend_scores": [
                            {
                                "trend_id": "eu-russia",
                                "relevance_score": 7,
                                "rationale": "match",
                            }
                        ],
                    }
                ]
            }
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
            )

    classifier.client = SimpleNamespace(chat=SimpleNamespace(completions=BadCompletions()))

    with pytest.raises(ValueError, match="trend ids mismatch"):
        await classifier.classify_items([item], trends)


@pytest.mark.asyncio
async def test_classify_pending_items_raises_without_trends(mock_db_session) -> None:
    classifier, _chat, _cost_tracker = _build_classifier(mock_db_session, batch_size=10)
    item = _build_item("eu-russia escalation")
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [item]),
        SimpleNamespace(all=list),
    ]

    with pytest.raises(ValueError, match="No active trends"):
        await classifier.classify_pending_items(limit=10, trends=None)


@pytest.mark.asyncio
async def test_classify_items_raises_when_budget_exceeded(mock_db_session) -> None:
    classifier, _chat, cost_tracker = _build_classifier(mock_db_session, batch_size=10)
    cost_tracker.ensure_within_budget = AsyncMock(
        side_effect=BudgetExceededError("tier1 daily call limit (1) exceeded")
    )
    item = _build_item("eu-russia escalation")
    trends = [_build_trend("eu-russia", "EU-Russia")]

    with pytest.raises(BudgetExceededError, match="daily call limit"):
        await classifier.classify_items([item], trends)
