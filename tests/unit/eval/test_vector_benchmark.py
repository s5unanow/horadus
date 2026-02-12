from __future__ import annotations

import pytest

from src.eval import vector_benchmark as vector_benchmark_module

pytestmark = pytest.mark.unit


def test_recommend_strategy_prefers_fast_high_recall_candidate() -> None:
    metrics = {
        "exact": vector_benchmark_module.StrategyMetrics(
            name="exact",
            avg_latency_ms=4.0,
            p95_latency_ms=5.0,
            recall_at_k=1.0,
        ),
        "ivfflat": vector_benchmark_module.StrategyMetrics(
            name="ivfflat",
            avg_latency_ms=3.9,
            p95_latency_ms=4.8,
            recall_at_k=0.93,
        ),
        "hnsw": vector_benchmark_module.StrategyMetrics(
            name="hnsw",
            avg_latency_ms=2.5,
            p95_latency_ms=3.1,
            recall_at_k=0.98,
        ),
    }

    selected = vector_benchmark_module._recommend_strategy(metrics_by_strategy=metrics)

    assert selected == "hnsw"


def test_recommend_strategy_falls_back_to_exact_when_recall_or_speed_not_met() -> None:
    low_recall = {
        "exact": vector_benchmark_module.StrategyMetrics("exact", 4.0, 5.0, 1.0),
        "ivfflat": vector_benchmark_module.StrategyMetrics("ivfflat", 2.9, 3.5, 0.82),
        "hnsw": vector_benchmark_module.StrategyMetrics("hnsw", 3.2, 3.9, 0.90),
    }
    assert vector_benchmark_module._recommend_strategy(metrics_by_strategy=low_recall) == "exact"

    not_fast_enough = {
        "exact": vector_benchmark_module.StrategyMetrics("exact", 4.0, 5.0, 1.0),
        "ivfflat": vector_benchmark_module.StrategyMetrics("ivfflat", 3.95, 4.5, 0.97),
        "hnsw": vector_benchmark_module.StrategyMetrics("hnsw", 3.9, 4.4, 0.98),
    }
    assert (
        vector_benchmark_module._recommend_strategy(metrics_by_strategy=not_fast_enough) == "exact"
    )
