from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core import observability
from tests.unit.core.test_observability import _FakeMetric

pytestmark = pytest.mark.unit


def test_coverage_recorders_update_gauges_and_clear_stale_labels(monkeypatch) -> None:
    coverage_volume = _FakeMetric()
    coverage_ratio = _FakeMetric()
    coverage_alerts = _FakeMetric()

    monkeypatch.setattr(observability, "SOURCE_COVERAGE_VOLUME", coverage_volume)
    monkeypatch.setattr(observability, "SOURCE_COVERAGE_PROCESSED_RATIO", coverage_ratio)
    monkeypatch.setattr(observability, "SOURCE_COVERAGE_DROP_ALERTS_TOTAL", coverage_alerts)
    monkeypatch.setattr(observability, "_ACTIVE_COVERAGE_VOLUME_LABELS", set())
    monkeypatch.setattr(observability, "_ACTIVE_COVERAGE_RATIO_LABELS", set())

    observability.record_coverage_health(
        report=SimpleNamespace(
            total=SimpleNamespace(
                seen=4,
                processable=3,
                processed=2,
                deferred=1,
                skipped_by_language=1,
                pending_processable=1,
                processing=0,
                error=0,
            ),
            dimensions=(
                SimpleNamespace(
                    dimension="language",
                    rows=(
                        SimpleNamespace(
                            key="en",
                            counts=SimpleNamespace(
                                seen=2,
                                processable=2,
                                processed=2,
                                deferred=0,
                                skipped_by_language=0,
                                pending_processable=0,
                                processing=0,
                                error=0,
                            ),
                            processed_ratio=1.0,
                        ),
                    ),
                ),
            ),
        )
    )
    observability.record_coverage_drop_alert(severity="warning", dimension="language")
    observability.record_coverage_health(
        report=SimpleNamespace(
            total=SimpleNamespace(
                seen=1,
                processable=1,
                processed=1,
                deferred=0,
                skipped_by_language=0,
                pending_processable=0,
                processing=0,
                error=0,
            ),
            dimensions=(),
        )
    )

    assert coverage_volume.children[
        (("dimension", "total"), ("key", "all"), ("status", "seen"))
    ].set_calls == [4, 1]
    assert coverage_volume.children[
        (("dimension", "language"), ("key", "en"), ("status", "seen"))
    ].set_calls == [2, 0]
    assert coverage_ratio.children[(("dimension", "language"), ("key", "en"))].set_calls == [1.0, 0]
    assert coverage_alerts.children[
        (("dimension", "language"), ("severity", "warning"))
    ].inc_calls == [None]


def test_coverage_recorders_allow_reports_without_total(monkeypatch) -> None:
    coverage_volume = _FakeMetric()
    coverage_ratio = _FakeMetric()

    monkeypatch.setattr(observability, "SOURCE_COVERAGE_VOLUME", coverage_volume)
    monkeypatch.setattr(observability, "SOURCE_COVERAGE_PROCESSED_RATIO", coverage_ratio)
    monkeypatch.setattr(observability, "_ACTIVE_COVERAGE_VOLUME_LABELS", set())
    monkeypatch.setattr(observability, "_ACTIVE_COVERAGE_RATIO_LABELS", set())

    observability.record_coverage_health(
        report=SimpleNamespace(
            dimensions=(
                SimpleNamespace(
                    dimension="topic",
                    rows=(
                        SimpleNamespace(
                            key="world",
                            counts=SimpleNamespace(
                                seen=1,
                                processable=1,
                                processed=1,
                                deferred=0,
                                skipped_by_language=0,
                                pending_processable=0,
                                processing=0,
                                error=0,
                            ),
                            processed_ratio=1.0,
                        ),
                    ),
                ),
            )
        )
    )

    assert coverage_volume.children[
        (("dimension", "topic"), ("key", "world"), ("status", "seen"))
    ].set_calls == [1]
