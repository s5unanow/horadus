"""Tier 2 LLM classifier for detailed event extraction."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.processing.claim_heuristics import (
    build_claim_graph,
    claim_language,
    claim_polarity,
    claim_relation,
    claim_tokens,
    dedupe_strings,
)
from src.processing.cost_tracker import TIER2, CostTracker
from src.processing.event_claims import (
    assign_claim_keys_to_impacts,
    sync_event_claims,
)
from src.processing.llm_failover import LLMChatRoute
from src.processing.llm_input_safety import (
    DEFAULT_CHARS_PER_TOKEN,
    DEFAULT_TRUNCATION_MARKER,
    estimate_tokens,
    truncate_to_token_limit,
    wrap_untrusted_text,
)
from src.processing.llm_policy import (
    apply_latest_active_route_metadata,
    build_safe_payload_content,
    invoke_with_policy,
)
from src.processing.llm_runtime_cache import (
    build_semantic_cache_kwargs,
    build_tier2_event_provenance,
    with_cache_hit_derivation,
)
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.tier2_runtime import (
    Tier2Output,
    mapped_impacts_count,
    parse_tier2_datetime,
    parse_tier2_output,
    parse_tier2_response,
    persist_tier2_output,
    validate_tier2_output_alignment,
)
from src.processing.trend_impact_mapping import TREND_IMPACT_MAPPING_KEY, map_event_trend_impacts
from src.processing.trend_impact_reconciliation import TREND_IMPACT_RECONCILIATION_KEY
from src.storage.event_state import (
    EventEpistemicState,
    apply_event_state_update,
    derived_epistemic_state,
    resolved_event_activity_state,
    resolved_event_epistemic_state,
    resolved_independent_evidence_count,
)
from src.storage.models import Event, EventItem, RawItem, Trend


@dataclass(slots=True)
class Tier2Usage:
    """Usage and cost metrics for Tier 2 calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    active_provider: str | None = None
    active_model: str | None = None
    active_reasoning_effort: str | None = None
    used_secondary_route: bool = False


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


_Tier2Output = Tier2Output
_mapped_impacts_count = mapped_impacts_count


class Tier2Classifier:
    """
    Thorough event classifier with strict structured output validation.
    """

    _MAX_REQUEST_INPUT_TOKENS: ClassVar[int] = 8000
    _PAYLOAD_HEADROOM_TOKENS: ClassVar[int] = 256
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
    _parse_output = staticmethod(
        lambda response: parse_tier2_response(response, output_model=_Tier2Output)
    )
    _validate_output_alignment = staticmethod(validate_tier2_output_alignment)
    _dedupe_strings = staticmethod(dedupe_strings)
    _build_claim_graph = staticmethod(build_claim_graph)
    _claim_relation = staticmethod(claim_relation)
    _claim_tokens = staticmethod(claim_tokens)
    _claim_polarity = staticmethod(claim_polarity)
    _claim_language = staticmethod(claim_language)
    _parse_datetime = staticmethod(parse_tier2_datetime)

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
        reasoning_effort: str | None = None,
        secondary_reasoning_effort: str | None = None,
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
        self.reasoning_effort = reasoning_effort or settings.LLM_TIER2_REASONING_EFFORT
        self.secondary_reasoning_effort = (
            secondary_reasoning_effort or settings.LLM_TIER2_SECONDARY_REASONING_EFFORT
        )
        self.request_overrides = (
            dict(request_overrides) if isinstance(request_overrides, dict) else None
        )
        self.prompt_path = prompt_path
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
            apply_latest_active_route_metadata(target_usage=usage, source_usage=event_usage)
            usage.used_secondary_route = (
                usage.used_secondary_route or event_usage.used_secondary_route
            )

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
        provenance_derivation: dict[str, Any] | None = None,
    ) -> tuple[Tier2EventResult, Tier2Usage]:
        """Classify one event and persist extracted fields."""
        if event.id is None:
            raise ValueError("Event must have an id before Tier 2 classification")
        if not trends:
            raise ValueError("At least one trend is required for Tier 2 classification")

        chunks = (
            context_chunks
            if context_chunks is not None
            else await self._load_event_context(event.id)
        )
        payload = self._build_payload(event=event, trends=trends, context_chunks=chunks)
        cached = await self._load_cached_classification(
            event=event,
            trends=trends,
            payload=payload,
            provenance_derivation=provenance_derivation,
        )
        if cached is not None:
            return (cached, Tier2Usage())

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
        invocation = await self._invoke_event_model(messages=messages)
        usage = Tier2Usage(
            prompt_tokens=invocation.prompt_tokens,
            completion_tokens=invocation.completion_tokens,
            api_calls=1,
            estimated_cost_usd=invocation.estimated_cost_usd,
            active_provider=invocation.active_provider,
            active_model=invocation.active_model,
            active_reasoning_effort=invocation.active_reasoning_effort,
            used_secondary_route=invocation.used_secondary_route,
        )

        output = self._parse_output(invocation.response)
        self._validate_output_alignment(output, trends=trends)
        categories_count, trend_impacts_count = await self._persist_live_output(
            event=event,
            trends=trends,
            output=output,
            invocation=invocation,
            payload=payload,
            provenance_derivation=provenance_derivation,
        )
        result = Tier2EventResult(
            event_id=event.id,
            categories_count=categories_count,
            trend_impacts_count=trend_impacts_count,
        )
        return (result, usage)

    async def _load_cached_classification(
        self,
        *,
        event: Event,
        trends: list[Trend],
        payload: dict[str, Any],
        provenance_derivation: dict[str, Any] | None,
    ) -> Tier2EventResult | None:
        cached_content: str | None = None
        cache_provider: str | None = self.primary_provider
        cache_model = self.model
        cache_reasoning_effort = self.reasoning_effort
        for provider, model, reasoning_effort in self._semantic_cache_read_routes():
            cache_kwargs = build_semantic_cache_kwargs(
                stage=TIER2,
                provider=provider,
                model=model,
                prompt_path=self.prompt_path,
                prompt_template=self.prompt_template,
                schema_name="tier2_event_classification",
                schema_payload=self._STRICT_RESPONSE_FORMAT["json_schema"]["schema"],
                request_overrides=self.request_overrides,
            )
            candidate = await asyncio.to_thread(
                self.semantic_cache.get,
                **cache_kwargs,
                payload=payload,
            )
            if isinstance(candidate, str) and candidate.strip():
                cached_content = candidate
                cache_provider = provider
                cache_model = model
                cache_reasoning_effort = reasoning_effort
                break
        if cached_content is None:
            return None
        cached_output = parse_tier2_output(
            raw_content=cached_content,
            output_model=_Tier2Output,
            validate_output_alignment=self._validate_output_alignment,
            trends=trends,
        )
        if cached_output is None:
            return None
        categories_count, trend_impacts_count = await persist_tier2_output(
            session=self.session,
            sync_event_claims=sync_event_claims,
            event=event,
            output=cached_output,
            trends=trends,
            apply_output=self._apply_output,
            extraction_provenance=build_tier2_event_provenance(
                requested_provider=self.primary_provider,
                requested_model=self.model,
                requested_reasoning_effort=self.reasoning_effort,
                active_provider=cache_provider,
                active_model=cache_model,
                active_reasoning_effort=cache_reasoning_effort,
                prompt_path=self.prompt_path,
                prompt_template=self.prompt_template,
                schema_payload=self._STRICT_RESPONSE_FORMAT["json_schema"]["schema"],
                request_overrides=self.request_overrides,
                derivation=with_cache_hit_derivation(provenance_derivation),
            ),
            mapped_impacts_count=mapped_impacts_count,
        )
        return Tier2EventResult(
            event_id=event.id,
            categories_count=categories_count,
            trend_impacts_count=trend_impacts_count,
        )

    def _semantic_cache_read_routes(self) -> list[tuple[str | None, str, str | None]]:
        routes: list[tuple[str | None, str, str | None]] = [
            (self.primary_provider, self.model, self.reasoning_effort)
        ]
        if self.secondary_model is not None:
            secondary_route = (
                self.secondary_provider or self.primary_provider,
                self.secondary_model,
                self.secondary_reasoning_effort,
            )
            if secondary_route not in routes:
                routes.append(secondary_route)
        return routes

    async def _invoke_event_model(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> Any:
        return await invoke_with_policy(
            stage=TIER2,
            messages=messages,
            primary_route=LLMChatRoute(
                provider=self.primary_provider,
                model=self.model,
                client=self.client,
                reasoning_effort=self.reasoning_effort,
                request_overrides=self.request_overrides,
            ),
            secondary_route=(
                None
                if self.secondary_client is None or self.secondary_model is None
                else LLMChatRoute(
                    provider=self.secondary_provider or self.primary_provider,
                    model=self.secondary_model,
                    client=self.secondary_client,
                    reasoning_effort=self.secondary_reasoning_effort,
                    request_overrides=self.request_overrides,
                )
            ),
            temperature=0,
            strict_response_format=self._STRICT_RESPONSE_FORMAT,
            fallback_response_format=self._JSON_OBJECT_RESPONSE_FORMAT,
            cost_tracker=self.cost_tracker,
            budget_tier=TIER2,
        )

    async def _persist_live_output(
        self,
        *,
        event: Event,
        trends: list[Trend],
        output: _Tier2Output,
        invocation: Any,
        payload: dict[str, Any],
        provenance_derivation: dict[str, Any] | None,
    ) -> tuple[int, int]:
        categories_count, trend_impacts_count = await persist_tier2_output(
            session=self.session,
            sync_event_claims=sync_event_claims,
            event=event,
            output=output,
            trends=trends,
            apply_output=self._apply_output,
            extraction_provenance=build_tier2_event_provenance(
                requested_provider=self.primary_provider,
                requested_model=self.model,
                requested_reasoning_effort=self.reasoning_effort,
                active_provider=invocation.active_provider,
                active_model=invocation.active_model,
                active_reasoning_effort=invocation.active_reasoning_effort,
                prompt_path=self.prompt_path,
                prompt_template=self.prompt_template,
                schema_payload=self._STRICT_RESPONSE_FORMAT["json_schema"]["schema"],
                request_overrides=self.request_overrides,
                derivation=provenance_derivation,
            ),
            mapped_impacts_count=mapped_impacts_count,
        )
        response_choices = getattr(invocation.response, "choices", None)
        if isinstance(response_choices, list) and response_choices:
            message = getattr(response_choices[0], "message", None)
            raw_content = getattr(message, "content", None)
            if isinstance(raw_content, str) and raw_content.strip():
                cache_write_kwargs = build_semantic_cache_kwargs(
                    stage=TIER2,
                    provider=invocation.active_provider,
                    model=invocation.active_model,
                    prompt_path=self.prompt_path,
                    prompt_template=self.prompt_template,
                    schema_name="tier2_event_classification",
                    schema_payload=self._STRICT_RESPONSE_FORMAT["json_schema"]["schema"],
                    request_overrides=self.request_overrides,
                )
                await asyncio.to_thread(
                    self.semantic_cache.set,
                    **cache_write_kwargs,
                    payload=payload,
                    value=raw_content,
                )
        return (categories_count, trend_impacts_count)

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
        _ = trends
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
        }
        self._enforce_payload_budget(payload)
        payload["context_chunks"] = [
            wrap_untrusted_text(text=str(chunk), tag="UNTRUSTED_EVENT_CONTEXT")
            for chunk in payload["context_chunks"]
        ]
        if self._estimate_payload_tokens(payload) > self._MAX_REQUEST_INPUT_TOKENS:
            msg = "Tier 2 payload exceeds safe input budget after deterministic reductions"
            raise ValueError(msg)
        return payload

    def _enforce_payload_budget(self, payload: dict[str, Any]) -> None:
        budget_limit = self._payload_budget_limit()
        if self._estimate_payload_tokens(payload) <= budget_limit:
            return

        context_chunks = payload.get("context_chunks")
        if not isinstance(context_chunks, list):
            return

        while len(context_chunks) > 1 and self._estimate_payload_tokens(payload) > budget_limit:
            context_chunks.pop()

        if self._estimate_payload_tokens(payload) <= budget_limit:
            return

        context_chunks[0] = truncate_to_token_limit(
            text=str(context_chunks[0]),
            max_tokens=self._MIN_CONTEXT_CHUNK_TOKENS,
            marker=self._TRUNCATION_MARKER,
            chars_per_token=self._CHARS_PER_TOKEN,
        )
        if self._estimate_payload_tokens(payload) > budget_limit:
            msg = "Tier 2 payload exceeds safe input budget after deterministic reductions"
            raise ValueError(msg)

    def _estimate_payload_tokens(self, payload: dict[str, Any]) -> int:
        serialized = json.dumps(payload, ensure_ascii=True)
        return estimate_tokens(text=serialized, chars_per_token=self._CHARS_PER_TOKEN)

    def _payload_budget_limit(self) -> int:
        return max(1, self._MAX_REQUEST_INPUT_TOKENS - self._PAYLOAD_HEADROOM_TOKENS)

    def _apply_output(self, *, event: Event, output: _Tier2Output, trends: list[Trend]) -> None:
        existing_claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        system_claims = {}
        for system_key in (TREND_IMPACT_RECONCILIATION_KEY,):
            if system_key in existing_claims:
                system_claims[system_key] = existing_claims[system_key]
        event.canonical_summary = output.summary.strip()
        event.extracted_who = self._dedupe_strings(output.extracted_who)
        event.extracted_what = output.extracted_what.strip()
        event.extracted_where = output.extracted_where.strip() if output.extracted_where else None
        event.extracted_when = self._parse_datetime(output.extracted_when)
        event.categories = self._dedupe_strings(output.categories)
        claims = self._dedupe_strings(output.claims)
        claim_graph = self._build_claim_graph(claims)
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
        if resolved_event_epistemic_state(event) != EventEpistemicState.RETRACTED.value:
            apply_event_state_update(
                event,
                epistemic_state=derived_epistemic_state(
                    unique_source_count=resolved_independent_evidence_count(event),
                    has_contradictions=has_contradictions,
                ),
                activity_state=resolved_event_activity_state(event),
            )
        event.extracted_claims = {"claims": claims, "claim_graph": claim_graph, **system_claims}
        mapping = map_event_trend_impacts(event=event, trends=trends)
        event.extracted_claims["trend_impacts"] = assign_claim_keys_to_impacts(
            event=event,
            impacts=mapping.impacts,
        )
        event.extracted_claims[TREND_IMPACT_MAPPING_KEY] = mapping.diagnostics
