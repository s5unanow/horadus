from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.processing.embedding_service import EmbeddingService
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.processing.tier1_classifier import Tier1Classifier
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.database import async_session_maker
from src.storage.models import (
    ApiUsage,
    Event,
    EventItem,
    ProcessingStatus,
    RawItem,
    Source,
    SourceType,
    Trend,
    TrendEvidence,
)

pytestmark = pytest.mark.integration


def _load_wrapped_json_payload(raw_content: str) -> dict[str, Any]:
    start = raw_content.find("{")
    end = raw_content.rfind("}")
    if start < 0 or end < start:
        msg = "Unable to locate JSON payload in wrapped content"
        raise ValueError(msg)
    return json.loads(raw_content[start : end + 1])


class FakeEmbeddingsAPI:
    async def create(self, *, model: str, input: list[str]) -> object:
        _ = model
        data = [
            SimpleNamespace(index=index, embedding=[float(index + 1)] * 1536)
            for index, _text in enumerate(input)
        ]
        return SimpleNamespace(data=data)


class FakeTier1Completions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        messages = kwargs.get("messages", [])
        user_content = messages[-1]["content"] if messages else "{}"
        payload = _load_wrapped_json_payload(user_content)
        trend_id = payload["trends"][0]["trend_id"]

        items = []
        for item in payload["items"]:
            items.append(
                {
                    "item_id": item["item_id"],
                    "trend_scores": [
                        {
                            "trend_id": trend_id,
                            "relevance_score": 8,
                            "rationale": "Relevant military movement signal",
                        }
                    ],
                }
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps({"items": items})))
            ],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=40),
        )


class FakeTier2Completions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        messages = kwargs.get("messages", [])
        user_content = messages[-1]["content"] if messages else "{}"
        payload = _load_wrapped_json_payload(user_content)
        trend_id = payload["trends"][0]["trend_id"]

        response_payload = {
            "summary": "Forces moved closer to the border area. Diplomatic contacts continued.",
            "extracted_who": ["NATO", "Russia"],
            "extracted_what": "Cross-border military force movement",
            "extracted_where": "Baltic region",
            "extracted_when": "2026-02-07T12:00:00Z",
            "claims": ["Mechanized units were redeployed"],
            "categories": ["military", "security"],
            "trend_impacts": [
                {
                    "trend_id": trend_id,
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.8,
                    "confidence": 0.9,
                    "rationale": "Visible force buildup pattern",
                }
            ],
        }

        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(response_payload))),
            ],
            usage=SimpleNamespace(prompt_tokens=180, completion_tokens=70),
        )


@pytest.mark.asyncio
async def test_processing_pipeline_runs_end_to_end() -> None:
    source_name = f"Pipeline Source {uuid4()}"
    trend_name = f"Pipeline Trend {uuid4()}"
    external_id = f"https://integration.local/{uuid4()}/article"

    async with async_session_maker() as session:
        source = Source(
            type=SourceType.RSS,
            name=source_name,
            url=f"https://integration.local/{uuid4()}/feed",
            credibility_score=0.9,
            config={},
            is_active=True,
        )
        trend = Trend(
            name=trend_name,
            description="Test trend for processing pipeline integration",
            definition={"id": "eu-russia"},
            baseline_log_odds=-2.197225,
            current_log_odds=-2.197225,
            indicators={
                "military_movement": {
                    "weight": 0.04,
                    "direction": "escalatory",
                    "keywords": ["troops", "deployment"],
                }
            },
            decay_half_life_days=30,
            is_active=True,
        )
        session.add(source)
        session.add(trend)
        await session.flush()

        item = RawItem(
            source_id=source.id,
            external_id=external_id,
            url=external_id,
            title="Military movement update",
            raw_content="Multiple units moved toward the border according to local reports.",
            content_hash=f"hash-pipeline-integration-{uuid4().hex}",
            fetched_at=datetime(2000, 1, 1, tzinfo=UTC),
            processing_status=ProcessingStatus.PENDING,
        )
        session.add(item)
        await session.commit()

        embedding_service = EmbeddingService(
            session=session,
            client=SimpleNamespace(embeddings=FakeEmbeddingsAPI()),
            model="test-embedding-model",
        )
        tier1_classifier = Tier1Classifier(
            session=session,
            client=SimpleNamespace(chat=SimpleNamespace(completions=FakeTier1Completions())),
            model="gpt-4.1-nano",
        )
        tier2_classifier = Tier2Classifier(
            session=session,
            client=SimpleNamespace(chat=SimpleNamespace(completions=FakeTier2Completions())),
            model="gpt-4o-mini",
        )

        pipeline = ProcessingPipeline(
            session=session,
            embedding_service=embedding_service,
            tier1_classifier=tier1_classifier,
            tier2_classifier=tier2_classifier,
        )

        result = await pipeline.process_pending_items(limit=10, trends=[trend])
        await session.commit()

        saved_item = await session.scalar(select(RawItem).where(RawItem.id == item.id))
        assert saved_item is not None

        event_link = await session.scalar(select(EventItem).where(EventItem.item_id == item.id))
        assert event_link is not None

        event = await session.scalar(select(Event).where(Event.id == event_link.event_id))
        assert event is not None
        saved_trend = await session.scalar(select(Trend).where(Trend.id == trend.id))
        assert saved_trend is not None
        evidence_records = (
            await session.scalars(
                select(TrendEvidence).where(
                    TrendEvidence.trend_id == trend.id,
                    TrendEvidence.event_id == event.id,
                )
            )
        ).all()

        assert result.scanned >= 1
        assert result.processed >= 1
        assert result.classified >= 1
        assert result.errors == 0
        assert result.trend_impacts_seen >= 1
        assert result.trend_updates >= 1
        assert any(
            row.item_id == item.id and row.final_status == ProcessingStatus.CLASSIFIED
            for row in result.results
        )
        assert saved_item.processing_status == ProcessingStatus.CLASSIFIED
        assert saved_item.embedding is not None
        assert event.extracted_what == "Cross-border military force movement"
        assert event.categories == ["military", "security"]
        assert isinstance(event.extracted_claims, dict)
        assert len(event.extracted_claims["trend_impacts"]) == 1
        assert float(saved_trend.current_log_odds) > float(saved_trend.baseline_log_odds)
        assert len(evidence_records) == 1
        assert evidence_records[0].signal_type == "military_movement"


@pytest.mark.asyncio
async def test_processing_pipeline_keeps_item_pending_when_budget_exceeded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 1)

    source_name = f"Budget Source {uuid4()}"
    trend_name = f"Budget Trend {uuid4()}"
    external_id = f"https://integration.local/{uuid4()}/budget-article"
    tier1_completions = FakeTier1Completions()

    async with async_session_maker() as session:
        source = Source(
            type=SourceType.RSS,
            name=source_name,
            url=f"https://integration.local/{uuid4()}/feed",
            credibility_score=0.9,
            config={},
            is_active=True,
        )
        trend = Trend(
            name=trend_name,
            description="Budget guard trend",
            definition={"id": "eu-russia"},
            baseline_log_odds=-2.197225,
            current_log_odds=-2.197225,
            indicators={
                "military_movement": {
                    "weight": 0.04,
                    "direction": "escalatory",
                    "keywords": ["troops", "deployment"],
                }
            },
            decay_half_life_days=30,
            is_active=True,
        )
        session.add(source)
        session.add(trend)
        await session.flush()

        usage_date = datetime.now(tz=UTC).date()
        existing_usage = await session.scalar(
            select(ApiUsage).where(
                ApiUsage.usage_date == usage_date,
                ApiUsage.tier == "tier1",
            )
        )
        if existing_usage is None:
            session.add(
                ApiUsage(
                    usage_date=usage_date,
                    tier="tier1",
                    call_count=1,
                    input_tokens=100,
                    output_tokens=10,
                    estimated_cost_usd=0.1,
                )
            )
        else:
            existing_usage.call_count = 1
            existing_usage.input_tokens = 100
            existing_usage.output_tokens = 10
            existing_usage.estimated_cost_usd = 0.1

        item = RawItem(
            source_id=source.id,
            external_id=external_id,
            url=external_id,
            title="Budget constrained article",
            raw_content="Fresh article while budget is exhausted.",
            content_hash=f"hash-budget-integration-{uuid4().hex}",
            fetched_at=datetime(2000, 1, 1, tzinfo=UTC),
            processing_status=ProcessingStatus.PENDING,
        )
        session.add(item)
        await session.commit()

        embedding_service = EmbeddingService(
            session=session,
            client=SimpleNamespace(embeddings=FakeEmbeddingsAPI()),
            model="test-embedding-model",
        )
        tier1_classifier = Tier1Classifier(
            session=session,
            client=SimpleNamespace(chat=SimpleNamespace(completions=tier1_completions)),
            model="gpt-4.1-nano",
        )
        tier2_classifier = Tier2Classifier(
            session=session,
            client=SimpleNamespace(chat=SimpleNamespace(completions=FakeTier2Completions())),
            model="gpt-4o-mini",
        )
        pipeline = ProcessingPipeline(
            session=session,
            embedding_service=embedding_service,
            tier1_classifier=tier1_classifier,
            tier2_classifier=tier2_classifier,
        )

        result = await pipeline.process_pending_items(limit=10, trends=[trend])
        await session.commit()

        saved_item = await session.scalar(select(RawItem).where(RawItem.id == item.id))
        assert saved_item is not None
        assert saved_item.processing_status == ProcessingStatus.PENDING
        assert result.scanned == 1
        assert result.processed == 0
        assert result.errors == 0
        assert result.results[0].final_status == ProcessingStatus.PENDING
        assert tier1_completions.calls == 0
