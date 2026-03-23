"""
Gold-set benchmarking utilities for Tier-1/Tier-2 model configurations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from openai import AsyncOpenAI

from src.core.config import settings
from src.core.trend_config_loader import discover_trend_config_files, load_trends_from_config_dir
from src.eval import artifact_provenance as provenance
from src.processing.llm_policy import apply_latest_active_route_metadata
from src.processing.semantic_cache import LLMSemanticCache
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2Classifier, Tier2Usage
from src.storage.models import Event, ProcessingStatus, RawItem

HUMAN_VERIFIED_LABEL = "human_verified"
DISPATCH_MODE_REALTIME = "realtime"
DISPATCH_MODE_BATCH = "batch"
REQUEST_PRIORITY_REALTIME = "realtime"
REQUEST_PRIORITY_FLEX = "flex"
_BATCH_DISPATCH_SIZE = 10
_SAFE_TIER1_BATCH_SIZE = 1
_TIER1_BATCH_POLICY_SAFE_DEFAULT = "safe_single_item_default"
_TIER1_BATCH_POLICY_DIAGNOSTIC = "diagnostic_multi_item_batch"
_TIER1_PROMPT_PATH = "ai/prompts/tier1_filter.md"
_TIER2_PROMPT_PATH = "ai/prompts/tier2_classify.md"
_DEFAULT_BENCHMARK_CONFIG_NAMES = ("baseline", "alternative")


@dataclass(slots=True)
class EvalConfig:
    """Benchmark configuration for a Tier-1/Tier-2 model pair."""

    name: str
    tier1_model: str
    tier2_model: str
    provider: str = "openai"
    base_url: str | None = None
    tier1_reasoning_effort: str | None = None
    tier2_reasoning_effort: str | None = None
    tier1_request_overrides: dict[str, Any] | None = None
    tier2_request_overrides: dict[str, Any] | None = None


@dataclass(slots=True)
class Tier1GoldLabel:
    """Expected Tier-1 labels for one gold-set item."""

    trend_scores: dict[str, int]
    max_relevance: int


@dataclass(slots=True)
class Tier2GoldLabel:
    """Expected Tier-2 labels for one gold-set item."""

    trend_id: str
    signal_type: str
    direction: str
    severity: float
    confidence: float


@dataclass(slots=True)
class GoldSetItem:
    """One item from the gold-set dataset."""

    item_id: str
    title: str
    content: str
    label_verification: str
    tier1: Tier1GoldLabel
    tier2: Tier2GoldLabel | None


@dataclass(slots=True)
class _Tier1Metrics:
    queue_threshold: int = settings.TIER1_RELEVANCE_THRESHOLD
    items_total: int = 0
    failures: int = 0
    score_pairs_total: int = 0
    queue_accuracy_total: int = 0
    score_abs_error_sum: float = 0.0
    max_relevance_abs_error_sum: float = 0.0

    def record(self, *, gold: GoldSetItem, predicted: Tier1ItemResult) -> None:
        self.items_total += 1
        for trend_id, expected_score in gold.tier1.trend_scores.items():
            predicted_score = next(
                (
                    score.relevance_score
                    for score in predicted.trend_scores
                    if score.trend_id == trend_id
                ),
                0,
            )
            self.score_pairs_total += 1
            self.score_abs_error_sum += abs(predicted_score - expected_score)

        self.max_relevance_abs_error_sum += abs(predicted.max_relevance - gold.tier1.max_relevance)
        expected_queue = gold.tier1.max_relevance >= self.queue_threshold
        if predicted.should_queue_tier2 == expected_queue:
            self.queue_accuracy_total += 1

    def record_failure(self, *, gold: GoldSetItem) -> None:
        self.items_total += 1
        self.failures += 1
        for expected_score in gold.tier1.trend_scores.values():
            self.score_pairs_total += 1
            self.score_abs_error_sum += abs(expected_score)
        self.max_relevance_abs_error_sum += abs(gold.tier1.max_relevance)

    def to_dict(self) -> dict[str, float | int]:
        score_mae = (
            self.score_abs_error_sum / self.score_pairs_total if self.score_pairs_total > 0 else 0.0
        )
        max_mae = (
            self.max_relevance_abs_error_sum / self.items_total if self.items_total > 0 else 0.0
        )
        queue_acc = self.queue_accuracy_total / self.items_total if self.items_total > 0 else 0.0
        return {
            "items_total": self.items_total,
            "failures": self.failures,
            "score_pairs_total": self.score_pairs_total,
            "score_mae": round(score_mae, 6),
            "max_relevance_mae": round(max_mae, 6),
            "queue_threshold": self.queue_threshold,
            "queue_accuracy": round(queue_acc, 6),
        }


@dataclass(slots=True)
class _Tier2Metrics:
    items_total: int = 0
    failures: int = 0
    trend_match_correct: int = 0
    signal_type_correct: int = 0
    direction_correct: int = 0
    severity_abs_error_sum: float = 0.0
    confidence_abs_error_sum: float = 0.0

    def record(
        self,
        *,
        expected: Tier2GoldLabel,
        predicted: Tier2GoldLabel | None,
    ) -> None:
        self.items_total += 1
        if predicted is None:
            self.failures += 1
            self.severity_abs_error_sum += abs(0.0 - expected.severity)
            self.confidence_abs_error_sum += abs(0.0 - expected.confidence)
            return

        if predicted.trend_id == expected.trend_id:
            self.trend_match_correct += 1
        if predicted.signal_type == expected.signal_type:
            self.signal_type_correct += 1
        if predicted.direction == expected.direction:
            self.direction_correct += 1
        self.severity_abs_error_sum += abs(predicted.severity - expected.severity)
        self.confidence_abs_error_sum += abs(predicted.confidence - expected.confidence)

    def to_dict(self) -> dict[str, float | int]:
        denominator = self.items_total if self.items_total > 0 else 1
        return {
            "items_total": self.items_total,
            "failures": self.failures,
            "trend_match_accuracy": round(self.trend_match_correct / denominator, 6),
            "signal_type_accuracy": round(self.signal_type_correct / denominator, 6),
            "direction_accuracy": round(self.direction_correct / denominator, 6),
            "severity_mae": round(self.severity_abs_error_sum / denominator, 6),
            "confidence_mae": round(self.confidence_abs_error_sum / denominator, 6),
        }


@dataclass(slots=True)
class _NoopSession:
    async def flush(self) -> None:
        return None


@dataclass(slots=True)
class _NoopCostTracker:
    async def ensure_within_budget(
        self,
        _tier: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        _ = (provider, model)
        return

    async def record_usage(
        self,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        _ = (tier, input_tokens, output_tokens, provider, model)
        return


@dataclass(slots=True)
class _BenchmarkResponseRecorder:
    last_raw_output: str | None = None

    def reset(self) -> None:
        self.last_raw_output = None

    def capture_response(self, response: Any) -> None:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            return
        message = getattr(choices[0], "message", None)
        raw_content = getattr(message, "content", None)
        if isinstance(raw_content, str) and raw_content.strip():
            self.last_raw_output = raw_content


class _RecordingChatCompletions:
    def __init__(self, *, wrapped: Any, recorder: _BenchmarkResponseRecorder) -> None:
        self._wrapped = wrapped
        self._recorder = recorder

    async def create(self, **kwargs: Any) -> Any:
        response = await self._wrapped.create(**kwargs)
        self._recorder.capture_response(response)
        return response


def _wrap_client_with_recorder(
    *,
    client: Any,
    recorder: _BenchmarkResponseRecorder,
) -> Any:
    chat = getattr(client, "chat", None)
    completions = getattr(chat, "completions", None)
    if completions is None or not hasattr(completions, "create"):
        return client
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=_RecordingChatCompletions(wrapped=completions, recorder=recorder)
        )
    )


def _build_benchmark_secondary_client(
    *,
    primary_api_key: str,
    secondary_model: str | None,
    recorder: _BenchmarkResponseRecorder,
) -> Any | None:
    if secondary_model is None:
        return None
    secondary_api_key = settings.LLM_SECONDARY_API_KEY or primary_api_key
    secondary_client = _build_openai_client(
        api_key=secondary_api_key,
        base_url=settings.LLM_SECONDARY_BASE_URL or None,
    )
    return _wrap_client_with_recorder(client=secondary_client, recorder=recorder)


def available_configs() -> dict[str, EvalConfig]:
    """Return all named benchmark configurations, including explicit candidates."""
    configs = (
        EvalConfig(
            name="baseline",
            tier1_model=settings.LLM_TIER1_MODEL,
            tier2_model=settings.LLM_TIER2_MODEL,
            provider=settings.LLM_PRIMARY_PROVIDER,
            base_url=settings.LLM_PRIMARY_BASE_URL or None,
        ),
        EvalConfig(
            name="alternative",
            tier1_model="gpt-4o-mini",
            tier2_model="gpt-4.1-nano",
        ),
        EvalConfig(
            name="tier1-gpt5-nano-minimal",
            tier1_model="gpt-5-nano",
            tier2_model=settings.LLM_TIER2_MODEL,
            provider=settings.LLM_PRIMARY_PROVIDER,
            base_url=settings.LLM_PRIMARY_BASE_URL or None,
            tier1_reasoning_effort="minimal",
        ),
        EvalConfig(
            name="tier1-gpt5-nano-low",
            tier1_model="gpt-5-nano",
            tier2_model=settings.LLM_TIER2_MODEL,
            provider=settings.LLM_PRIMARY_PROVIDER,
            base_url=settings.LLM_PRIMARY_BASE_URL or None,
            tier1_reasoning_effort="low",
        ),
        EvalConfig(
            name="tier2-gpt5-mini-low",
            tier1_model=settings.LLM_TIER1_MODEL,
            tier2_model="gpt-5-mini",
            provider=settings.LLM_PRIMARY_PROVIDER,
            base_url=settings.LLM_PRIMARY_BASE_URL or None,
            tier2_reasoning_effort="low",
        ),
        EvalConfig(
            name="tier2-gpt5-mini-medium",
            tier1_model=settings.LLM_TIER1_MODEL,
            tier2_model="gpt-5-mini",
            provider=settings.LLM_PRIMARY_PROVIDER,
            base_url=settings.LLM_PRIMARY_BASE_URL or None,
            tier2_reasoning_effort="medium",
        ),
    )
    return {config.name: config for config in configs}


def default_config_names() -> tuple[str, ...]:
    """Return the config names used when benchmark runs omit ``--config``."""
    return _DEFAULT_BENCHMARK_CONFIG_NAMES


def default_configs() -> list[EvalConfig]:
    """Return the default benchmark configs used when ``--config`` is omitted."""
    known = available_configs()
    return [known[name] for name in _DEFAULT_BENCHMARK_CONFIG_NAMES]


def _normalize_dispatch_mode(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {DISPATCH_MODE_REALTIME, DISPATCH_MODE_BATCH}
    if normalized not in allowed:
        msg = f"Unsupported dispatch mode '{value}'. Allowed: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized


def _normalize_request_priority(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {REQUEST_PRIORITY_REALTIME, REQUEST_PRIORITY_FLEX}
    if normalized not in allowed:
        msg = f"Unsupported request priority '{value}'. Allowed: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized


def _request_overrides_for_priority(priority: str) -> dict[str, Any] | None:
    if priority == REQUEST_PRIORITY_FLEX:
        return {"service_tier": "flex"}
    return None


def _merge_request_overrides(*overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for override in overrides:
        if isinstance(override, dict):
            merged.update(override)
    return merged or None


def _tier1_batch_settings_for_dispatch(dispatch_mode: str) -> tuple[int, str]:
    if dispatch_mode == DISPATCH_MODE_REALTIME:
        return (_SAFE_TIER1_BATCH_SIZE, _TIER1_BATCH_POLICY_SAFE_DEFAULT)
    return (_BATCH_DISPATCH_SIZE, _TIER1_BATCH_POLICY_DIAGNOSTIC)


def load_gold_set(
    path: Path,
    *,
    max_items: int | None = None,
    require_human_verified: bool = False,
) -> list[GoldSetItem]:
    """Load and validate a gold-set JSONL file."""
    if not path.exists():
        msg = f"Gold set file not found: {path}"
        raise FileNotFoundError(msg)

    rows: list[GoldSetItem] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            item = _parse_gold_item(payload, line_number=line_number)
            if require_human_verified and item.label_verification != HUMAN_VERIFIED_LABEL:
                continue
            rows.append(item)
            if max_items is not None and len(rows) >= max_items:
                break

    if not rows:
        if require_human_verified:
            msg = (
                "Gold set has no human-verified items. "
                "Add rows with label_verification='human_verified' or run without --require-human-verified."
            )
            raise ValueError(msg)
        msg = "Gold set is empty"
        raise ValueError(msg)
    return rows


def _count_label_verification(items: list[GoldSetItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = item.label_verification
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _parse_gold_item(payload: dict[str, Any], *, line_number: int) -> GoldSetItem:
    item_id = str(payload.get("item_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    label_verification_raw = str(payload.get("label_verification", "")).strip().lower()
    label_verification = label_verification_raw if label_verification_raw else "unknown"
    expected = payload.get("expected")
    if not item_id or not title or not content or not isinstance(expected, dict):
        msg = f"Invalid gold-set row at line {line_number}"
        raise ValueError(msg)

    tier1_raw = expected.get("tier1")
    if not isinstance(tier1_raw, dict):
        msg = f"Missing tier1 labels at line {line_number}"
        raise ValueError(msg)
    trend_scores_raw = tier1_raw.get("trend_scores")
    max_relevance_raw = tier1_raw.get("max_relevance")
    if not isinstance(trend_scores_raw, dict) or not isinstance(max_relevance_raw, int):
        msg = f"Invalid tier1 labels at line {line_number}"
        raise ValueError(msg)

    trend_scores: dict[str, int] = {}
    for trend_id, score in trend_scores_raw.items():
        trend_key = str(trend_id).strip()
        if not trend_key or not isinstance(score, int):
            msg = f"Invalid tier1 trend score at line {line_number}"
            raise ValueError(msg)
        trend_scores[trend_key] = score

    tier2_raw = expected.get("tier2")
    tier2_label: Tier2GoldLabel | None = None
    if tier2_raw is not None:
        if not isinstance(tier2_raw, dict):
            msg = f"Invalid tier2 labels at line {line_number}"
            raise ValueError(msg)
        try:
            tier2_label = Tier2GoldLabel(
                trend_id=str(tier2_raw["trend_id"]).strip(),
                signal_type=str(tier2_raw["signal_type"]).strip(),
                direction=str(tier2_raw["direction"]).strip(),
                severity=float(tier2_raw["severity"]),
                confidence=float(tier2_raw["confidence"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid tier2 labels at line {line_number}"
            raise ValueError(msg) from exc

    return GoldSetItem(
        item_id=item_id,
        title=title,
        content=content,
        label_verification=label_verification,
        tier1=Tier1GoldLabel(
            trend_scores=trend_scores,
            max_relevance=max_relevance_raw,
        ),
        tier2=tier2_label,
    )


def _resolve_configs(config_names: list[str] | None) -> list[EvalConfig]:
    if not config_names:
        return default_configs()
    known = available_configs()
    selected: list[EvalConfig] = []
    for name in config_names:
        key = name.strip().lower()
        config = known.get(key)
        if config is None:
            msg = f"Unknown benchmark config '{name}'. Available: {', '.join(sorted(known.keys()))}"
            raise ValueError(msg)
        selected.append(config)
    return selected


def _format_group_summary(grouped_items: dict[str, list[str]], *, limit: int = 8) -> str:
    ordered = sorted(grouped_items.items(), key=lambda entry: (-len(entry[1]), entry[0]))
    parts: list[str] = []
    for key, item_ids in ordered[:limit]:
        sample = ", ".join(sorted(item_ids)[:3])
        suffix = f", +{len(item_ids) - 3} more" if len(item_ids) > 3 else ""
        parts.append(f"{key}({len(item_ids)}; sample={sample}{suffix})")
    if len(ordered) > limit:
        parts.append(f"+{len(ordered) - limit} more")
    return ", ".join(parts)


def _load_trends_from_config(*, config_dir: Path) -> list[Any]:
    # Keep benchmark loader aligned with runtime canary + taxonomy utilities.
    return list(load_trends_from_config_dir(config_dir=config_dir))


def _assert_gold_set_taxonomy_alignment(*, items: list[GoldSetItem], trends: list[Any]) -> None:
    indicators_by_trend: dict[str, set[str]] = {}
    for trend in trends:
        trend_id = str(trend.definition.get("id", "")).strip()
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        indicators_by_trend[trend_id] = set(indicators.keys())

    configured_trend_ids = set(indicators_by_trend.keys())
    tier1_unknown_keys: dict[str, list[str]] = {}
    tier2_unknown_trend_ids: dict[str, list[str]] = {}
    tier2_unknown_signal_types: dict[str, list[str]] = {}

    for item in items:
        row_trend_keys = set(item.tier1.trend_scores.keys())
        for unknown_key in sorted(row_trend_keys - configured_trend_ids):
            tier1_unknown_keys.setdefault(unknown_key, []).append(item.item_id)

        if item.tier2 is None:
            continue
        if item.tier2.trend_id not in configured_trend_ids:
            tier2_unknown_trend_ids.setdefault(item.tier2.trend_id, []).append(item.item_id)
            continue

        expected_signal_types = indicators_by_trend[item.tier2.trend_id]
        if item.tier2.signal_type not in expected_signal_types:
            mismatch_key = f"{item.tier2.trend_id}:{item.tier2.signal_type}"
            tier2_unknown_signal_types.setdefault(mismatch_key, []).append(item.item_id)

    failures: list[str] = []
    if tier1_unknown_keys:
        failures.append(
            "Tier-1 trend_scores contains unknown trend_id values: "
            + _format_group_summary(tier1_unknown_keys)
        )
    if tier2_unknown_trend_ids:
        failures.append(
            "Tier-2 labels contain unknown trend_id values: "
            + _format_group_summary(tier2_unknown_trend_ids)
        )
    if tier2_unknown_signal_types:
        failures.append(
            "Tier-2 labels contain unknown signal_type values for configured trends: "
            + _format_group_summary(tier2_unknown_signal_types)
        )

    if failures:
        msg = "Benchmark taxonomy preflight failed:\n- " + "\n- ".join(failures)
        raise ValueError(msg)


def _item_uuid(item_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"horadus-eval/{item_id}")


def _build_raw_item(item: GoldSetItem) -> RawItem:
    raw_text = f"{item.title}\n\n{item.content}"
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return RawItem(
        id=_item_uuid(item.item_id),
        source_id=uuid5(NAMESPACE_URL, "horadus-eval/source"),
        external_id=item.item_id,
        url=f"https://eval.local/{item.item_id}",
        title=item.title,
        raw_content=raw_text,
        content_hash=content_hash,
        processing_status=ProcessingStatus.PENDING,
    )


def _build_event(item: GoldSetItem) -> Event:
    summary = item.content if len(item.content) <= 400 else f"{item.content[:400]}..."
    return Event(
        id=_item_uuid(item.item_id),
        canonical_summary=f"{item.title}. {summary}",
        event_summary=f"{item.title}. {summary}",
        source_count=1,
        unique_source_count=1,
    )


def _extract_first_impact(event: Event) -> Tier2GoldLabel | None:
    claims = event.extracted_claims
    if not isinstance(claims, dict):
        return None
    impacts = claims.get("trend_impacts")
    if not isinstance(impacts, list) or not impacts:
        return None
    first = impacts[0]
    if not isinstance(first, dict):
        return None
    try:
        return Tier2GoldLabel(
            trend_id=str(first["trend_id"]).strip(),
            signal_type=str(first["signal_type"]).strip(),
            direction=str(first["direction"]).strip(),
            severity=float(first["severity"]),
            confidence=float(first["confidence"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _build_openai_client(*, api_key: str, base_url: str | None) -> AsyncOpenAI:
    if not api_key.strip():
        msg = "An API key is required to run the benchmark"
        raise ValueError(msg)
    if isinstance(base_url, str) and base_url.strip():
        return AsyncOpenAI(api_key=api_key, base_url=base_url.strip())
    return AsyncOpenAI(api_key=api_key)


def _usage_to_dict(
    *, tier1_usage: Tier1Usage, tier2_usage: Tier2Usage, items_total: int
) -> dict[str, Any]:
    total_cost = tier1_usage.estimated_cost_usd + tier2_usage.estimated_cost_usd
    per_item = total_cost / items_total if items_total > 0 else 0.0
    return {
        "tier1_prompt_tokens": tier1_usage.prompt_tokens,
        "tier1_completion_tokens": tier1_usage.completion_tokens,
        "tier1_api_calls": tier1_usage.api_calls,
        "tier1_estimated_cost_usd": round(tier1_usage.estimated_cost_usd, 8),
        "tier1_active_provider": tier1_usage.active_provider,
        "tier1_active_model": tier1_usage.active_model,
        "tier1_active_reasoning_effort": tier1_usage.active_reasoning_effort,
        "tier1_used_secondary_route": tier1_usage.used_secondary_route,
        "tier2_prompt_tokens": tier2_usage.prompt_tokens,
        "tier2_completion_tokens": tier2_usage.completion_tokens,
        "tier2_api_calls": tier2_usage.api_calls,
        "tier2_estimated_cost_usd": round(tier2_usage.estimated_cost_usd, 8),
        "tier2_active_provider": tier2_usage.active_provider,
        "tier2_active_model": tier2_usage.active_model,
        "tier2_active_reasoning_effort": tier2_usage.active_reasoning_effort,
        "tier2_used_secondary_route": tier2_usage.used_secondary_route,
        "total_estimated_cost_usd": round(total_cost, 8),
        "estimated_cost_per_item_usd": round(per_item, 8),
    }


def _serialize_tier1_prediction(predicted: Tier1ItemResult) -> dict[str, Any]:
    return {
        "max_relevance": predicted.max_relevance,
        "should_queue_tier2": predicted.should_queue_tier2,
        "trend_scores": {score.trend_id: score.relevance_score for score in predicted.trend_scores},
    }


def _serialize_tier2_prediction(predicted: Tier2GoldLabel) -> dict[str, Any]:
    return {
        "trend_id": predicted.trend_id,
        "signal_type": predicted.signal_type,
        "direction": predicted.direction,
        "severity": predicted.severity,
        "confidence": predicted.confidence,
    }


def _extract_stage_raw_output(*, recorder: _BenchmarkResponseRecorder, subject: Any) -> str | None:
    if recorder.last_raw_output:
        return recorder.last_raw_output
    raw_output = getattr(subject, "_benchmark_last_raw_output", None)
    return raw_output if isinstance(raw_output, str) and raw_output.strip() else None


def _build_item_result(item: GoldSetItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "title": item.title,
        "label_verification": item.label_verification,
        "expected": {
            "tier1": {
                "trend_scores": item.tier1.trend_scores,
                "max_relevance": item.tier1.max_relevance,
            },
            "tier2": (_serialize_tier2_prediction(item.tier2) if item.tier2 is not None else None),
        },
        "tier1": None,
        "tier2": (
            {"status": "skipped", "reason": "no_tier2_gold_label"} if item.tier2 is None else None
        ),
    }


def _stage_failure(
    *,
    error_category: str,
    error_message: str,
    raw_model_output: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failure",
        "error_category": error_category,
        "error_message": error_message,
    }
    if raw_model_output is not None:
        payload["raw_model_output"] = raw_model_output
    return payload


def _stage_success(
    *,
    predicted: dict[str, Any],
    raw_model_output: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "success",
        "predicted": predicted,
    }
    if raw_model_output is not None:
        payload["raw_model_output"] = raw_model_output
    return payload


async def run_gold_set_benchmark(
    *,
    gold_set_path: str,
    output_dir: str,
    api_key: str,
    trend_config_dir: str = "config/trends",
    max_items: int = 200,
    config_names: list[str] | None = None,
    require_human_verified: bool = False,
    dispatch_mode: str = DISPATCH_MODE_REALTIME,
    request_priority: str = REQUEST_PRIORITY_REALTIME,
) -> Path:
    """
    Run Tier-1/Tier-2 benchmark over a gold set and persist JSON results.
    """
    gold_items = load_gold_set(
        Path(gold_set_path),
        max_items=max(1, max_items),
        require_human_verified=require_human_verified,
    )
    normalized_dispatch_mode = _normalize_dispatch_mode(dispatch_mode)
    normalized_request_priority = _normalize_request_priority(request_priority)
    priority_request_overrides = _request_overrides_for_priority(normalized_request_priority)
    tier1_batch_size, tier1_batch_policy = _tier1_batch_settings_for_dispatch(
        normalized_dispatch_mode
    )
    configs = _resolve_configs(config_names)
    trends = _load_trends_from_config(config_dir=Path(trend_config_dir))
    _assert_gold_set_taxonomy_alignment(items=gold_items, trends=trends)
    raw_items = [_build_raw_item(item) for item in gold_items]
    label_verification_counts = _count_label_verification(gold_items)
    trend_config_files = discover_trend_config_files(config_dir=Path(trend_config_dir))

    bounded_max_items = max(1, max_items)
    run_payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "gold_set_path": str(Path(gold_set_path)),
        "trend_config_dir": str(Path(trend_config_dir)),
        "items_evaluated": len(gold_items),
        "require_human_verified": require_human_verified,
        "dispatch_mode": dispatch_mode,
        "request_priority": request_priority,
        "label_verification_counts": label_verification_counts,
        "dataset_scope": {
            "max_items": bounded_max_items,
            "require_human_verified": require_human_verified,
            "tier1_label_mode": "sparse_allowed",
        },
        "execution_mode": {
            "dispatch_mode": normalized_dispatch_mode,
            "request_priority": normalized_request_priority,
            "tier1_batch_size": tier1_batch_size,
            "tier1_batch_policy": tier1_batch_policy,
        },
        "source_control": provenance.build_source_control_provenance(),
        "prompt_provenance": provenance.build_file_manifest_provenance(
            {"tier1": _TIER1_PROMPT_PATH, "tier2": _TIER2_PROMPT_PATH}
        ),
        "trend_config_provenance": provenance.build_directory_provenance(
            directory=Path(trend_config_dir),
            files=trend_config_files,
        ),
        "gold_set_fingerprint_sha256": provenance.gold_set_fingerprint(gold_items),
        "gold_set_item_ids_sha256": provenance.gold_set_item_ids_fingerprint(gold_items),
        "configs": [],
    }

    for config in configs:
        config_started_at = perf_counter()
        client = _build_openai_client(api_key=api_key, base_url=config.base_url)
        noop_session = _NoopSession()
        noop_cost_tracker = _NoopCostTracker()
        disabled_semantic_cache = LLMSemanticCache(enabled=False)
        tier1_recorder = _BenchmarkResponseRecorder()
        tier2_recorder = _BenchmarkResponseRecorder()
        tier1_request_overrides = _merge_request_overrides(
            priority_request_overrides,
            config.tier1_request_overrides,
        )
        tier2_request_overrides = _merge_request_overrides(
            priority_request_overrides,
            config.tier2_request_overrides,
        )
        tier1_secondary_client = _build_benchmark_secondary_client(
            primary_api_key=api_key,
            secondary_model=settings.LLM_TIER1_SECONDARY_MODEL,
            recorder=tier1_recorder,
        )
        tier2_secondary_client = _build_benchmark_secondary_client(
            primary_api_key=api_key,
            secondary_model=settings.LLM_TIER2_SECONDARY_MODEL,
            recorder=tier2_recorder,
        )
        tier1 = Tier1Classifier(
            session=cast("Any", noop_session),
            client=_wrap_client_with_recorder(client=client, recorder=tier1_recorder),
            model=config.tier1_model,
            batch_size=tier1_batch_size,
            prompt_path=_TIER1_PROMPT_PATH,
            cost_tracker=cast("Any", noop_cost_tracker),
            reasoning_effort=config.tier1_reasoning_effort,
            request_overrides=tier1_request_overrides,
            secondary_client=tier1_secondary_client,
            semantic_cache=disabled_semantic_cache,
        )
        tier2 = Tier2Classifier(
            session=cast("Any", noop_session),
            client=_wrap_client_with_recorder(client=client, recorder=tier2_recorder),
            model=config.tier2_model,
            prompt_path=_TIER2_PROMPT_PATH,
            cost_tracker=cast("Any", noop_cost_tracker),
            reasoning_effort=config.tier2_reasoning_effort,
            request_overrides=tier2_request_overrides,
            secondary_client=tier2_secondary_client,
            semantic_cache=disabled_semantic_cache,
        )

        tier1_metrics = _Tier1Metrics(queue_threshold=settings.TIER1_RELEVANCE_THRESHOLD)
        tier1_usage = Tier1Usage()
        item_results_by_id = {item.item_id: _build_item_result(item) for item in gold_items}
        for batch_start in range(0, len(gold_items), tier1_batch_size):
            item_batch = gold_items[batch_start : batch_start + tier1_batch_size]
            raw_batch = raw_items[batch_start : batch_start + tier1_batch_size]
            tier1_recorder.reset()
            try:
                tier1_results, tier1_call_usage = await tier1.classify_items(raw_batch, trends)
            except ValueError as exc:
                raw_output = _extract_stage_raw_output(recorder=tier1_recorder, subject=tier1)
                for item in item_batch:
                    tier1_metrics.record_failure(gold=item)
                    item_results_by_id[item.item_id]["tier1"] = _stage_failure(
                        error_category=type(exc).__name__,
                        error_message=str(exc),
                        raw_model_output=raw_output,
                    )
                continue

            tier1_usage.prompt_tokens += tier1_call_usage.prompt_tokens
            tier1_usage.completion_tokens += tier1_call_usage.completion_tokens
            tier1_usage.api_calls += tier1_call_usage.api_calls
            tier1_usage.estimated_cost_usd += tier1_call_usage.estimated_cost_usd
            apply_latest_active_route_metadata(
                target_usage=tier1_usage,
                source_usage=tier1_call_usage,
            )
            tier1_usage.used_secondary_route = (
                tier1_usage.used_secondary_route or tier1_call_usage.used_secondary_route
            )

            predictions_by_item = {result.item_id: result for result in tier1_results}
            for item in item_batch:
                prediction = predictions_by_item.get(_item_uuid(item.item_id))
                if prediction is None:
                    tier1_metrics.record_failure(gold=item)
                    item_results_by_id[item.item_id]["tier1"] = _stage_failure(
                        error_category="MissingPrediction",
                        error_message="Tier 1 benchmark received no prediction for input item",
                        raw_model_output=_extract_stage_raw_output(
                            recorder=tier1_recorder,
                            subject=tier1,
                        ),
                    )
                    continue

                tier1_metrics.record(gold=item, predicted=prediction)
                item_results_by_id[item.item_id]["tier1"] = _stage_success(
                    predicted=_serialize_tier1_prediction(prediction),
                    raw_model_output=_extract_stage_raw_output(
                        recorder=tier1_recorder,
                        subject=tier1,
                    ),
                )

        tier2_metrics = _Tier2Metrics()
        tier2_usage = Tier2Usage()
        for item in gold_items:
            if item.tier2 is None:
                continue

            event = _build_event(item)
            tier2_recorder.reset()
            try:
                _, tier2_call_usage = await tier2.classify_event(
                    event=event,
                    trends=trends,
                    context_chunks=[f"{item.title}\n\n{item.content}"],
                )
            except ValueError as exc:
                tier2_metrics.record(expected=item.tier2, predicted=None)
                item_results_by_id[item.item_id]["tier2"] = _stage_failure(
                    error_category=type(exc).__name__,
                    error_message=str(exc),
                    raw_model_output=_extract_stage_raw_output(
                        recorder=tier2_recorder,
                        subject=tier2,
                    ),
                )
                continue
            tier2_usage.prompt_tokens += tier2_call_usage.prompt_tokens
            tier2_usage.completion_tokens += tier2_call_usage.completion_tokens
            tier2_usage.api_calls += tier2_call_usage.api_calls
            tier2_usage.estimated_cost_usd += tier2_call_usage.estimated_cost_usd
            apply_latest_active_route_metadata(
                target_usage=tier2_usage,
                source_usage=tier2_call_usage,
            )
            tier2_usage.used_secondary_route = (
                tier2_usage.used_secondary_route or tier2_call_usage.used_secondary_route
            )

            tier2_prediction = _extract_first_impact(event)
            tier2_metrics.record(expected=item.tier2, predicted=tier2_prediction)
            if tier2_prediction is None:
                item_results_by_id[item.item_id]["tier2"] = _stage_failure(
                    error_category="MissingPrediction",
                    error_message="Tier 2 benchmark received no trend impact prediction",
                    raw_model_output=_extract_stage_raw_output(
                        recorder=tier2_recorder,
                        subject=tier2,
                    ),
                )
            else:
                item_results_by_id[item.item_id]["tier2"] = _stage_success(
                    predicted=_serialize_tier2_prediction(tier2_prediction),
                    raw_model_output=_extract_stage_raw_output(
                        recorder=tier2_recorder,
                        subject=tier2,
                    ),
                )

        tier2_usage.estimated_cost_usd = round(tier2_usage.estimated_cost_usd, 8)
        run_payload["configs"].append(
            {
                "name": config.name,
                "provider": config.provider,
                "tier1_model": config.tier1_model,
                "tier2_model": config.tier2_model,
                "tier1_api_mode": "chat_completions",
                "tier2_api_mode": "chat_completions",
                "tier1_reasoning_effort": config.tier1_reasoning_effort,
                "tier2_reasoning_effort": config.tier2_reasoning_effort,
                "tier1_request_overrides": provenance.normalize_request_overrides(
                    tier1_request_overrides
                ),
                "tier2_request_overrides": provenance.normalize_request_overrides(
                    tier2_request_overrides
                ),
                "elapsed_seconds": round(perf_counter() - config_started_at, 6),
                "tier1_metrics": tier1_metrics.to_dict(),
                "tier2_metrics": tier2_metrics.to_dict(),
                "usage": _usage_to_dict(
                    tier1_usage=tier1_usage,
                    tier2_usage=tier2_usage,
                    items_total=len(gold_items),
                ),
                "item_results": [item_results_by_id[item.item_id] for item in gold_items],
            }
        )

    return _write_result(output_dir=Path(output_dir), payload=run_payload)


def _write_result(*, output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"benchmark-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
