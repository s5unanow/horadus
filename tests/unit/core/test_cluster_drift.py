from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.cluster_drift import (
    ClusterDriftThresholds,
    ClusterEventSample,
    _language_drift_score,
    _normalize_distribution,
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


def test_distribution_helpers_handle_empty_and_negative_values() -> None:
    assert _normalize_distribution({"en": -1, "ru": 0}) == {}
    assert _language_drift_score(current_distribution={}, baseline_distribution={}) == 0.0


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


def test_compute_cluster_drift_summary_handles_empty_inputs_and_threshold_edges() -> None:
    now = datetime.now(tz=UTC).replace(microsecond=0)
    summary = compute_cluster_drift_summary(
        event_samples=[],
        thresholds=ClusterDriftThresholds(
            singleton_rate_warn=0.0,
            large_cluster_rate_warn=0.0,
            contradiction_rate_warn=0.0,
            language_drift_warn=0.0,
            large_cluster_size=1,
        ),
        baseline_language_distribution=None,
        window_start=now - timedelta(days=1),
        window_end=now,
    )

    assert summary["event_count"] == 0
    assert summary["singleton_rate"] == 0.0
    assert summary["large_cluster_size"] == 2
    assert summary["language_distribution"] == {}
    assert summary["baseline_language_distribution"] == {}
    assert summary["language_drift_score"] == 0.0
    assert summary["warning_keys"] == []


def test_compute_cluster_drift_summary_emits_all_warning_keys() -> None:
    now = datetime.now(tz=UTC).replace(microsecond=0)
    summary = compute_cluster_drift_summary(
        event_samples=[
            ClusterEventSample(item_count=1, has_contradictions=True, languages=(" ",)),
            ClusterEventSample(item_count=5, has_contradictions=False, languages=("ru",)),
        ],
        thresholds=ClusterDriftThresholds(
            singleton_rate_warn=0.1,
            large_cluster_rate_warn=0.1,
            contradiction_rate_warn=0.1,
            language_drift_warn=0.1,
            large_cluster_size=4,
        ),
        baseline_language_distribution={"en": 1.0},
        window_start=now - timedelta(days=1),
        window_end=now,
    )

    assert summary["warning_keys"] == [
        "singleton_rate",
        "large_cluster_tail",
        "contradiction_incidence",
        "language_distribution_drift",
    ]
    assert summary["language_distribution"] == {"ru": 0.5, "unknown": 0.5}


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


def test_load_latest_language_distribution_handles_missing_and_invalid_artifacts(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "cluster-drift"

    assert load_latest_language_distribution(artifact_dir) is None

    artifact_dir.mkdir()
    assert load_latest_language_distribution(artifact_dir) is None

    (artifact_dir / "2026-03-01.json").write_text(
        json.dumps({"language_distribution": {"en": "bad", "ru": 0.4}}),
        encoding="utf-8",
    )
    (artifact_dir / "2026-03-02.json").write_text(
        json.dumps({"language_distribution": "invalid"}),
        encoding="utf-8",
    )
    assert load_latest_language_distribution(artifact_dir) is None

    (artifact_dir / "2026-03-03.json").write_text(
        json.dumps({"language_distribution": {"en": "0.6", "ru": 0.4}}),
        encoding="utf-8",
    )
    assert load_latest_language_distribution(artifact_dir) == {"en": 0.6, "ru": 0.4}

    (artifact_dir / "2026-03-04.json").write_text(
        json.dumps({"language_distribution": {"en": "bad", "ru": 0.4}}),
        encoding="utf-8",
    )
    assert load_latest_language_distribution(artifact_dir) == {"ru": 0.4}


def test_write_cluster_drift_artifact_falls_back_for_invalid_window_end(tmp_path: Path) -> None:
    output_path = write_cluster_drift_artifact(
        artifact_dir=tmp_path / "cluster-drift",
        summary={"window_end": "invalid", "language_distribution": {}},
    )

    assert output_path.exists()
    assert output_path.suffix == ".json"
