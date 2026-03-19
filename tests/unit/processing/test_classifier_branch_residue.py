from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.processing.tier1_classifier as tier1_module
import src.processing.tier2_classifier as tier2_module
from src.processing.tier1_classifier import Tier1Classifier
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event, ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _tier1_classifier(mock_db_session) -> Tier1Classifier:
    return Tier1Classifier(
        session=mock_db_session,
        client=SimpleNamespace(),
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
        semantic_cache=SimpleNamespace(get=lambda **_: None, set=MagicMock()),
    )


def _tier2_classifier(mock_db_session) -> Tier2Classifier:
    return Tier2Classifier(
        session=mock_db_session,
        client=SimpleNamespace(),
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
        semantic_cache=SimpleNamespace(get=lambda **_: None, set=MagicMock()),
    )


@pytest.mark.asyncio
async def test_tier1_skips_cache_store_when_model_message_content_is_non_string(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = _tier1_classifier(mock_db_session)
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-1",
        title="title",
        raw_content="content",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )
    trend = SimpleNamespace(
        id=uuid4(),
        name="Trend",
        definition={"id": "eu-russia"},
        indicators={"signal": {"keywords": ["x"]}},
    )
    parsed_output = tier1_module._Tier1Output.model_validate(
        {
            "items": [
                {
                    "item_id": str(item.id),
                    "trend_scores": [
                        {"trend_id": "eu-russia", "relevance_score": 7, "rationale": "match"}
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(
        tier1_module,
        "invoke_with_policy",
        AsyncMock(
            return_value=SimpleNamespace(
                response=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=123))]
                ),
                prompt_tokens=1,
                completion_tokens=1,
                estimated_cost_usd=0.01,
                active_provider="openai",
                active_model="gpt",
                active_reasoning_effort=None,
                used_secondary_route=False,
            )
        ),
    )
    monkeypatch.setattr(classifier, "_parse_output", lambda _response: parsed_output)

    results, _ = await classifier._classify_batch([item], [trend])

    assert len(results) == 1
    classifier.semantic_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_tier2_skips_cache_store_when_model_message_content_is_non_string(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = _tier2_classifier(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="summary")
    trend = SimpleNamespace(
        id=uuid4(),
        name="Trend",
        definition={"id": "eu-russia"},
        indicators={"signal": {"direction": "escalatory", "keywords": ["x"]}},
    )
    parsed_output = tier2_module._Tier2Output.model_validate(
        {
            "summary": "summary",
            "extracted_who": [],
            "extracted_what": "what",
            "extracted_where": None,
            "extracted_when": None,
            "claims": [],
            "categories": [],
            "has_contradictions": False,
            "contradiction_notes": None,
        }
    )
    monkeypatch.setattr(
        tier2_module,
        "invoke_with_policy",
        AsyncMock(
            return_value=SimpleNamespace(
                response=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=123))]
                ),
                prompt_tokens=1,
                completion_tokens=1,
                estimated_cost_usd=0.01,
                active_provider="openai",
                active_model="gpt",
                active_reasoning_effort=None,
                used_secondary_route=False,
            )
        ),
    )
    monkeypatch.setattr(classifier, "_parse_output", lambda _response: parsed_output)

    result, _ = await classifier.classify_event(
        event=event,
        trends=[trend],
        context_chunks=["context"],
    )

    assert result.event_id == event.id
    classifier.semantic_cache.set.assert_not_called()
