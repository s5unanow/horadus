"""Deterministic Tier-2 value-of-information scheduling helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.processing.cost_tracker import TierBudgetSnapshot

_MAX_SOURCE_CREDIBILITY = 1.25
_MAX_INDICATOR_WEIGHT = 0.10
_FAIRNESS_INTERVAL = 4


@dataclass(frozen=True, slots=True)
class Tier2TrendSignal:
    """Tier-specific relevance plus bounded impact weight proxy for one trend."""

    trend_id: str
    relevance_score: int
    max_indicator_weight: float


@dataclass(frozen=True, slots=True)
class Tier2VOICandidate:
    """Deterministic runtime inputs used to prioritize one Tier-2 candidate."""

    item_id: UUID
    event_id: UUID | None
    original_position: int
    fetched_at: datetime | None
    published_at: datetime | None
    source_credibility: float
    created_event: bool
    event_first_seen_at: datetime | None
    event_source_count: int
    event_unique_source_count: int
    event_has_contradictions: bool
    trend_signals: tuple[Tier2TrendSignal, ...]


@dataclass(frozen=True, slots=True)
class Tier2VOIDecision:
    """Final ordering decision plus explainable factor values."""

    candidate: Tier2VOICandidate
    priority_score: float
    expected_delta: float
    uncertainty: float
    contradiction_risk: float
    novelty: float
    trend_relevance: float
    fairness_age: float
    reserve_candidate: bool
    applied_lane: str
    pressure_reason: str
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Tier2VOIPlan:
    """Tier-2 execution order and the reason for it."""

    decisions: tuple[Tier2VOIDecision, ...]
    pressure_reason: str
    used_fallback: bool


def build_tier2_voi_plan(
    *,
    candidates: Iterable[Tier2VOICandidate],
    budget_snapshot: TierBudgetSnapshot | None,
    relevance_threshold: int,
    low_headroom_threshold_pct: int,
    now: datetime | None = None,
) -> Tier2VOIPlan:
    """Return deterministic Tier-2 ordering decisions for one batch."""
    candidate_list = list(candidates)
    if len(candidate_list) <= 1:
        return Tier2VOIPlan(
            decisions=tuple(
                _score_candidate(
                    candidate=candidate,
                    relevance_threshold=relevance_threshold,
                    pressure_reason="not_under_pressure",
                    now=now,
                )
                for candidate in candidate_list
            ),
            pressure_reason="not_under_pressure",
            used_fallback=False,
        )

    pressure_reason = _resolve_pressure_reason(
        budget_snapshot=budget_snapshot,
        candidate_count=len(candidate_list),
        low_headroom_threshold_pct=low_headroom_threshold_pct,
    )
    if pressure_reason == "not_under_pressure":
        return Tier2VOIPlan(
            decisions=tuple(
                _score_candidate(
                    candidate=candidate,
                    relevance_threshold=relevance_threshold,
                    pressure_reason=pressure_reason,
                    now=now,
                )
                for candidate in candidate_list
            ),
            pressure_reason=pressure_reason,
            used_fallback=False,
        )

    if budget_snapshot is None:
        return _fifo_fallback(
            candidates=candidate_list,
            relevance_threshold=relevance_threshold,
            pressure_reason="missing_budget_snapshot",
            now=now,
        )
    if any(not candidate.trend_signals for candidate in candidate_list):
        return _fifo_fallback(
            candidates=candidate_list,
            relevance_threshold=relevance_threshold,
            pressure_reason=pressure_reason,
            fallback_reason="missing_trend_signals",
            now=now,
        )

    scored = [
        _score_candidate(
            candidate=candidate,
            relevance_threshold=relevance_threshold,
            pressure_reason=pressure_reason,
            now=now,
        )
        for candidate in candidate_list
    ]
    ranked = sorted(
        scored,
        key=lambda decision: (-decision.priority_score, decision.candidate.original_position),
    )
    if len(ranked) < _FAIRNESS_INTERVAL:
        return Tier2VOIPlan(
            decisions=tuple(ranked),
            pressure_reason=pressure_reason,
            used_fallback=False,
        )
    reserve_main_lane = [decision for decision in ranked if decision.reserve_candidate]
    main_lane = [
        *[decision for decision in ranked if not decision.reserve_candidate],
        *reserve_main_lane,
    ]
    reserve_lane = sorted(
        reserve_main_lane,
        key=lambda decision: (
            -decision.fairness_age,
            -decision.expected_delta,
            -decision.novelty,
            -decision.candidate.original_position,
        ),
    )
    ordered = _interleave_with_fairness(main_lane=main_lane, reserve_lane=reserve_lane)
    return Tier2VOIPlan(
        decisions=tuple(ordered),
        pressure_reason=pressure_reason,
        used_fallback=False,
    )


def _fifo_fallback(
    *,
    candidates: list[Tier2VOICandidate],
    relevance_threshold: int,
    pressure_reason: str,
    fallback_reason: str = "fifo_fallback",
    now: datetime | None = None,
) -> Tier2VOIPlan:
    decisions = tuple(
        replace(
            _score_candidate(
                candidate=candidate,
                relevance_threshold=relevance_threshold,
                pressure_reason=pressure_reason,
                now=now,
            ),
            applied_lane="fifo",
            fallback_reason=fallback_reason,
        )
        for candidate in candidates
    )
    return Tier2VOIPlan(
        decisions=decisions,
        pressure_reason=pressure_reason,
        used_fallback=True,
    )


def _resolve_pressure_reason(
    *,
    budget_snapshot: TierBudgetSnapshot | None,
    candidate_count: int,
    low_headroom_threshold_pct: int,
) -> str:
    if budget_snapshot is None:
        return "missing_budget_snapshot"

    if (
        budget_snapshot.remaining_calls is not None
        and budget_snapshot.remaining_calls < candidate_count
    ):
        return "remaining_tier2_calls"

    if (
        budget_snapshot.estimated_remaining_calls_from_budget is not None
        and budget_snapshot.estimated_remaining_calls_from_budget < candidate_count
    ):
        return "budget_cost_slots"

    if (
        budget_snapshot.headroom_ratio is not None
        and budget_snapshot.headroom_ratio <= max(0, low_headroom_threshold_pct) / 100.0
    ):
        return "low_budget_headroom"

    return "not_under_pressure"


def _score_candidate(
    *,
    candidate: Tier2VOICandidate,
    relevance_threshold: int,
    pressure_reason: str,
    now: datetime | None,
) -> Tier2VOIDecision:
    reference_now = now.astimezone(UTC) if now is not None else datetime.now(tz=UTC)
    scores = sorted(
        [signal.relevance_score for signal in candidate.trend_signals],
        reverse=True,
    )
    top_score = scores[0] if scores else 0
    second_score = scores[1] if len(scores) > 1 else 0
    trend_relevance = _clamp(top_score / 10.0)

    threshold_gap = abs(top_score - relevance_threshold)
    threshold_scale = max(1, 10 - min(relevance_threshold, 9))
    near_threshold = 1.0 - min(threshold_gap / threshold_scale, 1.0)
    ambiguity = 1.0 - min((top_score - second_score) / 10.0, 1.0)
    uncertainty = _clamp((near_threshold * 0.55) + (ambiguity * 0.45))

    max_indicator_weight = max(
        (max(0.0, float(signal.max_indicator_weight)) for signal in candidate.trend_signals),
        default=0.0,
    )
    weight_factor = _clamp(max_indicator_weight / _MAX_INDICATOR_WEIGHT)
    source_factor = _clamp(max(0.0, candidate.source_credibility) / _MAX_SOURCE_CREDIBILITY)
    expected_delta = _clamp(
        (weight_factor * 0.45) + (trend_relevance * 0.35) + (source_factor * 0.20)
    )

    contradiction_risk = _clamp(
        1.0
        if candidate.event_has_contradictions
        else (ambiguity * 0.65) + (0.35 if second_score >= relevance_threshold else 0.0)
    )
    novelty = _compute_novelty(candidate=candidate, now=reference_now)
    fairness_age = _compute_fairness_age(candidate=candidate, now=reference_now)
    reserve_candidate = _is_reserve_candidate(
        candidate=candidate,
        expected_delta=expected_delta,
        fairness_age=fairness_age,
    )
    priority_score = _clamp(
        (expected_delta * 0.32)
        + (uncertainty * 0.23)
        + (contradiction_risk * 0.15)
        + (novelty * 0.15)
        + (trend_relevance * 0.10)
        + (fairness_age * 0.05)
    )
    return Tier2VOIDecision(
        candidate=candidate,
        priority_score=round(priority_score, 6),
        expected_delta=round(expected_delta, 6),
        uncertainty=round(uncertainty, 6),
        contradiction_risk=round(contradiction_risk, 6),
        novelty=round(novelty, 6),
        trend_relevance=round(trend_relevance, 6),
        fairness_age=round(fairness_age, 6),
        reserve_candidate=reserve_candidate,
        applied_lane="voi",
        pressure_reason=pressure_reason,
    )


def _compute_novelty(*, candidate: Tier2VOICandidate, now: datetime) -> float:
    if candidate.created_event:
        return 1.0
    reference_time = candidate.event_first_seen_at or candidate.published_at or candidate.fetched_at
    if reference_time is None:
        return 0.5
    age_hours = max(0.0, (now - reference_time.astimezone(UTC)).total_seconds() / 3600.0)
    return _clamp(1.0 - min(age_hours / 48.0, 1.0))


def _compute_fairness_age(*, candidate: Tier2VOICandidate, now: datetime) -> float:
    reference_time = candidate.fetched_at or candidate.published_at
    if reference_time is None:
        return 0.0
    wait_hours = max(0.0, (now - reference_time.astimezone(UTC)).total_seconds() / 3600.0)
    return _clamp(wait_hours / 24.0)


def _is_reserve_candidate(
    *,
    candidate: Tier2VOICandidate,
    expected_delta: float,
    fairness_age: float,
) -> bool:
    if expected_delta < 0.55:
        return False
    if fairness_age >= 0.5:
        return True
    if candidate.event_unique_source_count <= 1:
        return True
    return candidate.original_position >= 3


def _interleave_with_fairness(
    *,
    main_lane: list[Tier2VOIDecision],
    reserve_lane: list[Tier2VOIDecision],
) -> list[Tier2VOIDecision]:
    ordered: list[Tier2VOIDecision] = []
    selected_item_ids: set[UUID] = set()
    main_index = 0
    reserve_index = 0

    while main_index < len(main_lane) or reserve_index < len(reserve_lane):
        while main_index < len(main_lane) and len(ordered) % _FAIRNESS_INTERVAL != (
            _FAIRNESS_INTERVAL - 1
        ):
            decision = main_lane[main_index]
            main_index += 1
            if decision.candidate.item_id in selected_item_ids:
                continue
            ordered.append(decision)
            selected_item_ids.add(decision.candidate.item_id)
            break

        if len(ordered) % _FAIRNESS_INTERVAL == (_FAIRNESS_INTERVAL - 1):
            reserve_decision = _next_unselected(
                decisions=reserve_lane,
                selected_item_ids=selected_item_ids,
                start_index=reserve_index,
            )
            if reserve_decision is not None:
                reserve_index = reserve_decision[0] + 1
                ordered.append(replace(reserve_decision[1], applied_lane="reserve"))
                selected_item_ids.add(reserve_decision[1].candidate.item_id)
                continue

        next_main = _next_unselected(
            decisions=main_lane,
            selected_item_ids=selected_item_ids,
            start_index=main_index,
        )
        if next_main is not None:
            main_index = next_main[0] + 1
            ordered.append(next_main[1])
            selected_item_ids.add(next_main[1].candidate.item_id)
            continue

        next_reserve = _next_unselected(
            decisions=reserve_lane,
            selected_item_ids=selected_item_ids,
            start_index=reserve_index,
        )
        if next_reserve is None:
            break
        reserve_index = next_reserve[0] + 1
        ordered.append(replace(next_reserve[1], applied_lane="reserve"))
        selected_item_ids.add(next_reserve[1].candidate.item_id)

    return ordered


def _next_unselected(
    *,
    decisions: list[Tier2VOIDecision],
    selected_item_ids: set[UUID],
    start_index: int,
) -> tuple[int, Tier2VOIDecision] | None:
    for index in range(start_index, len(decisions)):
        decision = decisions[index]
        if decision.candidate.item_id not in selected_item_ids:
            return (index, decision)
    return None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
