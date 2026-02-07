"""
Tier 2 LLM classifier for detailed event extraction and trend impacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.storage.models import Event, EventItem, RawItem, Trend


@dataclass(slots=True)
class TrendImpact:
    """Per-trend impact extracted by Tier 2."""

    trend_id: str
    signal_type: str
    direction: str
    severity: float
    confidence: float
    rationale: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "trend_id": self.trend_id,
            "signal_type": self.signal_type,
            "direction": self.direction,
            "severity": self.severity,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class Tier2Usage:
    """Usage and cost metrics for Tier 2 calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class Tier2EventResult:
    """Classification result for one event."""

    event_id: UUID
    categories_count: int
    trend_impacts_count: int


@dataclass(slots=True)
class Tier2RunResult:
    """Summary of classifying event batches."""

    scanned: int = 0
    classified: int = 0
    results: list[Tier2EventResult] = field(default_factory=list)
    usage: Tier2Usage = field(default_factory=Tier2Usage)


class _TrendImpactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_id: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    direction: str = Field(pattern="^(escalatory|de_escalatory)$")
    severity: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class _Tier2Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    extracted_who: list[str] = Field(default_factory=list)
    extracted_what: str = Field(min_length=1)
    extracted_where: str | None = None
    extracted_when: str | None = None
    claims: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    trend_impacts: list[_TrendImpactOutput] = Field(default_factory=list)


class Tier2Classifier:
    """
    Thorough event classifier with strict structured output validation.
    """

    _MODEL_PRICING_USD_PER_1M: ClassVar[dict[str, tuple[float, float]]] = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1-nano": (0.10, 0.40),
    }

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        prompt_path: str = "ai/prompts/tier2_classify.md",
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_TIER2_MODEL
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.client = client or self._create_client()

    def _create_client(self) -> AsyncOpenAI:
        if not settings.OPENAI_API_KEY.strip():
            msg = "OPENAI_API_KEY is required for Tier2Classifier"
            raise ValueError(msg)
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def classify_events(
        self,
        limit: int = 50,
        trends: list[Trend] | None = None,
    ) -> Tier2RunResult:
        """Classify events missing structured extraction."""
        events = await self._load_unclassified_events(limit=limit)
        if not events:
            return Tier2RunResult(scanned=0, classified=0)

        active_trends = trends or await self._load_active_trends()
        if not active_trends:
            msg = "No active trends available for Tier 2 classification"
            raise ValueError(msg)

        usage = Tier2Usage()
        results: list[Tier2EventResult] = []
        for event in events:
            context_chunks = await self._load_event_context(event.id)
            event_result, event_usage = await self.classify_event(
                event=event,
                trends=active_trends,
                context_chunks=context_chunks,
            )
            results.append(event_result)
            usage.prompt_tokens += event_usage.prompt_tokens
            usage.completion_tokens += event_usage.completion_tokens
            usage.api_calls += event_usage.api_calls
            usage.estimated_cost_usd += event_usage.estimated_cost_usd

        usage.estimated_cost_usd = round(usage.estimated_cost_usd, 8)
        return Tier2RunResult(
            scanned=len(events),
            classified=len(results),
            results=results,
            usage=usage,
        )

    async def classify_event(
        self,
        *,
        event: Event,
        trends: list[Trend],
        context_chunks: list[str] | None = None,
    ) -> tuple[Tier2EventResult, Tier2Usage]:
        """Classify one event and persist extracted fields."""
        if event.id is None:
            msg = "Event must have an id before Tier 2 classification"
            raise ValueError(msg)
        if not trends:
            msg = "At least one trend is required for Tier 2 classification"
            raise ValueError(msg)

        chunks = (
            context_chunks
            if context_chunks is not None
            else await self._load_event_context(event.id)
        )
        payload = self._build_payload(event=event, trends=trends, context_chunks=chunks)

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.prompt_template},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
        output = self._parse_output(response)
        self._validate_output_alignment(output, trends=trends)
        self._apply_output(event=event, output=output)
        await self.session.flush()

        usage = self._extract_usage(response)
        usage.api_calls = 1
        usage.estimated_cost_usd = self._estimate_cost_usd(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

        result = Tier2EventResult(
            event_id=event.id,
            categories_count=len(event.categories or []),
            trend_impacts_count=len(output.trend_impacts),
        )
        return (result, usage)

    async def _load_unclassified_events(self, limit: int) -> list[Event]:
        query = (
            select(Event)
            .where(Event.extracted_what.is_(None))
            .order_by(Event.first_seen_at.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(query)).all())

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    async def _load_event_context(self, event_id: UUID, max_items: int = 5) -> list[str]:
        query = (
            select(RawItem.title, RawItem.raw_content)
            .join(EventItem, EventItem.item_id == RawItem.id)
            .where(EventItem.event_id == event_id)
            .order_by(EventItem.added_at.desc())
            .limit(max_items)
        )
        rows = (await self.session.execute(query)).all()

        chunks: list[str] = []
        for title, raw_content in rows:
            title_text = (title or "").strip()
            content_text = (raw_content or "").strip()
            if not content_text:
                continue
            chunk = f"{title_text}\n\n{content_text}" if title_text else content_text
            if len(chunk) > 2500:
                chunk = f"{chunk[:2500]}..."
            chunks.append(chunk)
        return chunks

    def _build_payload(
        self,
        *,
        event: Event,
        trends: list[Trend],
        context_chunks: list[str],
    ) -> dict[str, Any]:
        return {
            "event_id": str(event.id),
            "summary": event.canonical_summary,
            "context_chunks": context_chunks,
            "trends": [self._trend_payload(trend) for trend in trends],
        }

    @staticmethod
    def _trend_payload(trend: Trend) -> dict[str, Any]:
        trend_id = Tier2Classifier._trend_identifier(trend)
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        serialized_indicators: list[dict[str, Any]] = []
        for signal_type, config in indicators.items():
            if not isinstance(config, dict):
                continue
            raw_keywords = config.get("keywords", [])
            keywords = [
                value.strip() for value in raw_keywords if isinstance(value, str) and value.strip()
            ]
            serialized_indicators.append(
                {
                    "signal_type": signal_type,
                    "direction": str(config.get("direction", "")),
                    "keywords": keywords,
                }
            )

        return {
            "trend_id": trend_id,
            "name": trend.name,
            "indicators": serialized_indicators,
        }

    @staticmethod
    def _trend_identifier(trend: Trend) -> str:
        definition = trend.definition if isinstance(trend.definition, dict) else {}
        definition_id = definition.get("id")
        if isinstance(definition_id, str) and definition_id.strip():
            return definition_id.strip()
        return str(trend.id)

    @staticmethod
    def _parse_output(response: Any) -> _Tier2Output:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            msg = "Tier 2 response missing choices"
            raise ValueError(msg)
        message = getattr(choices[0], "message", None)
        raw_content = getattr(message, "content", None)
        if not isinstance(raw_content, str) or not raw_content.strip():
            msg = "Tier 2 response missing message content"
            raise ValueError(msg)

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            msg = "Tier 2 response is not valid JSON"
            raise ValueError(msg) from exc
        return _Tier2Output.model_validate(parsed)

    @staticmethod
    def _validate_output_alignment(output: _Tier2Output, *, trends: list[Trend]) -> None:
        expected_trend_ids = {Tier2Classifier._trend_identifier(trend) for trend in trends}
        seen_trend_ids: set[str] = set()
        for impact in output.trend_impacts:
            if impact.trend_id not in expected_trend_ids:
                msg = f"Tier 2 response returned unknown trend id {impact.trend_id}"
                raise ValueError(msg)
            if impact.trend_id in seen_trend_ids:
                msg = f"Tier 2 response duplicated trend id {impact.trend_id}"
                raise ValueError(msg)
            seen_trend_ids.add(impact.trend_id)

    def _apply_output(self, *, event: Event, output: _Tier2Output) -> None:
        event.canonical_summary = output.summary.strip()
        event.extracted_who = self._dedupe_strings(output.extracted_who)
        event.extracted_what = output.extracted_what.strip()
        event.extracted_where = output.extracted_where.strip() if output.extracted_where else None
        event.extracted_when = self._parse_datetime(output.extracted_when)
        event.categories = self._dedupe_strings(output.categories)

        trend_impacts = [
            TrendImpact(
                trend_id=impact.trend_id,
                signal_type=impact.signal_type,
                direction=impact.direction,
                severity=impact.severity,
                confidence=impact.confidence,
                rationale=impact.rationale,
            ).as_dict()
            for impact in output.trend_impacts
        ]
        event.extracted_claims = {
            "claims": self._dedupe_strings(output.claims),
            "trend_impacts": trend_impacts,
        }

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @staticmethod
    def _parse_datetime(raw_value: str | None) -> datetime | None:
        if raw_value is None or not raw_value.strip():
            return None
        normalized = raw_value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _extract_usage(response: Any) -> Tier2Usage:
        usage_obj = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
        return Tier2Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    def _estimate_cost_usd(self, *, prompt_tokens: int, completion_tokens: int) -> float:
        input_price, output_price = self._price_for_model(self.model)
        return (prompt_tokens * input_price) / 1_000_000 + (
            completion_tokens * output_price
        ) / 1_000_000

    def _price_for_model(self, model: str) -> tuple[float, float]:
        direct = self._MODEL_PRICING_USD_PER_1M.get(model)
        if direct is not None:
            return direct
        for known_model, price in self._MODEL_PRICING_USD_PER_1M.items():
            if model.startswith(known_model):
                return price
        return (0.0, 0.0)
