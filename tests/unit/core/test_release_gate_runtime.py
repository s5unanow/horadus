from __future__ import annotations

import pytest

from src.core.release_gate_runtime import (
    RuntimeGateThresholds,
    StageRuntimeMetrics,
    evaluate_runtime_gate,
    parse_stage_metrics,
)

pytestmark = pytest.mark.unit


def _thresholds() -> RuntimeGateThresholds:
    return RuntimeGateThresholds(
        max_error_rate=0.05,
        max_p95_latency_ms=1200.0,
        max_budget_denial_rate=0.1,
        max_production_error_rate_drift=0.02,
        min_window_minutes=60,
    )


def test_parse_stage_metrics_accepts_stage_wrapped_payload() -> None:
    payload = {
        "stages": {
            "development": {
                "error_rate": 0.01,
                "p95_latency_ms": 100.0,
                "budget_denial_rate": 0.0,
                "window_minutes": 120,
            }
        }
    }

    parsed = parse_stage_metrics(payload)
    assert parsed["development"].error_rate == pytest.approx(0.01)
    assert parsed["development"].window_minutes == 120


def test_evaluate_runtime_gate_strict_passes_on_healthy_metrics() -> None:
    metrics = {
        "development": StageRuntimeMetrics(0.01, 200.0, 0.0, 120),
        "staging": StageRuntimeMetrics(0.02, 400.0, 0.01, 120),
        "production": StageRuntimeMetrics(0.03, 500.0, 0.02, 120),
    }

    result = evaluate_runtime_gate(
        metrics_by_stage=metrics,
        thresholds=_thresholds(),
        strict_mode=True,
    )

    assert result.has_failures is False
    assert all(check.status == "PASS" for check in result.checks)


def test_evaluate_runtime_gate_strict_fails_on_threshold_breach() -> None:
    metrics = {
        "staging": StageRuntimeMetrics(0.02, 400.0, 0.01, 120),
        "production": StageRuntimeMetrics(0.09, 500.0, 0.02, 120),
    }

    result = evaluate_runtime_gate(
        metrics_by_stage=metrics,
        thresholds=_thresholds(),
        strict_mode=True,
    )

    assert result.has_failures is True
    assert any(check.status == "FAIL" and check.metric == "error_rate" for check in result.checks)


def test_evaluate_runtime_gate_development_mode_warns_only() -> None:
    metrics = {
        "development": StageRuntimeMetrics(0.2, 3000.0, 0.5, 10),
    }

    result = evaluate_runtime_gate(
        metrics_by_stage=metrics,
        thresholds=_thresholds(),
        strict_mode=False,
    )

    assert result.has_failures is False
    assert any(check.status == "WARN" for check in result.checks)
