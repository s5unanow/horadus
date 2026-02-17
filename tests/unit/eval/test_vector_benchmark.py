from __future__ import annotations

import json
from pathlib import Path

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


def test_update_revalidation_summary_writes_latest_and_history(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    artifact_path = tmp_path / "vector-benchmark-1.json"
    artifact_path.write_text("{}", encoding="utf-8")

    summary_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=payload,
        artifact_path=artifact_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["latest"]["artifact"] == "vector-benchmark-1.json"
    assert summary["latest"]["selected_default"] == "ivfflat"
    assert len(summary["history"]) == 1


def test_update_revalidation_summary_appends_history_entries(tmp_path: Path) -> None:
    base_payload = {
        "generated_at": "2026-02-16T00:00:00+00:00",
        "dataset": {
            "size": 4000,
            "dimensions": 64,
            "query_count": 200,
            "vector_fingerprint_sha256": "abc123",
        },
        "recommendation": {
            "selected_default": "ivfflat",
            "selection_rule": "rule",
        },
    }
    first_artifact = tmp_path / "vector-benchmark-1.json"
    second_artifact = tmp_path / "vector-benchmark-2.json"
    first_artifact.write_text("{}", encoding="utf-8")
    second_artifact.write_text("{}", encoding="utf-8")

    vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=base_payload,
        artifact_path=first_artifact,
    )
    second_payload = {
        **base_payload,
        "generated_at": "2026-02-17T00:00:00+00:00",
        "recommendation": {
            "selected_default": "hnsw",
            "selection_rule": "rule",
        },
    }
    summary_path = vector_benchmark_module._update_revalidation_summary(
        output_dir=tmp_path,
        payload=second_payload,
        artifact_path=second_artifact,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["latest"]["artifact"] == "vector-benchmark-2.json"
    assert summary["latest"]["selected_default"] == "hnsw"
    assert len(summary["history"]) == 2
