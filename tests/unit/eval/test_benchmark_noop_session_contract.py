from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import NoResultFound

from src.eval import benchmark as benchmark_module
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event
from tests.unit.trend_forecast_contract_fixtures import sample_binary_forecast_contract

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_benchmark_noop_session_query_surface() -> None:
    session = benchmark_module._NoopSession()

    assert await session.execute(object()) is session
    assert await session.scalars(object()) is session
    assert session.all() == []
    assert session.add(object()) is None
    assert await session.flush([object()]) is None
    with pytest.raises(NoResultFound, match="No rows are available"):
        session.one()


@pytest.mark.asyncio
async def test_benchmark_noop_cost_tracker_preserves_call_contract() -> None:
    tracker = benchmark_module._NoopCostTracker()

    assert await tracker.ensure_within_budget("tier2", provider="openai", model="model") is None
    assert (
        await tracker.record_usage(
            tier="tier2",
            input_tokens=1,
            output_tokens=2,
            provider="openai",
            model="model",
        )
        is None
    )
    with pytest.raises(TypeError):
        await tracker.record_usage(tokens=1)


@dataclass(slots=True)
class _FakeChatCompletions:
    calls: list[dict[str, object]]

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response_payload = {
            "summary": "Troop movements intensified near the border.",
            "extracted_who": ["NATO", "Russia"],
            "extracted_what": "Troop deployment increased near the border.",
            "extracted_where": "Baltic region",
            "extracted_when": "2026-02-07T12:00:00Z",
            "claims": ["Troop deployment increased near the border."],
            "categories": ["military", "security"],
            "has_contradictions": False,
            "contradiction_notes": None,
        }
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(response_payload)))
            ],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40),
        )


def _build_trend() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name="EU-Russia",
        definition={
            "id": "eu-russia",
            "actors": ["NATO", "Russia"],
            "regions": ["Baltic region"],
            "forecast_contract": sample_binary_forecast_contract(),
        },
        indicators={
            "military_movement": {
                "direction": "escalatory",
                "keywords": ["troop", "deployment", "border"],
                "weight": 0.04,
            }
        },
    )


@pytest.mark.asyncio
async def test_benchmark_noop_session_satisfies_real_tier2_persistence_contract() -> None:
    chat = _FakeChatCompletions(calls=[])
    classifier = Tier2Classifier(
        session=benchmark_module._NoopSession(),
        client=SimpleNamespace(chat=SimpleNamespace(completions=chat)),
        model="gpt-4o-mini",
        secondary_model=None,
        cost_tracker=SimpleNamespace(
            ensure_within_budget=AsyncMock(return_value=None),
            record_usage=AsyncMock(return_value=None),
        ),
        semantic_cache=LLMSemanticCache(enabled=False),
    )
    event = Event(id=uuid4(), canonical_summary="Initial summary")

    result, usage = await classifier.classify_event(
        event=event,
        trends=[_build_trend()],
        context_chunks=["NATO reported troop deployment near the Baltic border."],
    )

    assert result.event_id == event.id
    assert result.categories_count == 2
    assert result.trend_impacts_count == 1
    assert usage.api_calls == 1
    assert event.extracted_what == "Troop deployment increased near the border."
    assert event.extracted_claims["trend_impacts"][0]["trend_id"] == "eu-russia"
    assert chat.calls
