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
from src.processing.cost_tracker import TIER2, CostTracker
from src.processing.llm_failover import LLMChatRoute
from src.processing.llm_input_safety import (
    DEFAULT_CHARS_PER_TOKEN,
    DEFAULT_TRUNCATION_MARKER,
    estimate_tokens,
    truncate_to_token_limit,
    wrap_untrusted_text,
)
from src.processing.llm_policy import (
    build_safe_payload_content,
    invoke_with_policy,
)
from src.processing.semantic_cache import LLMSemanticCache
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
    has_contradictions: bool = False
    contradiction_notes: str | None = None
    trend_impacts: list[_TrendImpactOutput] = Field(default_factory=list)


class Tier2Classifier:
    """
    Thorough event classifier with strict structured output validation.
    """

    _MAX_REQUEST_INPUT_TOKENS: ClassVar[int] = 8000
    _MAX_CONTEXT_CHUNK_TOKENS: ClassVar[int] = 350
    _MIN_CONTEXT_CHUNK_TOKENS: ClassVar[int] = 64
    _CHARS_PER_TOKEN: ClassVar[int] = DEFAULT_CHARS_PER_TOKEN
    _TRUNCATION_MARKER: ClassVar[str] = DEFAULT_TRUNCATION_MARKER
    _STRICT_RESPONSE_FORMAT: ClassVar[dict[str, Any]] = {
        "type": "json_schema",
        "json_schema": {
            "name": "tier2_event_classification",
            "schema": _Tier2Output.model_json_schema(),
            "strict": True,
        },
    }
    _JSON_OBJECT_RESPONSE_FORMAT: ClassVar[dict[str, str]] = {"type": "json_object"}

    def __init__(
        self,
        session: AsyncSession,
        client: AsyncOpenAI | Any | None = None,
        secondary_client: AsyncOpenAI | Any | None = None,
        model: str | None = None,
        secondary_model: str | None = None,
        prompt_path: str = "ai/prompts/tier2_classify.md",
        cost_tracker: CostTracker | None = None,
        primary_provider: str | None = None,
        secondary_provider: str | None = None,
        primary_base_url: str | None = None,
        secondary_base_url: str | None = None,
        request_overrides: dict[str, Any] | None = None,
        semantic_cache: LLMSemanticCache | None = None,
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_TIER2_MODEL
        self.secondary_model = secondary_model or settings.LLM_TIER2_SECONDARY_MODEL
        self.primary_provider = primary_provider or settings.LLM_PRIMARY_PROVIDER
        self.secondary_provider = secondary_provider or settings.LLM_SECONDARY_PROVIDER
        self.primary_base_url = primary_base_url or settings.LLM_PRIMARY_BASE_URL
        self.secondary_base_url = secondary_base_url or settings.LLM_SECONDARY_BASE_URL
        self.request_overrides = (
            dict(request_overrides) if isinstance(request_overrides, dict) else None
        )
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.client = client or self._create_client(
            api_key=settings.OPENAI_API_KEY,
            base_url=self.primary_base_url,
        )
        self.secondary_client = self._build_secondary_client(secondary_client=secondary_client)
        self.cost_tracker = cost_tracker or CostTracker(session=session)
        self.semantic_cache = semantic_cache or LLMSemanticCache()

    @staticmethod
    def _create_client(*, api_key: str, base_url: str | None = None) -> AsyncOpenAI:
        if not api_key.strip():
            msg = "OPENAI_API_KEY is required for Tier2Classifier"
            raise ValueError(msg)
        if isinstance(base_url, str) and base_url.strip():
            return AsyncOpenAI(api_key=api_key, base_url=base_url.strip())
        return AsyncOpenAI(api_key=api_key)

    def _build_secondary_client(
        self,
        *,
        secondary_client: AsyncOpenAI | Any | None,
    ) -> AsyncOpenAI | Any | None:
        if self.secondary_model is None:
            return None
        if secondary_client is not None:
            return secondary_client

        secondary_api_key = settings.LLM_SECONDARY_API_KEY or settings.OPENAI_API_KEY
        if not secondary_api_key.strip():
            msg = "LLM secondary failover configured without API key"
            raise ValueError(msg)

        return self._create_client(
            api_key=secondary_api_key,
            base_url=self.secondary_base_url,
        )

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
        cached_content = self.semantic_cache.get(
            stage=TIER2,
            model=self.model,
            prompt_template=self.prompt_template,
            payload=payload,
        )
        if isinstance(cached_content, str) and cached_content.strip():
            try:
                cached_output = _Tier2Output.model_validate(json.loads(cached_content))
                self._validate_output_alignment(cached_output, trends=trends)
                self._apply_output(event=event, output=cached_output)
                await self.session.flush()
                return (
                    Tier2EventResult(
                        event_id=event.id,
                        categories_count=len(event.categories or []),
                        trend_impacts_count=len(cached_output.trend_impacts),
                    ),
                    Tier2Usage(),
                )
            except (ValueError, json.JSONDecodeError):
                pass

        payload_content = build_safe_payload_content(
            payload,
            tag="UNTRUSTED_TIER2_PAYLOAD",
            max_tokens=self._MAX_REQUEST_INPUT_TOKENS,
            chars_per_token=self._CHARS_PER_TOKEN,
            truncation_marker=self._TRUNCATION_MARKER,
            warning_message="Tier 2 payload exceeded token budget; truncating",
            warning_context={"stage": TIER2, "model": self.model},
        )
        messages = [
            {"role": "system", "content": self.prompt_template},
            {"role": "user", "content": payload_content},
        ]
        secondary_route = None
        if self.secondary_client is not None and self.secondary_model is not None:
            secondary_route = LLMChatRoute(
                provider=self.secondary_provider or self.primary_provider,
                model=self.secondary_model,
                client=self.secondary_client,
                request_overrides=self.request_overrides,
            )
        invocation = await invoke_with_policy(
            stage=TIER2,
            messages=messages,
            primary_route=LLMChatRoute(
                provider=self.primary_provider,
                model=self.model,
                client=self.client,
                request_overrides=self.request_overrides,
            ),
            secondary_route=secondary_route,
            temperature=0,
            strict_response_format=self._STRICT_RESPONSE_FORMAT,
            fallback_response_format=self._JSON_OBJECT_RESPONSE_FORMAT,
            cost_tracker=self.cost_tracker,
            budget_tier=TIER2,
        )
        usage = Tier2Usage(
            prompt_tokens=invocation.prompt_tokens,
            completion_tokens=invocation.completion_tokens,
            api_calls=1,
            estimated_cost_usd=invocation.estimated_cost_usd,
        )

        output = self._parse_output(invocation.response)
        self._validate_output_alignment(output, trends=trends)
        self._apply_output(event=event, output=output)
        response_choices = getattr(invocation.response, "choices", None)
        if isinstance(response_choices, list) and response_choices:
            message = getattr(response_choices[0], "message", None)
            raw_content = getattr(message, "content", None)
            if isinstance(raw_content, str) and raw_content.strip():
                self.semantic_cache.set(
                    stage=TIER2,
                    model=self.model,
                    prompt_template=self.prompt_template,
                    payload=payload,
                    value=raw_content,
                )
        await self.session.flush()

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
        sanitized_chunks = [
            truncate_to_token_limit(
                text=chunk,
                max_tokens=self._MAX_CONTEXT_CHUNK_TOKENS,
                marker=self._TRUNCATION_MARKER,
                chars_per_token=self._CHARS_PER_TOKEN,
            )
            for chunk in context_chunks
            if chunk.strip()
        ]

        if not sanitized_chunks:
            sanitized_chunks = [self._TRUNCATION_MARKER]

        payload = {
            "event_id": str(event.id),
            "summary": event.canonical_summary,
            "context_chunks": sanitized_chunks,
            "trends": [self._trend_payload(trend) for trend in trends],
        }
        self._enforce_payload_budget(payload)
        payload["context_chunks"] = [
            wrap_untrusted_text(text=str(chunk), tag="UNTRUSTED_EVENT_CONTEXT")
            for chunk in payload["context_chunks"]
        ]
        return payload

    def _enforce_payload_budget(self, payload: dict[str, Any]) -> None:
        if self._estimate_payload_tokens(payload) <= self._MAX_REQUEST_INPUT_TOKENS:
            return

        context_chunks = payload.get("context_chunks")
        if not isinstance(context_chunks, list):
            return

        while (
            len(context_chunks) > 1
            and self._estimate_payload_tokens(payload) > self._MAX_REQUEST_INPUT_TOKENS
        ):
            context_chunks.pop()

        if self._estimate_payload_tokens(payload) <= self._MAX_REQUEST_INPUT_TOKENS:
            return

        context_chunks[0] = truncate_to_token_limit(
            text=str(context_chunks[0]),
            max_tokens=self._MIN_CONTEXT_CHUNK_TOKENS,
            marker=self._TRUNCATION_MARKER,
            chars_per_token=self._CHARS_PER_TOKEN,
        )

    def _estimate_payload_tokens(self, payload: dict[str, Any]) -> int:
        serialized = json.dumps(payload, ensure_ascii=True)
        return estimate_tokens(text=serialized, chars_per_token=self._CHARS_PER_TOKEN)

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
        claims = self._dedupe_strings(output.claims)
        claim_graph = self._build_claim_graph(claims)

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
        contradiction_notes = (
            output.contradiction_notes.strip()
            if isinstance(output.contradiction_notes, str) and output.contradiction_notes.strip()
            else None
        )
        has_contradictions = bool(output.has_contradictions)
        if has_contradictions and contradiction_notes is None:
            contradiction_notes = "Potential contradiction detected across source claims."
        event.has_contradictions = has_contradictions
        event.contradiction_notes = contradiction_notes if has_contradictions else None
        event.extracted_claims = {
            "claims": claims,
            "claim_graph": claim_graph,
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

    def _build_claim_graph(self, claims: list[str]) -> dict[str, Any]:
        nodes = [
            {
                "claim_id": f"claim_{index + 1}",
                "text": claim,
                "normalized_text": self._normalize_claim_text(claim),
            }
            for index, claim in enumerate(claims)
        ]

        links: list[dict[str, str]] = []
        for index, source_node in enumerate(nodes):
            source_text = str(source_node["text"])
            for target_node in nodes[index + 1 :]:
                target_text = str(target_node["text"])
                relation = self._claim_relation(source_text, target_text)
                if relation is None:
                    continue
                links.append(
                    {
                        "source_claim_id": str(source_node["claim_id"]),
                        "target_claim_id": str(target_node["claim_id"]),
                        "relation": relation,
                    }
                )

        return {"nodes": nodes, "links": links}

    @staticmethod
    def _normalize_claim_text(value: str) -> str:
        normalized = value.lower().strip()
        chars = [ch if ch.isalnum() or ch.isspace() else " " for ch in normalized]
        return " ".join("".join(chars).split())

    def _claim_relation(self, first: str, second: str) -> str | None:
        first_tokens = self._claim_tokens(first)
        second_tokens = self._claim_tokens(second)
        overlap = first_tokens.intersection(second_tokens)
        if len(overlap) < 2:
            return None

        first_polarity = self._claim_polarity(first)
        second_polarity = self._claim_polarity(second)
        if first_polarity != second_polarity:
            return "contradict"
        return "support"

    def _claim_tokens(self, value: str) -> set[str]:
        stop_words = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "is",
            "of",
            "on",
            "or",
            "that",
            "the",
            "to",
            "was",
            "were",
            "with",
        }
        normalized = self._normalize_claim_text(value)
        return {
            token
            for token in normalized.split()
            if token and len(token) > 2 and token not in stop_words
        }

    @staticmethod
    def _claim_polarity(value: str) -> str:
        lowered = value.lower()
        negative_markers = (
            " not ",
            " no ",
            " never ",
            " deny",
            " denied",
            " denies",
            " refute",
            " refuted",
            " refutes",
            " false",
            " without ",
            "did not",
            "didn't",
        )
        for marker in negative_markers:
            if marker in f" {lowered} ":
                return "negative"
        return "positive"

    @staticmethod
    def _parse_datetime(raw_value: str | None) -> datetime | None:
        if raw_value is None or not raw_value.strip():
            return None
        normalized = raw_value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
