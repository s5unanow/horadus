from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.workers.tasks as tasks_module

pytestmark = pytest.mark.unit


def _session_maker(session: object):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


@pytest.mark.asyncio
async def test_monitor_cluster_drift_async_handles_mixed_language_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        ("event-1", True, "active", 3, ["en", None, "bg"]),
        ("event-2", False, "dormant", None, "not-a-list"),
    ]
    mock_session = AsyncMock()
    mock_session.execute.return_value = SimpleNamespace(all=lambda: rows)
    captured: dict[str, object] = {}

    def fake_compute(
        *, event_samples, thresholds, baseline_language_distribution, window_start, window_end
    ):
        captured["event_samples"] = event_samples
        captured["thresholds"] = thresholds
        captured["baseline_language_distribution"] = baseline_language_distribution
        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "event_count": 2,
            "warning_keys": "singleton_rate",
            "singleton_rate": 0.5,
            "large_cluster_rate": 0.0,
            "contradiction_rate": 0.5,
            "language_drift_score": 0.25,
        }

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(
        tasks_module.settings, "CLUSTER_DRIFT_ARTIFACT_DIR", "artifacts/cluster_drift"
    )
    monkeypatch.setattr(
        tasks_module,
        "load_latest_language_distribution",
        lambda _path: {"en": 1.0},
    )
    monkeypatch.setattr(tasks_module, "compute_cluster_drift_summary", fake_compute)

    def fake_write_cluster_drift_artifact(*, artifact_dir, summary):
        del summary
        return Path(artifact_dir) / "cluster_drift.json"

    monkeypatch.setattr(
        tasks_module,
        "write_cluster_drift_artifact",
        fake_write_cluster_drift_artifact,
    )

    result = await tasks_module._monitor_cluster_drift_async()

    event_samples = captured["event_samples"]
    assert event_samples[0].languages == ("en", "bg")
    assert event_samples[1].languages == ()
    assert result["warning_keys"] == []
    assert result["artifact_path"].endswith("cluster_drift.json")


@pytest.mark.asyncio
async def test_monitor_cluster_drift_async_skips_closed_zero_item_stubs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        ("event-1", True, "closed", 0, []),
        ("event-2", False, "active", 2, ["en"]),
    ]
    mock_session = AsyncMock()
    mock_session.execute.return_value = SimpleNamespace(all=lambda: rows)
    captured: dict[str, object] = {}

    def fake_compute(
        *, event_samples, thresholds, baseline_language_distribution, window_start, window_end
    ):
        del thresholds, baseline_language_distribution, window_start, window_end
        captured["event_samples"] = event_samples
        now = datetime.now(tz=UTC).isoformat()
        return {
            "window_start": now,
            "window_end": now,
            "event_count": len(event_samples),
            "warning_keys": [],
            "singleton_rate": 0.0,
            "large_cluster_rate": 0.0,
            "contradiction_rate": 0.0,
            "language_drift_score": 0.0,
        }

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(
        tasks_module.settings, "CLUSTER_DRIFT_ARTIFACT_DIR", "artifacts/cluster_drift"
    )
    monkeypatch.setattr(tasks_module, "load_latest_language_distribution", lambda _path: None)
    monkeypatch.setattr(tasks_module, "compute_cluster_drift_summary", fake_compute)

    def fake_write_cluster_drift_artifact(*, artifact_dir, summary):
        del summary
        return Path(artifact_dir) / "cluster_drift.json"

    monkeypatch.setattr(
        tasks_module,
        "write_cluster_drift_artifact",
        fake_write_cluster_drift_artifact,
    )

    result = await tasks_module._monitor_cluster_drift_async()

    event_samples = captured["event_samples"]
    assert len(event_samples) == 1
    assert event_samples[0].item_count == 2
    assert result["event_count"] == 1
