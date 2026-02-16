"""
Gold-set benchmarking utilities for Tier-1/Tier-2 model configurations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from openai import AsyncOpenAI

from src.core.config import settings
from src.processing.tier1_classifier import Tier1Classifier, Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import (
    Tier2Classifier,
    Tier2Usage,
)
from src.storage.models import Event, ProcessingStatus, RawItem

HUMAN_VERIFIED_LABEL = "human_verified"


@dataclass(slots=True)
class EvalConfig:
    """Benchmark configuration for a Tier-1/Tier-2 model pair."""

    name: str
    tier1_model: str
    tier2_model: str
    provider: str = "openai"
    base_url: str | None = None


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
    async def ensure_within_budget(self, _tier: str) -> None:
        return None

    async def record_usage(
        self,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        _ = (tier, input_tokens, output_tokens)
        return


DEFAULT_CONFIGS: tuple[EvalConfig, EvalConfig] = (
    EvalConfig(
        name="baseline",
        tier1_model="gpt-4.1-nano",
        tier2_model="gpt-4o-mini",
    ),
    EvalConfig(
        name="alternative",
        tier1_model="gpt-4o-mini",
        tier2_model="gpt-4.1-nano",
    ),
)


def available_configs() -> dict[str, EvalConfig]:
    """Return default named benchmark configurations."""
    return {config.name: config for config in DEFAULT_CONFIGS}


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


def _gold_set_fingerprint(items: list[GoldSetItem]) -> str:
    canonical_rows: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {
            "item_id": item.item_id,
            "title": item.title,
            "content": item.content,
            "label_verification": item.label_verification,
            "tier1": {
                "trend_scores": item.tier1.trend_scores,
                "max_relevance": item.tier1.max_relevance,
            },
        }
        if item.tier2 is not None:
            row["tier2"] = {
                "trend_id": item.tier2.trend_id,
                "signal_type": item.tier2.signal_type,
                "direction": item.tier2.direction,
                "severity": item.tier2.severity,
                "confidence": item.tier2.confidence,
            }
        else:
            row["tier2"] = None
        canonical_rows.append(row)

    payload = json.dumps(canonical_rows, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _gold_set_item_ids_fingerprint(items: list[GoldSetItem]) -> str:
    normalized_ids = "\n".join(sorted(item.item_id for item in items))
    return hashlib.sha256(normalized_ids.encode("utf-8")).hexdigest()


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
        return list(DEFAULT_CONFIGS)
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


def _build_trends() -> list[Any]:
    return [
        SimpleNamespace(
            id=uuid5(NAMESPACE_URL, "trend/eu-russia"),
            name="EU-Russia",
            definition={"id": "eu-russia"},
            indicators={
                "military_movement": {
                    "direction": "escalatory",
                    "keywords": ["troops", "deployment", "border", "artillery"],
                },
                "diplomatic_breakdown": {
                    "direction": "escalatory",
                    "keywords": ["talks", "sanctions", "ultimatum"],
                },
            },
        ),
        SimpleNamespace(
            id=uuid5(NAMESPACE_URL, "trend/us-china"),
            name="US-China",
            definition={"id": "us-china"},
            indicators={
                "diplomatic_engagement": {
                    "direction": "de_escalatory",
                    "keywords": ["summit", "dialogue", "talks", "agreement"],
                },
                "trade_restriction": {
                    "direction": "escalatory",
                    "keywords": ["tariff", "export controls", "restrictions"],
                },
            },
        ),
        SimpleNamespace(
            id=uuid5(NAMESPACE_URL, "trend/middle-east"),
            name="Middle East",
            definition={"id": "middle-east"},
            indicators={
                "energy_disruption": {
                    "direction": "escalatory",
                    "keywords": ["pipeline", "oil", "shipping", "strait"],
                },
                "ceasefire": {
                    "direction": "de_escalatory",
                    "keywords": ["ceasefire", "mediation", "truce"],
                },
            },
        ),
    ]


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
        "tier2_prompt_tokens": tier2_usage.prompt_tokens,
        "tier2_completion_tokens": tier2_usage.completion_tokens,
        "tier2_api_calls": tier2_usage.api_calls,
        "tier2_estimated_cost_usd": round(tier2_usage.estimated_cost_usd, 8),
        "total_estimated_cost_usd": round(total_cost, 8),
        "estimated_cost_per_item_usd": round(per_item, 8),
    }


async def run_gold_set_benchmark(
    *,
    gold_set_path: str,
    output_dir: str,
    api_key: str,
    max_items: int = 200,
    config_names: list[str] | None = None,
    require_human_verified: bool = False,
    dispatch_mode: str = "realtime",
    request_priority: str = "realtime",
) -> Path:
    """
    Run Tier-1/Tier-2 benchmark over a gold set and persist JSON results.
    """
    gold_items = load_gold_set(
        Path(gold_set_path),
        max_items=max(1, max_items),
        require_human_verified=require_human_verified,
    )
    configs = _resolve_configs(config_names)
    trends = _build_trends()
    raw_items = [_build_raw_item(item) for item in gold_items]
    label_verification_counts = _count_label_verification(gold_items)

    bounded_max_items = max(1, max_items)
    run_payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "gold_set_path": str(Path(gold_set_path)),
        "items_evaluated": len(gold_items),
        "require_human_verified": require_human_verified,
        "dispatch_mode": dispatch_mode,
        "request_priority": request_priority,
        "label_verification_counts": label_verification_counts,
        "dataset_scope": {
            "max_items": bounded_max_items,
            "require_human_verified": require_human_verified,
        },
        "gold_set_fingerprint_sha256": _gold_set_fingerprint(gold_items),
        "gold_set_item_ids_sha256": _gold_set_item_ids_fingerprint(gold_items),
        "configs": [],
    }

    for config in configs:
        client = _build_openai_client(api_key=api_key, base_url=config.base_url)
        noop_session = _NoopSession()
        noop_cost_tracker = _NoopCostTracker()
        tier1 = Tier1Classifier(
            session=cast("Any", noop_session),
            client=client,
            model=config.tier1_model,
            batch_size=1,
            cost_tracker=cast("Any", noop_cost_tracker),
        )
        tier2 = Tier2Classifier(
            session=cast("Any", noop_session),
            client=client,
            model=config.tier2_model,
            cost_tracker=cast("Any", noop_cost_tracker),
        )

        tier1_metrics = _Tier1Metrics(queue_threshold=settings.TIER1_RELEVANCE_THRESHOLD)
        tier1_usage = Tier1Usage()
        for item, raw_item in zip(gold_items, raw_items, strict=True):
            try:
                tier1_results, tier1_call_usage = await tier1.classify_items([raw_item], trends)
            except ValueError:
                tier1_metrics.record_failure(gold=item)
                continue

            tier1_usage.prompt_tokens += tier1_call_usage.prompt_tokens
            tier1_usage.completion_tokens += tier1_call_usage.completion_tokens
            tier1_usage.api_calls += tier1_call_usage.api_calls
            tier1_usage.estimated_cost_usd += tier1_call_usage.estimated_cost_usd

            prediction = next(
                (result for result in tier1_results if result.item_id == _item_uuid(item.item_id)),
                None,
            )
            if prediction is None:
                tier1_metrics.record_failure(gold=item)
                continue

            tier1_metrics.record(gold=item, predicted=prediction)

        tier2_metrics = _Tier2Metrics()
        tier2_usage = Tier2Usage()
        for item in gold_items:
            if item.tier2 is None:
                continue

            event = _build_event(item)
            try:
                _, tier2_call_usage = await tier2.classify_event(
                    event=event,
                    trends=trends,
                    context_chunks=[f"{item.title}\n\n{item.content}"],
                )
            except ValueError:
                tier2_metrics.record(expected=item.tier2, predicted=None)
                continue
            tier2_usage.prompt_tokens += tier2_call_usage.prompt_tokens
            tier2_usage.completion_tokens += tier2_call_usage.completion_tokens
            tier2_usage.api_calls += tier2_call_usage.api_calls
            tier2_usage.estimated_cost_usd += tier2_call_usage.estimated_cost_usd

            tier2_prediction = _extract_first_impact(event)
            tier2_metrics.record(expected=item.tier2, predicted=tier2_prediction)

        tier2_usage.estimated_cost_usd = round(tier2_usage.estimated_cost_usd, 8)
        run_payload["configs"].append(
            {
                "name": config.name,
                "provider": config.provider,
                "tier1_model": config.tier1_model,
                "tier2_model": config.tier2_model,
                "tier1_metrics": tier1_metrics.to_dict(),
                "tier2_metrics": tier2_metrics.to_dict(),
                "usage": _usage_to_dict(
                    tier1_usage=tier1_usage,
                    tier2_usage=tier2_usage,
                    items_total=len(gold_items),
                ),
            }
        )

    return _write_result(output_dir=Path(output_dir), payload=run_payload)


def _write_result(*, output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"benchmark-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
