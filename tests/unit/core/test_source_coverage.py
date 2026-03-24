from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.source_coverage import (
    CoverageCounts,
    CoverageDimensionSummary,
    CoverageHealthReport,
    CoverageSegment,
    _as_utc,
    _build_alerts,
    _index_previous_seen,
    _normalize_language,
    _normalize_status,
    _normalize_topic_values,
    _slug_text,
    build_source_coverage_report,
    deserialize_coverage_report,
    load_latest_coverage_snapshot,
    persist_coverage_snapshot,
    serialize_coverage_report,
    write_source_coverage_artifact,
)
from src.storage.models import ProcessingStatus, SourceType

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_build_source_coverage_report_distinguishes_processed_deferred_and_skipped() -> None:
    now = datetime(2026, 3, 24, 12, 0, tzinfo=UTC)
    mock_session = AsyncMock()
    mock_session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (
                ProcessingStatus.CLASSIFIED,
                None,
                "en",
                SourceType.RSS,
                "wire",
                {"categories": ["world", "politics"]},
            ),
            (
                ProcessingStatus.PENDING,
                "unsupported_language:fr:defer",
                "fr",
                SourceType.RSS,
                "wire",
                {"categories": ["world"]},
            ),
            (
                ProcessingStatus.NOISE,
                "unsupported_language:es:skip",
                "es",
                SourceType.GDELT,
                "aggregator",
                {"themes": ["MILITARY"]},
            ),
            (
                ProcessingStatus.PENDING,
                None,
                "uk",
                SourceType.TELEGRAM,
                "regional",
                {"categories": ["geopolitics"]},
            ),
        ]
    )

    report = await build_source_coverage_report(session=mock_session, window_end=now)

    assert report.total.seen == 4
    assert report.total.processable == 2
    assert report.total.processed == 1
    assert report.total.deferred == 1
    assert report.total.skipped_by_language == 1
    assert report.total.pending_processable == 1

    dimensions = {summary.dimension: summary for summary in report.dimensions}
    language_rows = {row.key: row for row in dimensions["language"].rows}
    assert language_rows["en"].counts.processed == 1
    assert language_rows["fr"].counts.deferred == 1
    assert language_rows["es"].counts.skipped_by_language == 1
    assert language_rows["uk"].counts.pending_processable == 1

    topic_rows = {row.key: row for row in dimensions["topic"].rows}
    assert topic_rows["world"].counts.seen == 2
    assert topic_rows["military"].counts.skipped_by_language == 1
    assert topic_rows["geopolitics"].counts.pending_processable == 1


@pytest.mark.asyncio
async def test_build_source_coverage_report_emits_drop_alerts_against_previous_snapshot() -> None:
    now = datetime(2026, 3, 24, 12, 0, tzinfo=UTC)
    mock_session = AsyncMock()
    mock_session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (
                ProcessingStatus.CLASSIFIED,
                None,
                "en",
                SourceType.RSS,
                "wire",
                {"categories": ["world"]},
            ),
        ]
    )
    previous_payload = {
        "total": {"seen": 10},
        "dimensions": [
            {
                "dimension": "language",
                "rows": [{"key": "en", "counts": {"seen": 9}}],
            },
            {
                "dimension": "source_family",
                "rows": [{"key": "rss", "counts": {"seen": 8}}],
            },
        ],
    }

    report = await build_source_coverage_report(
        session=mock_session,
        window_end=now,
        previous_snapshot_payload=previous_payload,
    )

    alert_dimensions = {alert.dimension for alert in report.alerts}
    assert {"total", "language", "source_family"} <= alert_dimensions
    assert report.alerts[0].severity == "critical"
    assert report.alerts[0].current_seen == 1
    assert report.alerts[0].previous_seen == 10


def test_source_coverage_payload_roundtrip_and_artifact_write(tmp_path: Path) -> None:
    report = CoverageHealthReport(
        generated_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        window_start=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        total=CoverageCounts(seen=3, processable=2, processed=1, skipped_by_language=1),
        dimensions=(
            CoverageDimensionSummary(
                dimension="language",
                multi_value=False,
                rows=(
                    CoverageSegment(
                        key="en",
                        label="en",
                        counts=CoverageCounts(seen=2, processable=2, processed=1),
                        processed_ratio=0.5,
                        pending_ratio=0.5,
                        change_ratio=None,
                    ),
                ),
            ),
        ),
        snapshot_id=uuid4(),
        artifact_path="artifacts/source_coverage/source-coverage-latest.json",
    )

    payload = serialize_coverage_report(report)
    restored = deserialize_coverage_report(payload)
    artifact_path = write_source_coverage_artifact(restored, artifact_dir=tmp_path)

    assert restored.total.seen == 3
    assert restored.dimensions[0].rows[0].processed_ratio == 0.5
    assert artifact_path.name.startswith("source-coverage-")
    assert (tmp_path / "source-coverage-latest.json").exists()


def test_source_coverage_normalization_helpers_cover_fallbacks() -> None:
    naive = datetime(2026, 3, 24, 12, 0, tzinfo=UTC).replace(tzinfo=None)

    assert _as_utc(naive).tzinfo is UTC
    assert _slug_text("   !!!   ") is None
    assert _normalize_language(None) == "unknown"
    assert _normalize_language("english") == "en"
    assert _normalize_language("english-us") == "en"
    assert _normalize_language("Spanish") == "es"
    assert _normalize_language("German") == "de"
    assert _normalize_language("pt-br") == "pt"
    assert _normalize_language("-") == "unknown"
    assert _normalize_status(" ") == "pending"
    assert _normalize_topic_values(None) == ("unconfigured",)
    assert _normalize_topic_values({"categories": ["  "], "themes": "not-a-list"}) == (
        "unconfigured",
    )


def test_index_previous_seen_and_deserialize_skip_invalid_shapes() -> None:
    assert _index_previous_seen(None) == {}
    assert _index_previous_seen({"total": {"seen": 3}, "dimensions": "bad"}) == {
        ("total", "all"): 3
    }
    assert _index_previous_seen(
        {
            "total": "bad",
            "dimensions": [
                "skip",
                {"dimension": "language", "rows": "bad"},
                {
                    "dimension": "language",
                    "rows": [
                        "skip",
                        {"key": "en", "counts": "bad"},
                        {"key": "fr", "counts": {"seen": 2}},
                    ],
                },
            ],
        }
    ) == {("language", "fr"): 2}

    restored = deserialize_coverage_report(
        {
            "generated_at": "2026-03-24T12:00:00+00:00",
            "window_start": "2026-03-23T12:00:00+00:00",
            "window_end": "2026-03-24T12:00:00+00:00",
            "lookback_hours": 24,
            "total": {"seen": 1},
            "dimensions": [
                "skip",
                {"dimension": "language", "rows": ["skip", {"key": "en", "counts": {"seen": 1}}]},
            ],
            "alerts": ["skip", {"severity": "warning", "dimension": "language"}],
        }
    )

    assert restored.dimensions[0].rows[0].key == "en"
    assert restored.alerts[0].dimension == "language"


def test_build_alerts_covers_warning_and_non_alert_paths() -> None:
    alerts = _build_alerts(
        total=CoverageCounts(seen=4),
        dimensions=(
            CoverageDimensionSummary(
                dimension="language",
                multi_value=False,
                rows=(
                    CoverageSegment(
                        key="en",
                        label="en",
                        counts=CoverageCounts(seen=4),
                        processed_ratio=1.0,
                        pending_ratio=0.0,
                        change_ratio=None,
                    ),
                    CoverageSegment(
                        key="bg",
                        label="bg",
                        counts=CoverageCounts(seen=4),
                        processed_ratio=1.0,
                        pending_ratio=0.0,
                        change_ratio=None,
                    ),
                ),
            ),
        ),
        previous_payload={
            "total": {"seen": 4},
            "dimensions": [
                {
                    "dimension": "language",
                    "rows": [
                        {"key": "en", "counts": {"seen": 10}},
                        {"key": "bg", "counts": {"seen": 6}},
                    ],
                }
            ],
        },
    )

    assert len(alerts) == 1
    assert alerts[0].dimension == "language"
    assert alerts[0].severity == "warning"


@pytest.mark.asyncio
async def test_load_and_persist_coverage_snapshot_cover_snapshot_helpers() -> None:
    snapshot_id = uuid4()
    report = CoverageHealthReport(
        generated_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        window_start=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        total=CoverageCounts(seen=2, processable=2, processed=1),
        dimensions=(),
    )
    load_session = AsyncMock()
    load_session.scalar.return_value = SimpleNamespace(id=snapshot_id)
    persisted: list[object] = []

    loaded = await load_latest_coverage_snapshot(load_session)
    assert loaded.id == snapshot_id

    async def fake_flush() -> None:
        persisted[0].id = snapshot_id

    persist_session = SimpleNamespace(
        add=lambda obj: persisted.append(obj),
        flush=AsyncMock(side_effect=fake_flush),
    )
    snapshot = await persist_coverage_snapshot(
        persist_session,
        report=report,
        artifact_path="artifacts/source_coverage/source-coverage-latest.json",
    )

    assert snapshot.payload["snapshot_id"] == str(snapshot_id)
