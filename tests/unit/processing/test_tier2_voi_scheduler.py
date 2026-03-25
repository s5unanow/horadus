from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.processing.cost_tracker import TierBudgetSnapshot
from src.processing.tier2_voi_scheduler import (
    Tier2TrendSignal,
    Tier2VOICandidate,
    _compute_novelty,
    _interleave_with_fairness,
    _next_unselected,
    build_tier2_voi_plan,
)

pytestmark = pytest.mark.unit


def _budget_snapshot(
    *,
    remaining_calls: int | None,
    estimated_remaining_calls_from_budget: int | None = None,
    headroom_ratio: float | None = 0.05,
) -> TierBudgetSnapshot:
    return TierBudgetSnapshot(
        tier="tier2",
        calls_used=5,
        call_limit=10,
        remaining_calls=remaining_calls,
        cost_usd=1.25,
        average_cost_per_call_usd=0.25,
        budget_remaining_usd=0.75,
        daily_cost_limit_usd=2.0,
        headroom_ratio=headroom_ratio,
        estimated_remaining_calls_from_budget=estimated_remaining_calls_from_budget,
    )


def _candidate(
    *,
    original_position: int,
    relevance_scores: tuple[int, ...],
    weights: tuple[float, ...],
    source_credibility: float = 0.9,
    created_event: bool = True,
    unique_sources: int = 1,
    contradictions: bool = False,
    fetched_hours_ago: float = 1.0,
    event_first_seen_hours_ago: float = 1.0,
) -> Tier2VOICandidate:
    now = datetime.now(tz=UTC)
    return Tier2VOICandidate(
        item_id=uuid4(),
        event_id=uuid4(),
        original_position=original_position,
        fetched_at=now - timedelta(hours=fetched_hours_ago),
        published_at=now - timedelta(hours=max(fetched_hours_ago, 0.5)),
        source_credibility=source_credibility,
        created_event=created_event,
        event_first_seen_at=now - timedelta(hours=event_first_seen_hours_ago),
        event_source_count=max(1, unique_sources),
        event_unique_source_count=unique_sources,
        event_has_contradictions=contradictions,
        trend_signals=tuple(
            Tier2TrendSignal(
                trend_id=f"trend-{index}",
                relevance_score=score,
                max_indicator_weight=weights[index],
            )
            for index, score in enumerate(relevance_scores)
        ),
    )


def test_build_tier2_voi_plan_prefers_high_impact_ambiguity_under_pressure() -> None:
    high_impact_ambiguous = _candidate(
        original_position=0,
        relevance_scores=(9, 8),
        weights=(0.08, 0.07),
        contradictions=True,
        unique_sources=1,
    )
    low_value = _candidate(
        original_position=1,
        relevance_scores=(6,),
        weights=(0.02,),
        source_credibility=0.5,
        created_event=False,
        unique_sources=4,
        event_first_seen_hours_ago=30,
    )

    plan = build_tier2_voi_plan(
        candidates=[low_value, high_impact_ambiguous],
        budget_snapshot=_budget_snapshot(remaining_calls=1),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.pressure_reason == "remaining_tier2_calls"
    assert plan.decisions[0].candidate.item_id == high_impact_ambiguous.item_id
    assert plan.decisions[0].priority_score > plan.decisions[1].priority_score


def test_build_tier2_voi_plan_interleaves_reserve_candidates_for_fairness() -> None:
    main_one = _candidate(
        original_position=0,
        relevance_scores=(10,),
        weights=(0.08,),
        unique_sources=3,
    )
    main_two = _candidate(
        original_position=1,
        relevance_scores=(9,),
        weights=(0.07,),
        unique_sources=3,
    )
    main_three = _candidate(
        original_position=2,
        relevance_scores=(8,),
        weights=(0.06,),
        unique_sources=3,
    )
    reserve = _candidate(
        original_position=4,
        relevance_scores=(9,),
        weights=(0.08,),
        fetched_hours_ago=16,
        unique_sources=1,
    )

    plan = build_tier2_voi_plan(
        candidates=[main_one, main_two, main_three, reserve],
        budget_snapshot=_budget_snapshot(remaining_calls=2),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.pressure_reason == "remaining_tier2_calls"
    assert plan.decisions[3].candidate.item_id == reserve.item_id
    assert plan.decisions[3].applied_lane == "reserve"


def test_build_tier2_voi_plan_falls_back_to_fifo_without_budget_snapshot() -> None:
    first = _candidate(original_position=0, relevance_scores=(7,), weights=(0.04,))
    second = _candidate(original_position=1, relevance_scores=(9,), weights=(0.08,))

    plan = build_tier2_voi_plan(
        candidates=[first, second],
        budget_snapshot=None,
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.used_fallback is True
    assert [decision.candidate.item_id for decision in plan.decisions] == [
        first.item_id,
        second.item_id,
    ]
    assert all(decision.applied_lane == "fifo" for decision in plan.decisions)


def test_build_tier2_voi_plan_preserves_original_order_when_not_under_pressure() -> None:
    first = _candidate(original_position=0, relevance_scores=(6,), weights=(0.03,))
    second = _candidate(original_position=1, relevance_scores=(9,), weights=(0.08,))

    plan = build_tier2_voi_plan(
        candidates=[first, second],
        budget_snapshot=_budget_snapshot(remaining_calls=5, headroom_ratio=0.8),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.used_fallback is False
    assert plan.pressure_reason == "not_under_pressure"
    assert [decision.candidate.item_id for decision in plan.decisions] == [
        first.item_id,
        second.item_id,
    ]


def test_build_tier2_voi_plan_falls_back_when_trend_signals_missing() -> None:
    candidate = _candidate(original_position=0, relevance_scores=(7,), weights=(0.04,))
    missing_signals = replace(candidate, trend_signals=())

    plan = build_tier2_voi_plan(
        candidates=[candidate, missing_signals],
        budget_snapshot=_budget_snapshot(remaining_calls=1),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.used_fallback is True
    assert plan.decisions[0].fallback_reason == "missing_trend_signals"


def test_build_tier2_voi_plan_uses_budget_cost_slots_pressure_reason() -> None:
    first = _candidate(original_position=0, relevance_scores=(7,), weights=(0.04,))
    second = _candidate(original_position=1, relevance_scores=(9,), weights=(0.08,))

    plan = build_tier2_voi_plan(
        candidates=[first, second],
        budget_snapshot=_budget_snapshot(
            remaining_calls=None,
            estimated_remaining_calls_from_budget=1,
            headroom_ratio=0.8,
        ),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.pressure_reason == "budget_cost_slots"


def test_build_tier2_voi_plan_uses_low_budget_headroom_pressure_reason() -> None:
    first = _candidate(original_position=0, relevance_scores=(7,), weights=(0.04,))
    second = _candidate(original_position=1, relevance_scores=(9,), weights=(0.08,))

    plan = build_tier2_voi_plan(
        candidates=[first, second],
        budget_snapshot=_budget_snapshot(
            remaining_calls=None,
            estimated_remaining_calls_from_budget=None,
            headroom_ratio=0.05,
        ),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    )

    assert plan.pressure_reason == "low_budget_headroom"


def test_compute_novelty_uses_midpoint_when_all_reference_times_are_missing() -> None:
    candidate = _candidate(original_position=0, relevance_scores=(7,), weights=(0.04,))
    missing_times = replace(
        candidate,
        created_event=False,
        event_first_seen_at=None,
        published_at=None,
        fetched_at=None,
    )

    novelty = _compute_novelty(candidate=missing_times, now=datetime.now(tz=UTC))

    assert novelty == pytest.approx(0.5)


def test_interleave_with_fairness_uses_reserve_fallback_and_skips_selected_items() -> None:
    candidate = _candidate(original_position=0, relevance_scores=(8,), weights=(0.06,))
    decision = build_tier2_voi_plan(
        candidates=[candidate],
        budget_snapshot=_budget_snapshot(remaining_calls=1),
        relevance_threshold=5,
        low_headroom_threshold_pct=10,
    ).decisions[0]

    ordered = _interleave_with_fairness(main_lane=[], reserve_lane=[decision])

    assert ordered[0].applied_lane == "reserve"
    assert (
        _next_unselected(
            decisions=[decision],
            selected_item_ids={decision.candidate.item_id},
            start_index=0,
        )
        is None
    )


def test_interleave_with_fairness_handles_missing_reserve_slot() -> None:
    ordered = _interleave_with_fairness(
        main_lane=[
            build_tier2_voi_plan(
                candidates=[
                    _candidate(
                        original_position=index, relevance_scores=(8 - index,), weights=(0.06,)
                    )
                ],
                budget_snapshot=_budget_snapshot(remaining_calls=1),
                relevance_threshold=5,
                low_headroom_threshold_pct=10,
            ).decisions[0]
            for index in range(4)
        ],
        reserve_lane=[],
    )

    assert [decision.candidate.original_position for decision in ordered] == [0, 1, 2, 3]
