"""
Historical replay and champion/challenger comparison harness.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select

from src.core.calibration import calculate_brier_score, normalize_utc
from src.storage.database import async_session_maker
from src.storage.models import (
    Event,
    EventItem,
    OutcomeType,
    RawItem,
    TrendEvidence,
    TrendOutcome,
    TrendSnapshot,
)


@dataclass(slots=True)
class ReplayConfig:
    """Replay policy profile for champion/challenger comparisons."""

    name: str
    decision_threshold: float
    abstain_lower: float | None = None
    abstain_upper: float | None = None
    estimated_cost_per_decision_usd: float = 0.0
    estimated_latency_per_decision_ms: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.decision_threshold <= 1.0:
            msg = "decision_threshold must be within [0, 1]"
            raise ValueError(msg)
        if self.abstain_lower is not None and not 0.0 <= self.abstain_lower <= 1.0:
            msg = "abstain_lower must be within [0, 1]"
            raise ValueError(msg)
        if self.abstain_upper is not None and not 0.0 <= self.abstain_upper <= 1.0:
            msg = "abstain_upper must be within [0, 1]"
            raise ValueError(msg)
        if (
            self.abstain_lower is not None
            and self.abstain_upper is not None
            and self.abstain_lower > self.abstain_upper
        ):
            msg = "abstain_lower must be <= abstain_upper"
            raise ValueError(msg)
        if self.estimated_cost_per_decision_usd < 0:
            msg = "estimated_cost_per_decision_usd must be >= 0"
            raise ValueError(msg)
        if self.estimated_latency_per_decision_ms < 0:
            msg = "estimated_latency_per_decision_ms must be >= 0"
            raise ValueError(msg)


@dataclass(slots=True)
class _ReplayPoint:
    probability: float
    actual_value: float
    brier_score: float
    binary_actual: int | None


DEFAULT_REPLAY_CONFIGS: tuple[ReplayConfig, ReplayConfig] = (
    ReplayConfig(
        name="stable",
        decision_threshold=0.50,
        abstain_lower=0.45,
        abstain_upper=0.55,
        estimated_cost_per_decision_usd=0.00018,
        estimated_latency_per_decision_ms=260,
    ),
    ReplayConfig(
        name="fast_lower_threshold",
        decision_threshold=0.45,
        abstain_lower=0.40,
        abstain_upper=0.50,
        estimated_cost_per_decision_usd=0.00014,
        estimated_latency_per_decision_ms=190,
    ),
)


def available_replay_configs() -> dict[str, ReplayConfig]:
    """Return available named replay policy profiles."""
    return {config.name: config for config in DEFAULT_REPLAY_CONFIGS}


def _resolve_replay_config(name: str) -> ReplayConfig:
    key = name.strip().lower()
    known = available_replay_configs()
    config = known.get(key)
    if config is None:
        msg = f"Unknown replay config '{name}'. Available: {', '.join(sorted(known.keys()))}"
        raise ValueError(msg)
    return config


def _actual_outcome_value(raw_outcome: str | None) -> float | None:
    if raw_outcome is None:
        return None
    try:
        outcome = OutcomeType(raw_outcome)
    except ValueError:
        return None
    if outcome == OutcomeType.OCCURRED:
        return 1.0
    if outcome == OutcomeType.DID_NOT_OCCUR:
        return 0.0
    if outcome == OutcomeType.PARTIAL:
        return 0.5
    return None


def _binary_actual(raw_outcome: str | None) -> int | None:
    if raw_outcome is None:
        return None
    try:
        outcome = OutcomeType(raw_outcome)
    except ValueError:
        return None
    if outcome == OutcomeType.OCCURRED:
        return 1
    if outcome == OutcomeType.DID_NOT_OCCUR:
        return 0
    return None


def _build_replay_points(outcomes: list[TrendOutcome]) -> list[_ReplayPoint]:
    points: list[_ReplayPoint] = []
    for outcome in outcomes:
        probability = float(outcome.predicted_probability)
        raw_outcome = outcome.outcome
        if raw_outcome is None:
            continue
        actual_value = _actual_outcome_value(raw_outcome)
        if actual_value is None:
            continue

        brier_score = (
            float(outcome.brier_score)
            if outcome.brier_score is not None
            else calculate_brier_score(
                predicted_probability=probability,
                outcome=OutcomeType(raw_outcome),
            )
        )
        if brier_score is None:
            continue

        points.append(
            _ReplayPoint(
                probability=probability,
                actual_value=actual_value,
                brier_score=float(brier_score),
                binary_actual=_binary_actual(raw_outcome),
            )
        )
    return points


def _decision_for_probability(probability: float, config: ReplayConfig) -> str:
    if (
        config.abstain_lower is not None
        and config.abstain_upper is not None
        and config.abstain_lower <= probability <= config.abstain_upper
    ):
        return "abstain"
    if probability >= config.decision_threshold:
        return "positive"
    return "negative"


def _evaluate_policy(config: ReplayConfig, points: list[_ReplayPoint]) -> dict[str, Any]:
    true_positive = 0
    true_negative = 0
    false_positive = 0
    false_negative = 0
    abstentions = 0
    binary_items = 0
    decision_items = 0

    for point in points:
        decision = _decision_for_probability(point.probability, config)
        if point.binary_actual is None:
            continue
        binary_items += 1
        if decision == "abstain":
            abstentions += 1
            continue

        decision_items += 1
        if decision == "positive" and point.binary_actual == 1:
            true_positive += 1
        elif decision == "negative" and point.binary_actual == 0:
            true_negative += 1
        elif decision == "positive" and point.binary_actual == 0:
            false_positive += 1
        elif decision == "negative" and point.binary_actual == 1:
            false_negative += 1

    accuracy = (true_positive + true_negative) / decision_items if decision_items > 0 else 0.0
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else 0.0
    )
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    mean_brier = sum(point.brier_score for point in points) / len(points) if points else 0.0
    mean_abs_calibration_error = (
        sum(abs(point.probability - point.actual_value) for point in points) / len(points)
        if points
        else 0.0
    )

    estimated_cost = decision_items * config.estimated_cost_per_decision_usd
    estimated_latency_total_ms = decision_items * config.estimated_latency_per_decision_ms
    latency_per_decision = float(config.estimated_latency_per_decision_ms)
    abstain_ratio = abstentions / binary_items if binary_items > 0 else 0.0

    return {
        "quality": {
            "scored_outcomes": len(points),
            "binary_outcomes": binary_items,
            "decisions_made": decision_items,
            "abstentions": abstentions,
            "abstain_ratio": round(abstain_ratio, 6),
            "decision_accuracy": round(accuracy, 6),
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1_score": round(f1_score, 6),
            "mean_brier_score": round(mean_brier, 6),
            "mean_abs_calibration_error": round(mean_abs_calibration_error, 6),
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "cost": {
            "estimated_cost_per_decision_usd": round(config.estimated_cost_per_decision_usd, 8),
            "estimated_total_cost_usd": round(estimated_cost, 8),
        },
        "latency": {
            "estimated_latency_per_decision_ms": config.estimated_latency_per_decision_ms,
            "estimated_total_latency_ms": estimated_latency_total_ms,
            "estimated_p50_latency_ms": latency_per_decision if decision_items > 0 else 0.0,
            "estimated_p95_latency_ms": latency_per_decision if decision_items > 0 else 0.0,
        },
    }


def _numeric_deltas(champion: dict[str, Any], challenger: dict[str, Any]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for key, champion_value in champion.items():
        challenger_value = challenger.get(key)
        if isinstance(champion_value, int | float) and isinstance(challenger_value, int | float):
            deltas[key] = round(float(challenger_value) - float(champion_value), 6)
    return deltas


def _assess_promotion(
    *,
    champion_metrics: dict[str, Any],
    challenger_metrics: dict[str, Any],
) -> dict[str, Any]:
    champion_quality = champion_metrics["quality"]
    challenger_quality = challenger_metrics["quality"]
    champion_cost = champion_metrics["cost"]
    challenger_cost = challenger_metrics["cost"]
    champion_latency = champion_metrics["latency"]
    challenger_latency = challenger_metrics["latency"]

    reasons: list[str] = []
    recommended = True

    accuracy_delta = float(challenger_quality["decision_accuracy"]) - float(
        champion_quality["decision_accuracy"]
    )
    if accuracy_delta < -0.01:
        recommended = False
        reasons.append("Decision accuracy regressed by more than 0.01.")

    brier_delta = float(challenger_quality["mean_brier_score"]) - float(
        champion_quality["mean_brier_score"]
    )
    if brier_delta > 0.01:
        recommended = False
        reasons.append("Mean Brier score worsened by more than 0.01.")

    champion_total_cost = float(champion_cost["estimated_total_cost_usd"])
    challenger_total_cost = float(challenger_cost["estimated_total_cost_usd"])
    if champion_total_cost > 0 and challenger_total_cost > champion_total_cost * 1.20:
        recommended = False
        reasons.append("Estimated replay cost increased by more than 20%.")

    champion_p95_latency = float(champion_latency["estimated_p95_latency_ms"])
    challenger_p95_latency = float(challenger_latency["estimated_p95_latency_ms"])
    if champion_p95_latency > 0 and challenger_p95_latency > champion_p95_latency * 1.20:
        recommended = False
        reasons.append("Estimated p95 latency increased by more than 20%.")

    if recommended:
        reasons.append("Challenger meets replay promotion gates for quality/cost/latency.")

    return {
        "recommended": recommended,
        "reasons": reasons,
    }


async def _load_dataset_counts(
    *,
    period_start: datetime,
    period_end: datetime,
    trend_id: UUID | None,
) -> dict[str, int]:
    async with async_session_maker() as session:
        if trend_id is None:
            raw_items_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(RawItem)
                    .where(RawItem.fetched_at >= period_start)
                    .where(RawItem.fetched_at <= period_end)
                )
                or 0
            )
            events_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.last_updated_at >= period_start)
                    .where(Event.last_updated_at <= period_end)
                )
                or 0
            )
        else:
            raw_items_count = int(
                await session.scalar(
                    select(func.count(func.distinct(RawItem.id)))
                    .select_from(RawItem)
                    .join(EventItem, EventItem.item_id == RawItem.id)
                    .join(TrendEvidence, TrendEvidence.event_id == EventItem.event_id)
                    .where(TrendEvidence.trend_id == trend_id)
                    .where(TrendEvidence.is_invalidated.is_(False))
                    .where(RawItem.fetched_at >= period_start)
                    .where(RawItem.fetched_at <= period_end)
                )
                or 0
            )
            events_count = int(
                await session.scalar(
                    select(func.count(func.distinct(Event.id)))
                    .select_from(Event)
                    .join(TrendEvidence, TrendEvidence.event_id == Event.id)
                    .where(TrendEvidence.trend_id == trend_id)
                    .where(TrendEvidence.is_invalidated.is_(False))
                    .where(Event.last_updated_at >= period_start)
                    .where(Event.last_updated_at <= period_end)
                )
                or 0
            )

        evidence_query = (
            select(func.count())
            .select_from(TrendEvidence)
            .where(TrendEvidence.created_at >= period_start)
            .where(TrendEvidence.created_at <= period_end)
            .where(TrendEvidence.is_invalidated.is_(False))
        )
        snapshot_query = (
            select(func.count())
            .select_from(TrendSnapshot)
            .where(TrendSnapshot.timestamp >= period_start)
            .where(TrendSnapshot.timestamp <= period_end)
        )
        outcome_query = (
            select(func.count())
            .select_from(TrendOutcome)
            .where(TrendOutcome.prediction_date >= period_start)
            .where(TrendOutcome.prediction_date <= period_end)
        )
        if trend_id is not None:
            evidence_query = evidence_query.where(TrendEvidence.trend_id == trend_id)
            snapshot_query = snapshot_query.where(TrendSnapshot.trend_id == trend_id)
            outcome_query = outcome_query.where(TrendOutcome.trend_id == trend_id)

        trend_evidence_count = int(await session.scalar(evidence_query) or 0)
        trend_snapshot_count = int(await session.scalar(snapshot_query) or 0)
        outcome_count = int(await session.scalar(outcome_query) or 0)

    return {
        "raw_items": raw_items_count,
        "events": events_count,
        "trend_evidence": trend_evidence_count,
        "trend_snapshots": trend_snapshot_count,
        "trend_outcomes": outcome_count,
    }


async def run_historical_replay_comparison(
    *,
    output_dir: str,
    champion_config_name: str = "stable",
    challenger_config_name: str = "fast_lower_threshold",
    trend_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    days: int = 90,
) -> Path:
    """Run replay comparison over historical outcomes in a shared time window."""
    period_end = normalize_utc(end_date) if end_date is not None else datetime.now(tz=UTC)
    period_start = (
        normalize_utc(start_date)
        if start_date is not None
        else period_end - timedelta(days=max(1, days))
    )
    if period_start > period_end:
        msg = "start_date must be <= end_date"
        raise ValueError(msg)

    champion_config = _resolve_replay_config(champion_config_name)
    challenger_config = _resolve_replay_config(challenger_config_name)

    async with async_session_maker() as session:
        query = (
            select(TrendOutcome)
            .where(TrendOutcome.prediction_date >= period_start)
            .where(TrendOutcome.prediction_date <= period_end)
            .order_by(TrendOutcome.prediction_date.asc())
        )
        if trend_id is not None:
            query = query.where(TrendOutcome.trend_id == trend_id)
        outcomes = list((await session.scalars(query)).all())

    points = _build_replay_points(outcomes)
    if not points:
        msg = "No scored outcomes available in replay window."
        raise ValueError(msg)

    champion_metrics = _evaluate_policy(champion_config, points)
    challenger_metrics = _evaluate_policy(challenger_config, points)
    dataset_counts = await _load_dataset_counts(
        period_start=period_start,
        period_end=period_end,
        trend_id=trend_id,
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "window": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "days": max(1, days),
        },
        "trend_id": str(trend_id) if trend_id is not None else None,
        "dataset_counts": dataset_counts,
        "champion": {
            "config": asdict(champion_config),
            "metrics": champion_metrics,
        },
        "challenger": {
            "config": asdict(challenger_config),
            "metrics": challenger_metrics,
        },
        "comparison": {
            "quality_delta": _numeric_deltas(
                champion_metrics["quality"],
                challenger_metrics["quality"],
            ),
            "cost_delta": _numeric_deltas(
                champion_metrics["cost"],
                challenger_metrics["cost"],
            ),
            "latency_delta": _numeric_deltas(
                champion_metrics["latency"],
                challenger_metrics["latency"],
            ),
            "promotion_assessment": _assess_promotion(
                champion_metrics=champion_metrics,
                challenger_metrics=challenger_metrics,
            ),
        },
    }
    return _write_result(output_dir=Path(output_dir), payload=payload)


def _write_result(*, output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"replay-{timestamp}-{uuid4().hex[:8]}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
