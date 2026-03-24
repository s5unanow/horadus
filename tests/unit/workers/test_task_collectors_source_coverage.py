from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.workers.tasks as tasks_module
from src.core.source_coverage import CoverageCounts, CoverageHealthReport

pytestmark = pytest.mark.unit


def _session_maker(session: object):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


@pytest.mark.asyncio
async def test_monitor_source_coverage_async_persists_snapshot_and_records_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    report = CoverageHealthReport(
        generated_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        window_start=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        total=CoverageCounts(seen=4, processable=3, processed=2, deferred=1),
        dimensions=(),
        alerts=(
            SimpleNamespace(
                severity="warning",
                dimension="source_family",
                key="rss",
                label="rss",
                current_seen=2,
                previous_seen=6,
                message="drop",
            ),
        ),
    )
    health_calls: list[int] = []
    alert_calls: list[tuple[str, str]] = []
    warning_events: list[dict[str, object]] = []

    async def fake_build(**_: object) -> CoverageHealthReport:
        return report

    async def fake_load_latest(_session: object) -> SimpleNamespace:
        return SimpleNamespace(payload={"total": {"seen": 6}, "dimensions": []})

    async def fake_persist(
        _session: object,
        *,
        report: CoverageHealthReport,
        artifact_path: str | None,
    ) -> SimpleNamespace:
        assert report.total.seen == 4
        assert artifact_path is not None
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.coverage_helpers, "build_source_coverage_report", fake_build)
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "load_latest_coverage_snapshot",
        fake_load_latest,
    )
    monkeypatch.setattr(tasks_module.coverage_helpers, "persist_coverage_snapshot", fake_persist)
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "write_source_coverage_artifact",
        lambda *, artifact_dir, **_: Path(artifact_dir) / "coverage.json",
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "record_coverage_health",
        lambda *, report: health_calls.append(report.total.seen),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "record_coverage_drop_alert",
        lambda *, severity, dimension: alert_calls.append((severity, dimension)),
    )
    monkeypatch.setattr(
        tasks_module,
        "logger",
        SimpleNamespace(warning=lambda _message, **event: warning_events.append(event)),
    )

    result = await tasks_module.coverage_helpers.monitor_source_coverage_async(
        async_session_maker=tasks_module.async_session_maker,
        logger=tasks_module.logger,
    )

    assert result["task"] == "monitor_source_coverage"
    assert result["artifact_path"].endswith("coverage.json")
    assert result["total_seen"] == 4
    assert result["alert_count"] == 1
    assert health_calls == [4]
    assert alert_calls == [("warning", "source_family")]
    assert warning_events[0]["alert_count"] == 1
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_source_coverage_async_skips_warning_log_without_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()
    report = CoverageHealthReport(
        generated_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        window_start=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        total=CoverageCounts(seen=1, processable=1, processed=1),
        dimensions=(),
        alerts=(),
    )
    warning_events: list[dict[str, object]] = []

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "build_source_coverage_report",
        AsyncMock(return_value=report),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "load_latest_coverage_snapshot",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "persist_coverage_snapshot",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "write_source_coverage_artifact",
        lambda *, artifact_dir, **_: Path(artifact_dir) / "coverage.json",
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "record_coverage_health",
        lambda **_: None,
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "record_coverage_drop_alert",
        lambda **_: None,
    )
    monkeypatch.setattr(
        tasks_module,
        "logger",
        SimpleNamespace(warning=lambda _message, **event: warning_events.append(event)),
    )

    result = await tasks_module.coverage_helpers.monitor_source_coverage_async(
        async_session_maker=tasks_module.async_session_maker,
        logger=tasks_module.logger,
    )

    assert result["alert_count"] == 0
    assert warning_events == []


@pytest.mark.asyncio
async def test_monitor_source_coverage_async_removes_artifacts_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mock_session = AsyncMock()
    report = CoverageHealthReport(
        generated_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        window_start=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        total=CoverageCounts(seen=1, processable=1, processed=1),
        dimensions=(),
    )
    artifact_path = tmp_path / "source-coverage-20260324T120000Z.json"
    latest_path = tmp_path / "source-coverage-latest.json"
    artifact_path.write_text("artifact\n", encoding="utf-8")
    latest_path.write_text("latest\n", encoding="utf-8")
    mock_session.commit.side_effect = RuntimeError("commit failed")

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "build_source_coverage_report",
        AsyncMock(return_value=report),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "load_latest_coverage_snapshot",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "persist_coverage_snapshot",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "write_source_coverage_artifact",
        lambda **_: artifact_path,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await tasks_module.coverage_helpers.monitor_source_coverage_async(
            async_session_maker=tasks_module.async_session_maker,
            logger=tasks_module.logger,
        )

    assert artifact_path.exists() is False
    assert latest_path.exists() is False


@pytest.mark.asyncio
async def test_monitor_source_coverage_async_reraises_without_artifact_cleanup_when_build_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "build_source_coverage_report",
        AsyncMock(side_effect=RuntimeError("build failed")),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "load_latest_coverage_snapshot",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tasks_module.coverage_helpers,
        "write_source_coverage_artifact",
        lambda **_: pytest.fail("artifact write should not run"),
    )

    with pytest.raises(RuntimeError, match="build failed"):
        await tasks_module.coverage_helpers.monitor_source_coverage_async(
            async_session_maker=tasks_module.async_session_maker,
            logger=tasks_module.logger,
        )

    mock_session.commit.assert_not_awaited()
