from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.eval import replay as replay_module
from src.storage.models import OutcomeType, TrendOutcome

pytestmark = pytest.mark.unit


class _ScalarResult:
    def __init__(self, values: list[TrendOutcome]):
        self._values = values

    def all(self) -> list[TrendOutcome]:
        return self._values


def _build_outcome(
    *,
    probability: float,
    outcome: OutcomeType | str | None,
    brier_score: float | None = None,
) -> TrendOutcome:
    return TrendOutcome(
        trend_id=uuid4(),
        prediction_date=datetime(2026, 1, 1, tzinfo=UTC),
        predicted_probability=probability,
        predicted_risk_level="elevated",
        probability_band_low=max(0.001, probability - 0.1),
        probability_band_high=min(0.999, probability + 0.1),
        outcome_date=datetime(2026, 1, 2, tzinfo=UTC),
        outcome=outcome.value if isinstance(outcome, OutcomeType) else outcome,
        brier_score=brier_score,
    )


def test_evaluate_policy_returns_quality_cost_and_latency_metrics() -> None:
    config = replay_module.ReplayConfig(
        name="test",
        decision_threshold=0.5,
        estimated_cost_per_decision_usd=0.1,
        estimated_latency_per_decision_ms=10,
    )
    points = [
        replay_module._ReplayPoint(
            probability=0.9,
            actual_value=1.0,
            brier_score=0.01,
            binary_actual=1,
        ),
        replay_module._ReplayPoint(
            probability=0.7,
            actual_value=0.0,
            brier_score=0.49,
            binary_actual=0,
        ),
        replay_module._ReplayPoint(
            probability=0.2,
            actual_value=0.0,
            brier_score=0.04,
            binary_actual=0,
        ),
    ]

    metrics = replay_module._evaluate_policy(config, points)

    assert metrics["quality"]["decision_accuracy"] == 0.666667
    assert metrics["quality"]["precision"] == 0.5
    assert metrics["quality"]["recall"] == 1.0
    assert metrics["quality"]["f1_score"] == 0.666667
    assert metrics["quality"]["mean_abs_calibration_error"] == 0.333333
    assert metrics["cost"]["estimated_total_cost_usd"] == 0.3
    assert metrics["latency"]["estimated_total_latency_ms"] == 30


def test_assess_promotion_blocks_when_quality_regresses() -> None:
    champion = {
        "quality": {
            "decision_accuracy": 0.81,
            "mean_brier_score": 0.18,
        },
        "cost": {
            "estimated_total_cost_usd": 1.0,
        },
        "latency": {
            "estimated_p95_latency_ms": 200.0,
        },
    }
    challenger = {
        "quality": {
            "decision_accuracy": 0.75,
            "mean_brier_score": 0.20,
        },
        "cost": {
            "estimated_total_cost_usd": 1.05,
        },
        "latency": {
            "estimated_p95_latency_ms": 210.0,
        },
    }

    assessment = replay_module._assess_promotion(
        champion_metrics=champion,
        challenger_metrics=challenger,
    )

    assert assessment["recommended"] is False
    assert "Decision accuracy regressed by more than 0.01." in assessment["reasons"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"decision_threshold": -0.1}, "decision_threshold must be within [0, 1]"),
        ({"abstain_lower": -0.1}, "abstain_lower must be within [0, 1]"),
        ({"abstain_upper": 1.1}, "abstain_upper must be within [0, 1]"),
        (
            {"abstain_lower": 0.6, "abstain_upper": 0.5},
            "abstain_lower must be <= abstain_upper",
        ),
        (
            {"estimated_cost_per_decision_usd": -0.01},
            "estimated_cost_per_decision_usd must be >= 0",
        ),
        (
            {"estimated_latency_per_decision_ms": -1},
            "estimated_latency_per_decision_ms must be >= 0",
        ),
    ],
)
def test_replay_config_rejects_invalid_values(kwargs: dict[str, float], message: str) -> None:
    config_kwargs: dict[str, float | str] = {"name": "bad", "decision_threshold": 0.5}
    config_kwargs.update(kwargs)

    with pytest.raises(ValueError, match=re.escape(message)):
        replay_module.ReplayConfig(**config_kwargs)


def test_available_replay_configs_are_named_by_profile() -> None:
    configs = replay_module.available_replay_configs()

    assert set(configs) == {"stable", "fast_lower_threshold"}
    assert configs["stable"].decision_threshold == 0.5


def test_resolve_replay_config_is_case_and_whitespace_insensitive() -> None:
    resolved = replay_module._resolve_replay_config("  STABLE  ")

    assert resolved.name == "stable"


def test_resolve_replay_config_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown replay config 'unknown'"):
        replay_module._resolve_replay_config("unknown")


@pytest.mark.parametrize(
    ("raw_outcome", "expected"),
    [
        (OutcomeType.OCCURRED.value, 1.0),
        (OutcomeType.DID_NOT_OCCUR.value, 0.0),
        (OutcomeType.PARTIAL.value, 0.5),
        (OutcomeType.ONGOING.value, None),
        ("bogus", None),
        (None, None),
    ],
)
def test_actual_outcome_value_handles_scored_and_unscored_values(
    raw_outcome: str | None,
    expected: float | None,
) -> None:
    assert replay_module._actual_outcome_value(raw_outcome) == expected


@pytest.mark.parametrize(
    ("raw_outcome", "expected"),
    [
        (OutcomeType.OCCURRED.value, 1),
        (OutcomeType.DID_NOT_OCCUR.value, 0),
        (OutcomeType.PARTIAL.value, None),
        ("bogus", None),
        (None, None),
    ],
)
def test_binary_actual_only_keeps_binary_resolutions(
    raw_outcome: str | None,
    expected: int | None,
) -> None:
    assert replay_module._binary_actual(raw_outcome) == expected


def test_build_replay_points_skips_unusable_outcomes_and_backfills_brier_score() -> None:
    points = replay_module._build_replay_points(
        [
            _build_outcome(probability=0.8, outcome=OutcomeType.OCCURRED, brier_score=0.04),
            _build_outcome(probability=0.2, outcome=OutcomeType.DID_NOT_OCCUR, brier_score=None),
            _build_outcome(probability=0.5, outcome=OutcomeType.ONGOING, brier_score=None),
            _build_outcome(probability=0.3, outcome="bogus", brier_score=None),
            _build_outcome(probability=0.4, outcome=None, brier_score=None),
        ]
    )

    assert len(points) == 2
    assert points[0].probability == pytest.approx(0.8)
    assert points[0].actual_value == 1.0
    assert points[0].binary_actual == 1
    assert points[1].brier_score == pytest.approx(0.04)
    assert points[1].binary_actual == 0


def test_build_replay_points_skips_items_when_brier_cannot_be_computed(monkeypatch) -> None:
    monkeypatch.setattr(replay_module, "calculate_brier_score", lambda **_kwargs: None)

    points = replay_module._build_replay_points(
        [_build_outcome(probability=0.2, outcome=OutcomeType.DID_NOT_OCCUR, brier_score=None)]
    )

    assert points == []


def test_decision_for_probability_respects_abstain_band() -> None:
    config = replay_module.ReplayConfig(
        name="test",
        decision_threshold=0.5,
        abstain_lower=0.45,
        abstain_upper=0.55,
    )

    assert replay_module._decision_for_probability(0.5, config) == "abstain"
    assert replay_module._decision_for_probability(0.7, config) == "positive"
    assert replay_module._decision_for_probability(0.2, config) == "negative"


def test_evaluate_policy_handles_abstentions_and_non_binary_points() -> None:
    config = replay_module.ReplayConfig(
        name="test",
        decision_threshold=0.6,
        abstain_lower=0.4,
        abstain_upper=0.6,
        estimated_cost_per_decision_usd=0.2,
        estimated_latency_per_decision_ms=25,
    )
    points = [
        replay_module._ReplayPoint(
            probability=0.5,
            actual_value=0.5,
            brier_score=0.0,
            binary_actual=None,
        ),
        replay_module._ReplayPoint(
            probability=0.55,
            actual_value=1.0,
            brier_score=0.2025,
            binary_actual=1,
        ),
    ]

    metrics = replay_module._evaluate_policy(config, points)

    assert metrics["quality"]["binary_outcomes"] == 1
    assert metrics["quality"]["decisions_made"] == 0
    assert metrics["quality"]["abstentions"] == 1
    assert metrics["quality"]["abstain_ratio"] == 1.0
    assert metrics["quality"]["decision_accuracy"] == 0.0
    assert metrics["cost"]["estimated_total_cost_usd"] == 0.0
    assert metrics["latency"]["estimated_p50_latency_ms"] == 0.0
    assert metrics["quality"]["mean_brier_score"] == 0.10125


def test_evaluate_policy_counts_false_negatives() -> None:
    config = replay_module.ReplayConfig(name="test", decision_threshold=0.6)
    points = [
        replay_module._ReplayPoint(
            probability=0.2,
            actual_value=1.0,
            brier_score=0.64,
            binary_actual=1,
        )
    ]

    metrics = replay_module._evaluate_policy(config, points)

    assert metrics["quality"]["false_negative"] == 1
    assert metrics["quality"]["recall"] == 0.0
    assert metrics["quality"]["decision_accuracy"] == 0.0


def test_numeric_deltas_only_include_numeric_keys() -> None:
    champion = {"score": 1.0, "count": 2, "label": "stable"}
    challenger = {"score": 1.5, "count": 5, "label": "fast"}

    assert replay_module._numeric_deltas(champion, challenger) == {
        "score": 0.5,
        "count": 3.0,
    }


def test_assess_promotion_accepts_good_challenger() -> None:
    champion = {
        "quality": {"decision_accuracy": 0.8, "mean_brier_score": 0.2},
        "cost": {"estimated_total_cost_usd": 1.0},
        "latency": {"estimated_p95_latency_ms": 200.0},
    }
    challenger = {
        "quality": {"decision_accuracy": 0.81, "mean_brier_score": 0.19},
        "cost": {"estimated_total_cost_usd": 1.15},
        "latency": {"estimated_p95_latency_ms": 220.0},
    }

    assessment = replay_module._assess_promotion(
        champion_metrics=champion,
        challenger_metrics=challenger,
    )

    assert assessment == {
        "recommended": True,
        "reasons": ["Challenger meets replay promotion gates for quality/cost/latency."],
    }


def test_assess_promotion_blocks_cost_and_latency_regressions() -> None:
    champion = {
        "quality": {"decision_accuracy": 0.8, "mean_brier_score": 0.2},
        "cost": {"estimated_total_cost_usd": 1.0},
        "latency": {"estimated_p95_latency_ms": 100.0},
    }
    challenger = {
        "quality": {"decision_accuracy": 0.8, "mean_brier_score": 0.2},
        "cost": {"estimated_total_cost_usd": 1.5},
        "latency": {"estimated_p95_latency_ms": 150.0},
    }

    assessment = replay_module._assess_promotion(
        champion_metrics=champion,
        challenger_metrics=challenger,
    )

    assert assessment["recommended"] is False
    assert "Estimated replay cost increased by more than 20%." in assessment["reasons"]
    assert "Estimated p95 latency increased by more than 20%." in assessment["reasons"]


@pytest.mark.asyncio
async def test_load_dataset_counts_aggregates_global_window(monkeypatch) -> None:
    scalar_values = iter([10, 3, 4, 5, 6])

    class _Session:
        async def scalar(self, _query):
            return next(scalar_values)

    @asynccontextmanager
    async def _fake_session_maker():
        yield _Session()

    monkeypatch.setattr(replay_module, "async_session_maker", _fake_session_maker)

    counts = await replay_module._load_dataset_counts(
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 2, tzinfo=UTC),
        trend_id=None,
    )

    assert counts == {
        "raw_items": 10,
        "events": 3,
        "trend_evidence": 4,
        "trend_snapshots": 5,
        "trend_outcomes": 6,
    }


@pytest.mark.asyncio
async def test_load_dataset_counts_filters_by_trend(monkeypatch) -> None:
    scalar_values = iter([2, 1, 4, 5, 6])

    class _Session:
        async def scalar(self, _query):
            return next(scalar_values)

    @asynccontextmanager
    async def _fake_session_maker():
        yield _Session()

    monkeypatch.setattr(replay_module, "async_session_maker", _fake_session_maker)

    counts = await replay_module._load_dataset_counts(
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 2, tzinfo=UTC),
        trend_id=uuid4(),
    )

    assert counts["raw_items"] == 2
    assert counts["events"] == 1


@pytest.mark.asyncio
async def test_run_historical_replay_comparison_rejects_inverted_window() -> None:
    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        await replay_module.run_historical_replay_comparison(
            output_dir="/tmp",
            start_date=datetime(2026, 1, 2, tzinfo=UTC),
            end_date=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_run_historical_replay_comparison_requires_scored_points(
    monkeypatch, tmp_path
) -> None:
    class _Session:
        async def scalars(self, _query):
            return _ScalarResult([])

    @asynccontextmanager
    async def _fake_session_maker():
        yield _Session()

    monkeypatch.setattr(replay_module, "async_session_maker", _fake_session_maker)

    with pytest.raises(ValueError, match="No scored outcomes available in replay window."):
        await replay_module.run_historical_replay_comparison(output_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_run_historical_replay_comparison_writes_payload(monkeypatch, tmp_path) -> None:
    trend_id = uuid4()
    outcome = _build_outcome(probability=0.8, outcome=OutcomeType.OCCURRED, brier_score=0.04)
    outcome.trend_id = trend_id
    written: dict[str, object] = {}

    class _Session:
        async def scalars(self, _query):
            return _ScalarResult([outcome])

    @asynccontextmanager
    async def _fake_session_maker():
        yield _Session()

    async def _fake_load_dataset_counts(**_kwargs):
        return {
            "raw_items": 1,
            "events": 1,
            "trend_evidence": 1,
            "trend_snapshots": 1,
            "trend_outcomes": 1,
        }

    def _fake_write_result(*, output_dir: Path, payload: dict[str, object]) -> Path:
        written["output_dir"] = output_dir
        written["payload"] = payload
        return output_dir / "artifact.json"

    monkeypatch.setattr(replay_module, "async_session_maker", _fake_session_maker)
    monkeypatch.setattr(replay_module, "_load_dataset_counts", _fake_load_dataset_counts)
    monkeypatch.setattr(replay_module, "_write_result", _fake_write_result)

    result = await replay_module.run_historical_replay_comparison(
        output_dir=str(tmp_path),
        champion_config_name="stable",
        challenger_config_name="fast_lower_threshold",
        trend_id=trend_id,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 31, tzinfo=UTC),
        days=30,
    )

    payload = written["payload"]
    assert result == tmp_path / "artifact.json"
    assert written["output_dir"] == tmp_path
    assert payload["trend_id"] == str(trend_id)
    assert payload["dataset_counts"]["raw_items"] == 1
    assert payload["window"]["days"] == 30
    assert payload["champion"]["config"]["name"] == "stable"
    assert payload["challenger"]["config"]["name"] == "fast_lower_threshold"
    assert payload["comparison"]["promotion_assessment"]["recommended"] is True


def test_write_result_creates_replay_artifact(tmp_path) -> None:
    payload = {"comparison": {"promotion_assessment": {"recommended": True}}}
    output_path = replay_module._write_result(output_dir=tmp_path, payload=payload)

    assert output_path.exists()
    assert output_path.name.startswith("replay-")
