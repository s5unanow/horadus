"""
Tier 1 LLM classifier for fast relevance filtering.
"""

from __future__ import annotations

import asyncio
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
from src.processing.cost_tracker import TIER1, CostTracker
from src.processing.llm_failover import (
    LLMChatRoute,
)
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
from src.storage.models import ProcessingStatus, RawItem, Trend


@dataclass(slots=True)
class TrendRelevanceScore:
    """Per-trend relevance score for one item."""

    trend_id: str
    relevance_score: int
    rationale: str | None = None


@dataclass(slots=True)
class Tier1ItemResult:
    """Tier 1 classification decision for one raw item."""

    item_id: UUID
    max_relevance: int
    should_queue_tier2: bool
    trend_scores: list[TrendRelevanceScore] = field(default_factory=list)


@dataclass(slots=True)
class Tier1Usage:
    """Usage and cost metrics for one classifier run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class Tier1RunResult:
    """Summary of classifying pending items."""

    scanned: int = 0
    noise_count: int = 0
    queued_count: int = 0
    queued_item_ids: list[UUID] = field(default_factory=list)
    results: list[Tier1ItemResult] = field(default_factory=list)
    usage: Tier1Usage = field(default_factory=Tier1Usage)


class _TrendScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_id: str = Field(min_length=1)
    relevance_score: int = Field(ge=0, le=10)
    rationale: str | None = None


class _ItemOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    trend_scores: list[_TrendScoreOutput] = Field(min_length=1)


class _Tier1Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[_ItemOutput] = Field(min_length=1)


class Tier1Classifier:
    """
    Fast relevance filter for routing items to Tier 2.
    """

    _MAX_REQUEST_INPUT_TOKENS: ClassVar[int] = 6000
    _MAX_TITLE_TOKENS: ClassVar[int] = 80
    _MAX_ITEM_CONTENT_TOKENS: ClassVar[int] = 300
    _CHARS_PER_TOKEN: ClassVar[int] = DEFAULT_CHARS_PER_TOKEN
    _TRUNCATION_MARKER: ClassVar[str] = DEFAULT_TRUNCATION_MARKER
    _STRICT_RESPONSE_FORMAT: ClassVar[dict[str, Any]] = {
        "type": "json_schema",
        "json_schema": {
            "name": "tier1_classification",
            "schema": _Tier1Output.model_json_schema(),
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
        batch_size: int | None = None,
        prompt_path: str = "ai/prompts/tier1_filter.md",
        cost_tracker: CostTracker | None = None,
        primary_provider: str | None = None,
        secondary_provider: str | None = None,
        primary_base_url: str | None = None,
        secondary_base_url: str | None = None,
        request_overrides: dict[str, Any] | None = None,
        semantic_cache: LLMSemanticCache | None = None,
    ) -> None:
        self.session = session
        self.model = model or settings.LLM_TIER1_MODEL
        self.secondary_model = secondary_model or settings.LLM_TIER1_SECONDARY_MODEL
        self.primary_provider = primary_provider or settings.LLM_PRIMARY_PROVIDER
        self.secondary_provider = secondary_provider or settings.LLM_SECONDARY_PROVIDER
        self.primary_base_url = primary_base_url or settings.LLM_PRIMARY_BASE_URL
        self.secondary_base_url = secondary_base_url or settings.LLM_SECONDARY_BASE_URL
        self.request_overrides = (
            dict(request_overrides) if isinstance(request_overrides, dict) else None
        )
        configured_batch_size = settings.LLM_TIER1_BATCH_SIZE if batch_size is None else batch_size
        self.batch_size = max(1, configured_batch_size)
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
            msg = "OPENAI_API_KEY is required for Tier1Classifier"
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

    async def classify_pending_items(
        self,
        limit: int = 100,
        trends: list[Trend] | None = None,
    ) -> Tier1RunResult:
        """Classify pending raw items and update their processing status."""
        pending_items = await self._load_pending_items(limit=limit)
        if not pending_items:
            return Tier1RunResult(scanned=0)

        active_trends = trends or await self._load_active_trends()
        if not active_trends:
            msg = "No active trends available for Tier 1 classification"
            raise ValueError(msg)

        results, usage = await self.classify_items(pending_items, active_trends)
        result_by_id = {result.item_id: result for result in results}

        queued_item_ids: list[UUID] = []
        noise_count = 0
        queued_count = 0
        for item in pending_items:
            item_result = result_by_id.get(item.id)
            if item_result is None:
                msg = f"Tier 1 output missing item id {item.id}"
                raise ValueError(msg)
            if item_result.should_queue_tier2:
                item.processing_status = ProcessingStatus.PROCESSING
                item.processing_started_at = datetime.now(tz=UTC)
                queued_item_ids.append(item.id)
                queued_count += 1
            else:
                item.processing_status = ProcessingStatus.NOISE
                item.processing_started_at = None
                noise_count += 1

        await self.session.flush()
        return Tier1RunResult(
            scanned=len(pending_items),
            noise_count=noise_count,
            queued_count=queued_count,
            queued_item_ids=queued_item_ids,
            results=results,
            usage=usage,
        )

    async def classify_items(
        self,
        items: list[RawItem],
        trends: list[Trend],
    ) -> tuple[list[Tier1ItemResult], Tier1Usage]:
        """Classify explicit items for explicit trends."""
        if not items:
            return ([], Tier1Usage())
        if not trends:
            msg = "At least one trend is required for Tier 1 classification"
            raise ValueError(msg)

        all_results: list[Tier1ItemResult] = []
        usage = Tier1Usage()
        for batch_start in range(0, len(items), self.batch_size):
            batch = items[batch_start : batch_start + self.batch_size]
            batch_results, batch_usage = await self._classify_batch(batch, trends)
            all_results.extend(batch_results)
            usage.prompt_tokens += batch_usage.prompt_tokens
            usage.completion_tokens += batch_usage.completion_tokens
            usage.api_calls += batch_usage.api_calls
            usage.estimated_cost_usd += batch_usage.estimated_cost_usd

        usage.estimated_cost_usd = round(usage.estimated_cost_usd, 8)
        return (all_results, usage)

    async def _classify_batch(
        self,
        items: list[RawItem],
        trends: list[Trend],
    ) -> tuple[list[Tier1ItemResult], Tier1Usage]:
        payload = self._build_payload(items=items, trends=trends)
        cached_content = await asyncio.to_thread(
            self.semantic_cache.get,
            stage=TIER1,
            model=self.model,
            prompt_template=self.prompt_template,
            payload=payload,
        )
        if isinstance(cached_content, str) and cached_content.strip():
            try:
                output = _Tier1Output.model_validate(json.loads(cached_content))
                self._validate_output_alignment(output, items=items, trends=trends)
                return (self._to_item_results(output), Tier1Usage())
            except (ValueError, json.JSONDecodeError):
                pass

        if (
            self._estimate_payload_tokens(payload) > self._MAX_REQUEST_INPUT_TOKENS
            and len(items) > 1
        ):
            midpoint = max(1, len(items) // 2)
            left_results, left_usage = await self._classify_batch(items[:midpoint], trends)
            right_results, right_usage = await self._classify_batch(items[midpoint:], trends)
            return (
                [*left_results, *right_results],
                Tier1Usage(
                    prompt_tokens=left_usage.prompt_tokens + right_usage.prompt_tokens,
                    completion_tokens=left_usage.completion_tokens + right_usage.completion_tokens,
                    api_calls=left_usage.api_calls + right_usage.api_calls,
                    estimated_cost_usd=left_usage.estimated_cost_usd
                    + right_usage.estimated_cost_usd,
                ),
            )

        payload_content = build_safe_payload_content(
            payload,
            tag="UNTRUSTED_TIER1_PAYLOAD",
            max_tokens=self._MAX_REQUEST_INPUT_TOKENS,
            chars_per_token=self._CHARS_PER_TOKEN,
            truncation_marker=self._TRUNCATION_MARKER,
            warning_message="Tier 1 payload exceeded token budget; truncating",
            warning_context={"stage": TIER1, "model": self.model},
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
            stage=TIER1,
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
            budget_tier=TIER1,
        )
        output = self._parse_output(invocation.response)
        self._validate_output_alignment(output, items=items, trends=trends)
        results = self._to_item_results(output)
        response_choices = getattr(invocation.response, "choices", None)
        if isinstance(response_choices, list) and response_choices:
            message = getattr(response_choices[0], "message", None)
            raw_content = getattr(message, "content", None)
            if isinstance(raw_content, str) and raw_content.strip():
                await asyncio.to_thread(
                    self.semantic_cache.set,
                    stage=TIER1,
                    model=self.model,
                    prompt_template=self.prompt_template,
                    payload=payload,
                    value=raw_content,
                )

        usage = Tier1Usage(
            prompt_tokens=invocation.prompt_tokens,
            completion_tokens=invocation.completion_tokens,
            api_calls=1,
            estimated_cost_usd=invocation.estimated_cost_usd,
        )
        return (results, usage)

    async def _load_pending_items(self, limit: int) -> list[RawItem]:
        query = (
            select(RawItem)
            .where(RawItem.processing_status == ProcessingStatus.PENDING)
            .order_by(RawItem.fetched_at.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(query)).all())

    async def _load_active_trends(self) -> list[Trend]:
        query = select(Trend).where(Trend.is_active.is_(True)).order_by(Trend.name.asc())
        return list((await self.session.scalars(query)).all())

    def _build_payload(self, items: list[RawItem], trends: list[Trend]) -> dict[str, Any]:
        trend_payloads = [self._trend_payload(trend) for trend in trends]
        item_payloads = [self._item_payload(item) for item in items]
        return {
            "threshold": settings.TIER1_RELEVANCE_THRESHOLD,
            "trends": trend_payloads,
            "items": item_payloads,
        }

    @staticmethod
    def _item_payload(item: RawItem) -> dict[str, str]:
        max_title_tokens = Tier1Classifier._MAX_TITLE_TOKENS
        max_content_tokens = Tier1Classifier._MAX_ITEM_CONTENT_TOKENS
        chars_per_token = Tier1Classifier._CHARS_PER_TOKEN
        truncation_marker = Tier1Classifier._TRUNCATION_MARKER
        if item.id is None:
            msg = "RawItem must have an id for Tier 1 classification"
            raise ValueError(msg)

        title = truncate_to_token_limit(
            text=(item.title or "").strip(),
            max_tokens=max_title_tokens,
            marker=truncation_marker,
            chars_per_token=chars_per_token,
        )
        content = truncate_to_token_limit(
            text=item.raw_content.strip(),
            max_tokens=max_content_tokens,
            marker=truncation_marker,
            chars_per_token=chars_per_token,
        )
        content = wrap_untrusted_text(text=content, tag="UNTRUSTED_ARTICLE_CONTENT")

        return {
            "item_id": str(item.id),
            "title": title,
            "content": content,
        }

    def _estimate_payload_tokens(self, payload: dict[str, Any]) -> int:
        serialized = json.dumps(payload, ensure_ascii=True)
        return estimate_tokens(text=serialized, chars_per_token=self._CHARS_PER_TOKEN)

    @staticmethod
    def _trend_payload(trend: Trend) -> dict[str, Any]:
        trend_id = Tier1Classifier._trend_identifier(trend)
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        keywords: list[str] = []
        for indicator in indicators.values():
            if not isinstance(indicator, dict):
                continue
            raw_keywords = indicator.get("keywords", [])
            if not isinstance(raw_keywords, list):
                continue
            for keyword in raw_keywords:
                if isinstance(keyword, str):
                    normalized = keyword.strip()
                    if normalized and normalized not in keywords:
                        keywords.append(normalized)

        return {
            "trend_id": trend_id,
            "name": trend.name,
            "keywords": keywords,
        }

    @staticmethod
    def _trend_identifier(trend: Trend) -> str:
        definition = trend.definition if isinstance(trend.definition, dict) else {}
        definition_id = definition.get("id")
        if isinstance(definition_id, str) and definition_id.strip():
            return definition_id.strip()
        return str(trend.id)

    @staticmethod
    def _parse_output(response: Any) -> _Tier1Output:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            msg = "Tier 1 response missing choices"
            raise ValueError(msg)
        message = getattr(choices[0], "message", None)
        raw_content = getattr(message, "content", None)
        if not isinstance(raw_content, str) or not raw_content.strip():
            msg = "Tier 1 response missing message content"
            raise ValueError(msg)

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            msg = "Tier 1 response is not valid JSON"
            raise ValueError(msg) from exc
        return _Tier1Output.model_validate(parsed)

    @staticmethod
    def _validate_output_alignment(
        output: _Tier1Output,
        *,
        items: list[RawItem],
        trends: list[Trend],
    ) -> None:
        expected_item_ids = {str(item.id) for item in items}
        actual_item_ids = {row.item_id for row in output.items}
        if expected_item_ids != actual_item_ids:
            msg = "Tier 1 response item ids do not match input batch"
            raise ValueError(msg)

        expected_trend_ids = {Tier1Classifier._trend_identifier(trend) for trend in trends}
        for row in output.items:
            seen_trend_ids: set[str] = set()
            for score in row.trend_scores:
                if score.trend_id in seen_trend_ids:
                    msg = f"Tier 1 response has duplicate trend id {score.trend_id}"
                    raise ValueError(msg)
                seen_trend_ids.add(score.trend_id)

            if seen_trend_ids != expected_trend_ids:
                msg = f"Tier 1 response trend ids mismatch for item {row.item_id}"
                raise ValueError(msg)

    @staticmethod
    def _to_item_results(output: _Tier1Output) -> list[Tier1ItemResult]:
        results: list[Tier1ItemResult] = []
        for row in output.items:
            trend_scores = [
                TrendRelevanceScore(
                    trend_id=score.trend_id,
                    relevance_score=score.relevance_score,
                    rationale=score.rationale,
                )
                for score in row.trend_scores
            ]
            max_relevance = max(score.relevance_score for score in row.trend_scores)
            results.append(
                Tier1ItemResult(
                    item_id=UUID(row.item_id),
                    max_relevance=max_relevance,
                    should_queue_tier2=max_relevance >= settings.TIER1_RELEVANCE_THRESHOLD,
                    trend_scores=trend_scores,
                )
            )
        return results
