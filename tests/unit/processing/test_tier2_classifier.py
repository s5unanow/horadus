from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class FakeChatCompletions:
    calls: list[dict[str, object]]

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs.get("messages", [])
        user_message = messages[-1]["content"] if isinstance(messages, list) and messages else "{}"
        payload = json.loads(user_message)

        trend_id = payload["trends"][0]["trend_id"]
        response_payload = {
            "summary": "Troop movements intensified near the border. Diplomatic channels remain open.",
            "extracted_who": ["NATO", "Russia"],
            "extracted_what": "Troop movement near the border",
            "extracted_where": "Baltic region",
            "extracted_when": "2026-02-07T12:00:00Z",
            "claims": ["Multiple units were redeployed", "Talks are ongoing"],
            "categories": ["military", "security"],
            "trend_impacts": [
                {
                    "trend_id": trend_id,
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.8,
                    "confidence": 0.9,
                    "rationale": "Observed force posture increase",
                }
            ],
        }
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(response_payload)))
            ],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=80),
        )


def _build_classifier(mock_db_session):
    chat = FakeChatCompletions(calls=[])
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    classifier = Tier2Classifier(
        session=mock_db_session,
        client=client,
        model="gpt-4o-mini",
    )
    return classifier, chat


def _build_trend(trend_id: str, name: str):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        definition={"id": trend_id},
        indicators={
            "military_movement": {
                "direction": "escalatory",
                "keywords": ["troops", "deployment"],
            }
        },
    )


@pytest.mark.asyncio
async def test_classify_event_updates_event_fields_and_usage(mock_db_session) -> None:
    classifier, chat = _build_classifier(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="Initial summary")
    trends = [_build_trend("eu-russia", "EU-Russia")]

    result, usage = await classifier.classify_event(
        event=event,
        trends=trends,
        context_chunks=["Context paragraph"],
    )

    assert result.event_id == event.id
    assert result.categories_count == 2
    assert result.trend_impacts_count == 1
    assert event.extracted_what == "Troop movement near the border"
    assert event.extracted_where == "Baltic region"
    assert event.extracted_when == datetime(2026, 2, 7, 12, 0, tzinfo=UTC)
    assert event.categories == ["military", "security"]
    assert isinstance(event.extracted_claims, dict)
    assert len(event.extracted_claims["trend_impacts"]) == 1
    assert usage.api_calls == 1
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 80
    assert usage.estimated_cost_usd == pytest.approx(0.000066, rel=0.001)
    assert len(chat.calls) == 1
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_classify_events_classifies_unstructured_events(mock_db_session) -> None:
    classifier, _chat = _build_classifier(mock_db_session)
    event_one = Event(id=uuid4(), canonical_summary="Summary 1")
    event_two = Event(id=uuid4(), canonical_summary="Summary 2")
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [event_one, event_two]),
    ]
    trends = [_build_trend("eu-russia", "EU-Russia")]

    async def fake_context(_event_id):
        return ["Context"]

    classifier._load_event_context = fake_context

    result = await classifier.classify_events(limit=10, trends=trends)

    assert result.scanned == 2
    assert result.classified == 2
    assert result.usage.api_calls == 2
    assert len(result.results) == 2


@pytest.mark.asyncio
async def test_classify_event_rejects_unknown_trend_ids(mock_db_session) -> None:
    classifier, _chat = _build_classifier(mock_db_session)
    event = Event(id=uuid4(), canonical_summary="Initial summary")
    trends = [_build_trend("eu-russia", "EU-Russia")]

    class BadCompletions:
        async def create(self, **kwargs):
            _ = kwargs
            payload = {
                "summary": "S1. S2.",
                "extracted_who": ["A"],
                "extracted_what": "W",
                "extracted_where": None,
                "extracted_when": None,
                "claims": [],
                "categories": [],
                "trend_impacts": [
                    {
                        "trend_id": "unknown",
                        "signal_type": "x",
                        "direction": "escalatory",
                        "severity": 0.4,
                        "confidence": 0.6,
                        "rationale": None,
                    }
                ],
            }
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
            )

    classifier.client = SimpleNamespace(chat=SimpleNamespace(completions=BadCompletions()))

    with pytest.raises(ValueError, match="unknown trend id"):
        await classifier.classify_event(event=event, trends=trends, context_chunks=["Context"])
