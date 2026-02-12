from __future__ import annotations

import pytest

from src.eval import replay as replay_module

pytestmark = pytest.mark.unit


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


def test_write_result_creates_replay_artifact(tmp_path) -> None:
    payload = {"comparison": {"promotion_assessment": {"recommended": True}}}
    output_path = replay_module._write_result(output_dir=tmp_path, payload=payload)

    assert output_path.exists()
    assert output_path.name.startswith("replay-")
