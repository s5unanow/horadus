from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.cluster_drift import (
    ClusterDriftThresholds,
    ClusterEventSample,
    compute_cluster_drift_summary,
    load_latest_language_distribution,
    write_cluster_drift_artifact,
)

pytestmark = pytest.mark.unit


def _thresholds() -> ClusterDriftThresholds:
    return ClusterDriftThresholds(
        singleton_rate_warn=0.5,
        large_cluster_rate_warn=0.4,
        contradiction_rate_warn=0.4,
        language_drift_warn=0.3,
        large_cluster_size=4,
    )


def test_compute_cluster_drift_summary_is_deterministic() -> None:
    now = datetime.now(tz=UTC).replace(microsecond=0)
    samples = [
        ClusterEventSample(item_count=1, has_contradictions=False, languages=("en",)),
        ClusterEventSample(item_count=5, has_contradictions=True, languages=("ru", "ru")),
        ClusterEventSample(item_count=2, has_contradictions=False, languages=("en", "uk")),
    ]

    summary = compute_cluster_drift_summary(
        event_samples=samples,
        thresholds=_thresholds(),
        baseline_language_distribution={"en": 0.9, "ru": 0.1},
        window_start=now - timedelta(days=1),
        window_end=now,
    )

    assert summary["event_count"] == 3
    assert summary["singleton_rate"] == pytest.approx(1 / 3, rel=0.001)
    assert summary["large_cluster_rate"] == pytest.approx(1 / 3, rel=0.001)
    assert summary["contradiction_rate"] == pytest.approx(1 / 3, rel=0.001)
    assert "language_distribution_drift" in summary["warning_keys"]


def test_write_cluster_drift_artifact_and_load_baseline(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "cluster-drift"
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    summary = {
        "window_end": now.isoformat(),
        "language_distribution": {"en": 0.6, "ru": 0.4},
    }

    output_path = write_cluster_drift_artifact(artifact_dir=artifact_dir, summary=summary)
    assert output_path.name == "2026-03-02.json"

    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["language_distribution"]["en"] == pytest.approx(0.6)

    baseline = load_latest_language_distribution(artifact_dir)
    assert baseline is not None
    assert baseline["ru"] == pytest.approx(0.4)
