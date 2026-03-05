"""
Tier-2 gold-set canary for detecting primary-model quality drift.

This is a coarse guardrail intended to catch major regressions (schema/validation
failures, taxonomy mismatches, large accuracy drops) before bulk trend deltas are
applied.

It deliberately uses a small fixed subset of Tier-2-labeled gold-set items to
keep cost bounded and results comparable run-to-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import structlog
from openai import AsyncOpenAI

from src.core.config import settings
from src.core.trend_config_loader import load_trends_from_config_dir
from src.eval.benchmark import HUMAN_VERIFIED_LABEL, GoldSetItem, Tier2GoldLabel, load_gold_set
from src.processing.cost_tracker import TIER2
from src.processing.tier2_classifier import Tier2Classifier
from src.storage.models import Event

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Tier2CanaryMetrics:
    items_total: int
    failures: int
    trend_match_accuracy: float
    signal_type_accuracy: float
    direction_accuracy: float
    severity_mae: float
    confidence_mae: float


@dataclass(frozen=True, slots=True)
class Tier2CanaryResult:
    model: str
    passed: bool
    metrics: Tier2CanaryMetrics
    reason: str


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


def _event_for_item(item: GoldSetItem) -> Event:
    summary = item.content if len(item.content) <= 400 else f"{item.content[:400]}..."
    return Event(
        id=uuid5(NAMESPACE_URL, f"horadus-canary/{item.item_id}"),
        canonical_summary=f"{item.title}. {summary}",
        source_count=1,
        unique_source_count=1,
    )


def _extract_first_impact(event: Event) -> Tier2GoldLabel | None:
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    impacts = claims.get("trend_impacts", [])
    if not isinstance(impacts, list) or not impacts:
        return None
    first = impacts[0]
    if not isinstance(first, dict):
        return None
    try:
        return Tier2GoldLabel(
            trend_id=str(first.get("trend_id", "")),
            signal_type=str(first.get("signal_type", "")),
            direction=str(first.get("direction", "")),
            severity=float(first.get("severity", 0.0) or 0.0),
            confidence=float(first.get("confidence", 0.0) or 0.0),
        )
    except (TypeError, ValueError):
        return None


def _select_tier2_items(items: list[GoldSetItem], *, max_items: int) -> list[GoldSetItem]:
    tier2_items = [
        item
        for item in items
        if item.label_verification == HUMAN_VERIFIED_LABEL and item.tier2 is not None
    ]
    tier2_items.sort(key=lambda item: item.item_id)
    return tier2_items[: max(1, max_items)]


def _evaluate_pass(metrics: Tier2CanaryMetrics) -> tuple[bool, str]:
    if metrics.items_total <= 0:
        return (False, "no_items")

    failure_rate = metrics.failures / metrics.items_total
    if failure_rate > settings.LLM_DEGRADED_CANARY_MAX_FAILURE_RATE:
        return (False, f"failure_rate:{failure_rate:.3f}")
    if metrics.trend_match_accuracy < settings.LLM_DEGRADED_CANARY_MIN_TREND_MATCH_ACCURACY:
        return (False, f"trend_match_accuracy:{metrics.trend_match_accuracy:.3f}")
    if metrics.signal_type_accuracy < settings.LLM_DEGRADED_CANARY_MIN_SIGNAL_TYPE_ACCURACY:
        return (False, f"signal_type_accuracy:{metrics.signal_type_accuracy:.3f}")
    if metrics.direction_accuracy < settings.LLM_DEGRADED_CANARY_MIN_DIRECTION_ACCURACY:
        return (False, f"direction_accuracy:{metrics.direction_accuracy:.3f}")
    if metrics.severity_mae > settings.LLM_DEGRADED_CANARY_MAX_SEVERITY_MAE:
        return (False, f"severity_mae:{metrics.severity_mae:.3f}")
    if metrics.confidence_mae > settings.LLM_DEGRADED_CANARY_MAX_CONFIDENCE_MAE:
        return (False, f"confidence_mae:{metrics.confidence_mae:.3f}")
    return (True, "ok")


async def run_tier2_canary(
    *,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    gold_set_path: str | None = None,
    trend_config_dir: str = "config/trends",
    max_items: int | None = None,
    request_overrides: dict[str, Any] | None = None,
) -> Tier2CanaryResult:
    resolved_key = (api_key or settings.OPENAI_API_KEY or "").strip()
    if not resolved_key:
        metrics = Tier2CanaryMetrics(
            items_total=0,
            failures=0,
            trend_match_accuracy=0.0,
            signal_type_accuracy=0.0,
            direction_accuracy=0.0,
            severity_mae=0.0,
            confidence_mae=0.0,
        )
        return Tier2CanaryResult(
            model=model,
            passed=False,
            metrics=metrics,
            reason="missing_api_key",
        )

    dataset_path = Path(gold_set_path or settings.LLM_DEGRADED_CANARY_GOLD_SET_PATH)
    items = load_gold_set(
        dataset_path,
        max_items=200,
        require_human_verified=False,
    )
    selected = _select_tier2_items(
        items,
        max_items=(
            max_items if max_items is not None else settings.LLM_DEGRADED_CANARY_MAX_TIER2_ITEMS
        ),
    )
    if not selected:
        metrics = Tier2CanaryMetrics(
            items_total=0,
            failures=0,
            trend_match_accuracy=0.0,
            signal_type_accuracy=0.0,
            direction_accuracy=0.0,
            severity_mae=0.0,
            confidence_mae=0.0,
        )
        return Tier2CanaryResult(
            model=model, passed=False, metrics=metrics, reason="empty_selection"
        )

    trends = load_trends_from_config_dir(config_dir=Path(trend_config_dir))
    if isinstance(base_url, str) and base_url.strip():
        client = AsyncOpenAI(api_key=resolved_key, base_url=base_url.strip())
    else:
        client = AsyncOpenAI(api_key=resolved_key)
    tier2 = Tier2Classifier(
        session=_NoopSession(),  # type: ignore[arg-type]
        client=client,
        model=model,
        secondary_model=None,  # primary-only canary
        cost_tracker=_NoopCostTracker(),  # type: ignore[arg-type]
        request_overrides=request_overrides,
    )

    failures = 0
    match_trend = 0
    match_signal = 0
    match_direction = 0
    severity_abs_error = 0.0
    confidence_abs_error = 0.0

    for item in selected:
        event = _event_for_item(item)
        expected = item.tier2
        if expected is None:
            continue
        try:
            await tier2.classify_event(
                event=event,
                trends=trends,  # type: ignore[arg-type]
                context_chunks=[f"{item.title}\n\n{item.content}"],
            )
        except Exception:
            failures += 1
            severity_abs_error += abs(0.0 - expected.severity)
            confidence_abs_error += abs(0.0 - expected.confidence)
            continue

        predicted = _extract_first_impact(event)
        if predicted is None:
            failures += 1
            severity_abs_error += abs(0.0 - expected.severity)
            confidence_abs_error += abs(0.0 - expected.confidence)
            continue

        if predicted.trend_id == expected.trend_id:
            match_trend += 1
        if predicted.signal_type == expected.signal_type:
            match_signal += 1
        if predicted.direction == expected.direction:
            match_direction += 1
        severity_abs_error += abs(predicted.severity - expected.severity)
        confidence_abs_error += abs(predicted.confidence - expected.confidence)

    denominator = len(selected) if selected else 1
    metrics = Tier2CanaryMetrics(
        items_total=denominator,
        failures=failures,
        trend_match_accuracy=match_trend / denominator,
        signal_type_accuracy=match_signal / denominator,
        direction_accuracy=match_direction / denominator,
        severity_mae=severity_abs_error / denominator,
        confidence_mae=confidence_abs_error / denominator,
    )
    passed, reason = _evaluate_pass(metrics)
    logger.info(
        "Tier-2 canary completed",
        stage=TIER2,
        model=model,
        passed=passed,
        reason=reason,
        items_total=metrics.items_total,
        failures=metrics.failures,
        trend_match_accuracy=round(metrics.trend_match_accuracy, 6),
        signal_type_accuracy=round(metrics.signal_type_accuracy, 6),
        direction_accuracy=round(metrics.direction_accuracy, 6),
        severity_mae=round(metrics.severity_mae, 6),
        confidence_mae=round(metrics.confidence_mae, 6),
    )
    return Tier2CanaryResult(model=model, passed=passed, metrics=metrics, reason=reason)
