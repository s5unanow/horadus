from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core import calibration_dashboard as calibration_dashboard_module
from src.core.calibration_dashboard import (
    CalibrationBucketSummary,
    CalibrationCoverageSummary,
    CalibrationDashboardReport,
    CalibrationDashboardService,
    CalibrationDriftAlert,
    TrendCoverageSummary,
)
from src.storage.models import OutcomeType

pytestmark = pytest.mark.unit


def test_render_ascii_sparkline_returns_flat_line_for_constant_values() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    assert service._render_ascii_sparkline([0.2, 0.2, 0.2]) == "---"


def test_render_ascii_sparkline_returns_varying_chars_for_changes() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    chart = service._render_ascii_sparkline([0.1, 0.25, 0.4, 0.3])
    assert len(chart) == 4
    assert len(set(chart)) > 1


def test_build_reliability_notes_formats_bucket_statement() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    notes = service._build_reliability_notes(
        [
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=7,
                actual_rate=0.43,
                expected_rate=0.25,
                calibration_error=0.18,
            )
        ]
    )
    assert notes == ["When we predicted 20%-30%, it happened 43% of the time (n=7)."]


def test_build_drift_alerts_returns_warning_and_critical_entries() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=25,
        resolved_predictions=25,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=2,
        trends_meeting_min=2,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )
    alerts = service._build_drift_alerts(
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=9,
                actual_rate=0.56,
                expected_rate=0.25,
                calibration_error=0.31,
            )
        ],
        mean_brier_score=0.32,
        resolved_predictions=25,
        coverage=coverage,
    )

    assert len(alerts) == 2
    assert alerts[0].alert_type == "mean_brier_drift"
    assert alerts[0].severity == "critical"
    assert alerts[1].alert_type == "bucket_error_drift"
    assert alerts[1].severity == "critical"


def test_build_drift_alerts_skips_when_sample_size_is_too_low() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=5,
        resolved_predictions=5,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=1,
        trends_meeting_min=1,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )
    alerts = service._build_drift_alerts(
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.7,
                bucket_end=0.8,
                prediction_count=2,
                actual_rate=1.0,
                expected_rate=0.75,
                calibration_error=0.25,
            )
        ],
        mean_brier_score=0.35,
        resolved_predictions=5,
        coverage=coverage,
    )
    assert alerts == []


def test_build_drift_alerts_returns_coverage_only_when_thresholds_are_not_breached() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=25,
        resolved_predictions=25,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=2,
        trends_meeting_min=2,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )

    alerts = service._build_drift_alerts(
        calibration_curve=[],
        mean_brier_score=0.05,
        resolved_predictions=25,
        coverage=coverage,
    )

    assert alerts == []


def test_build_drift_alerts_handles_missing_mean_and_non_breaching_bucket_error() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=25,
        resolved_predictions=25,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=2,
        trends_meeting_min=2,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )

    alerts = service._build_drift_alerts(
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.4,
                bucket_end=0.5,
                prediction_count=3,
                actual_rate=0.45,
                expected_rate=0.45,
                calibration_error=0.01,
            )
        ],
        mean_brier_score=None,
        resolved_predictions=25,
        coverage=coverage,
    )

    assert alerts == []


def test_build_coverage_summary_marks_low_sample_trends() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    summary = service._build_coverage_summary(
        total_by_trend={},
        resolved_by_trend={},
        trend_name_by_id={},
    )
    assert summary.coverage_sufficient is False
    assert summary.total_predictions == 0


def test_build_coverage_alerts_emits_low_sample_warning() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=8,
        resolved_predictions=3,
        unresolved_predictions=5,
        overall_resolved_ratio=0.375,
        trends_with_predictions=1,
        trends_meeting_min=0,
        trends_below_min=1,
        low_sample_trends=[
            TrendCoverageSummary(
                trend_id=uuid4(),
                trend_name="EU-Russia",
                total_predictions=8,
                resolved_predictions=3,
                resolved_ratio=0.375,
            )
        ],
        coverage_sufficient=False,
    )
    alerts = service._build_coverage_alerts(coverage)
    assert alerts
    assert alerts[0].alert_type == "low_sample_coverage"


def test_build_reliability_summary_aggregates_source_metrics() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcome_id_one = uuid4()
    outcome_id_two = uuid4()
    outcome_id_three = uuid4()

    summary = service._build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=2,
        pairs=[
            ("source-a", "Reuters", outcome_id_one),
            ("source-a", "Reuters", outcome_id_two),
            ("source-b", "AP", outcome_id_three),
        ],
        outcome_metrics={
            outcome_id_one: (0.8, 1.0, 0.04),
            outcome_id_two: (0.2, 0.0, 0.04),
            outcome_id_three: (0.6, 1.0, 0.16),
        },
    )

    assert summary.dimension == "source"
    assert summary.advisory_only is True
    assert summary.eligible_rows == 1
    assert summary.sparse_rows == 1
    assert summary.rows[0].label == "Reuters"
    assert summary.rows[0].sample_size == 2
    assert summary.rows[0].mean_predicted_probability == pytest.approx(0.5)
    assert summary.rows[0].observed_rate == pytest.approx(0.5)
    assert summary.rows[0].mean_brier_score == pytest.approx(0.04)
    assert summary.rows[0].calibration_gap == pytest.approx(0.0)
    assert summary.rows[0].eligible is True


def test_build_reliability_summary_applies_sparse_guardrails() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcome_id_one = uuid4()
    outcome_id_two = uuid4()

    summary = service._build_reliability_summary_from_pairs(
        dimension="source_tier",
        min_sample_size=3,
        pairs=[
            ("wire", "wire", outcome_id_one),
            ("wire", "wire", outcome_id_one),
            ("wire", "wire", outcome_id_two),
        ],
        outcome_metrics={
            outcome_id_one: (0.7, 1.0, 0.09),
            outcome_id_two: (0.4, 0.0, 0.16),
        },
    )

    assert summary.eligible_rows == 0
    assert summary.sparse_rows == 1
    assert summary.rows[0].sample_size == 2
    assert summary.rows[0].eligible is False
    assert summary.rows[0].confidence == "insufficient"
    assert "Sparse sample" in summary.rows[0].advisory_note


@pytest.mark.asyncio
async def test_emit_drift_notifications_forwards_to_webhook_notifier() -> None:
    notifier = AsyncMock()
    service = CalibrationDashboardService(
        session=AsyncMock(),
        drift_alert_notifier=notifier,
    )
    generated_at = datetime(2026, 2, 9, tzinfo=UTC)
    alerts = [
        CalibrationDriftAlert(
            alert_type="mean_brier_drift",
            severity="warning",
            metric_name="mean_brier_score",
            metric_value=0.22,
            threshold=0.2,
            sample_size=12,
            message="Threshold exceeded.",
        )
    ]

    await service._emit_drift_notifications(
        trend_id=None,
        drift_alerts=alerts,
        generated_at=generated_at,
    )

    notifier.notify.assert_awaited_once()


def test_render_ascii_sparkline_handles_empty_and_single_value_inputs() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    assert service._render_ascii_sparkline([]) == ""
    assert service._render_ascii_sparkline([0.5]) == "-"


def test_build_coverage_alerts_returns_empty_when_coverage_is_healthy() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=10,
        resolved_predictions=8,
        unresolved_predictions=2,
        overall_resolved_ratio=0.8,
        trends_with_predictions=2,
        trends_meeting_min=2,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )

    assert service._build_coverage_alerts(coverage) == []


def test_build_coverage_alerts_handles_zero_predictions_window() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=0,
        resolved_predictions=0,
        unresolved_predictions=0,
        overall_resolved_ratio=0.0,
        trends_with_predictions=0,
        trends_meeting_min=0,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=False,
    )

    alerts = service._build_coverage_alerts(coverage)

    assert len(alerts) == 1
    assert alerts[0].message == "No calibration predictions found in the dashboard window."


@pytest.mark.parametrize(
    ("value", "warn_threshold", "critical_threshold", "expected"),
    [
        (0.31, 0.2, 0.3, ("critical", 0.3)),
        (0.21, 0.2, 0.3, ("warning", 0.2)),
        (0.19, 0.2, 0.3, (None, None)),
    ],
)
def test_severity_and_threshold_returns_expected_bands(
    value: float,
    warn_threshold: float,
    critical_threshold: float,
    expected: tuple[str | None, float | None],
) -> None:
    assert (
        CalibrationDashboardService._severity_and_threshold(
            value=value,
            warn_threshold=warn_threshold,
            critical_threshold=critical_threshold,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_emit_drift_notifications_returns_early_without_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_alert = AsyncMock()
    warning_logger = AsyncMock()
    monkeypatch.setattr(
        calibration_dashboard_module, "record_calibration_drift_alert", record_alert
    )
    monkeypatch.setattr(calibration_dashboard_module.logger, "warning", warning_logger)

    notifier = AsyncMock()
    service = CalibrationDashboardService(session=AsyncMock(), drift_alert_notifier=notifier)

    await service._emit_drift_notifications(
        trend_id=uuid4(),
        drift_alerts=[],
        generated_at=datetime(2026, 2, 9, tzinfo=UTC),
    )

    notifier.notify.assert_not_called()
    record_alert.assert_not_called()
    warning_logger.assert_not_called()


@pytest.mark.asyncio
async def test_emit_drift_notifications_swallows_notifier_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, str]] = []
    log_calls: list[dict[str, object]] = []

    def record_alert(*, alert_type: str, severity: str) -> None:
        recorded.append((alert_type, severity))

    def log_warning(event: str, **kwargs: object) -> None:
        log_calls.append({"message": event, **kwargs})

    monkeypatch.setattr(
        calibration_dashboard_module,
        "record_calibration_drift_alert",
        record_alert,
    )
    monkeypatch.setattr(calibration_dashboard_module.logger, "warning", log_warning)

    notifier = AsyncMock()
    notifier.notify.side_effect = RuntimeError("webhook down")
    service = CalibrationDashboardService(session=AsyncMock(), drift_alert_notifier=notifier)
    alert = CalibrationDriftAlert(
        alert_type="mean_brier_drift",
        severity="warning",
        metric_name="mean_brier_score",
        metric_value=0.22,
        threshold=0.2,
        sample_size=12,
        message="Threshold exceeded.",
    )

    await service._emit_drift_notifications(
        trend_id=uuid4(),
        drift_alerts=[alert],
        generated_at=datetime(2026, 2, 9, tzinfo=UTC),
    )

    assert recorded == [("mean_brier_drift", "warning")]
    assert len(log_calls) == 2
    assert log_calls[-1]["message"] == "Calibration drift webhook notifier failed unexpectedly"


@pytest.mark.asyncio
async def test_build_dashboard_assembles_report_from_dependencies() -> None:
    service = CalibrationDashboardService(session=AsyncMock(), drift_alert_notifier=AsyncMock())
    trend_id = uuid4()
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    end_date = datetime(2026, 2, 1, tzinfo=UTC)
    outcomes = [
        SimpleNamespace(id=uuid4(), trend_id=trend_id, outcome=OutcomeType.OCCURRED.value),
        SimpleNamespace(id=uuid4(), trend_id=trend_id, outcome=None),
    ]
    scored_outcomes = [outcomes[0]]
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=2,
        resolved_predictions=1,
        unresolved_predictions=1,
        overall_resolved_ratio=0.5,
        trends_with_predictions=1,
        trends_meeting_min=0,
        trends_below_min=1,
        low_sample_trends=[],
        coverage_sufficient=False,
    )
    calibration_curve = [
        CalibrationBucketSummary(
            bucket_start=0.4,
            bucket_end=0.5,
            prediction_count=1,
            actual_rate=1.0,
            expected_rate=0.45,
            calibration_error=0.55,
        )
    ]
    brier_series = [
        SimpleNamespace(
            period_start=start_date,
            period_end=end_date,
            mean_brier_score=0.2,
            sample_size=1,
        )
    ]
    drift_alerts = [
        CalibrationDriftAlert(
            alert_type="bucket_error_drift",
            severity="critical",
            metric_name="max_bucket_calibration_error",
            metric_value=0.55,
            threshold=0.3,
            sample_size=1,
            message="bad bucket",
        )
    ]
    movements = [
        SimpleNamespace(
            trend_id=trend_id,
            trend_name="Trend",
            current_probability=0.5,
            weekly_change=0.1,
            risk_level="high",
            top_movers_7d=["evidence"],
            movement_chart="-",
        )
    ]

    def build_coverage_summary(**_: object) -> CalibrationCoverageSummary:
        return coverage

    def build_brier_timeseries(
        _loaded: list[SimpleNamespace],
        period_end: datetime,
    ) -> list[SimpleNamespace]:
        _ = period_end
        return brier_series

    service._load_outcomes = AsyncMock(return_value=outcomes)
    service._scored_outcomes = lambda loaded: scored_outcomes if loaded == outcomes else []
    service._count_predictions_by_trend = lambda loaded: {trend_id: len(loaded)}
    service._load_trend_names = AsyncMock(return_value={trend_id: "Trend"})
    service._build_coverage_summary = build_coverage_summary
    service._build_source_reliability_diagnostics = AsyncMock(
        return_value=("source-summary", "tier-summary")
    )
    service._build_brier_timeseries = build_brier_timeseries
    service._build_drift_alerts = lambda **_: drift_alerts
    service._emit_drift_notifications = AsyncMock()
    service._load_trend_movements = AsyncMock(return_value=movements)

    monkeypatch_buckets = pytest.MonkeyPatch()
    monkeypatch_buckets.setattr(
        calibration_dashboard_module,
        "build_calibration_buckets",
        lambda loaded: calibration_curve if loaded == scored_outcomes else [],
    )
    try:
        report = await service.build_dashboard(
            trend_id=trend_id,
            start_date=start_date,
            end_date=end_date,
        )
    finally:
        monkeypatch_buckets.undo()

    assert isinstance(report, CalibrationDashboardReport)
    assert report.total_predictions == 2
    assert report.resolved_predictions == 1
    assert report.mean_brier_score == 0.2
    assert report.calibration_curve == calibration_curve
    assert report.reliability_notes == [
        "When we predicted 40%-50%, it happened 100% of the time (n=1)."
    ]
    assert report.trend_movements == movements
    assert report.source_reliability == "source-summary"
    assert report.source_tier_reliability == "tier-summary"
    service._emit_drift_notifications.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_outcomes_and_trend_names_use_session_results() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    trend_id = uuid4()
    outcomes = [SimpleNamespace(id=uuid4(), trend_id=trend_id)]
    trend_rows = [(trend_id, "Trend A")]
    outcome_scalars = MagicMock()
    outcome_scalars.all.return_value = outcomes
    session.scalars = AsyncMock(return_value=outcome_scalars)
    execute_result = MagicMock()
    execute_result.all.return_value = trend_rows
    session.execute = AsyncMock(return_value=execute_result)

    loaded = await service._load_outcomes(
        trend_id=trend_id,
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 2, 1, tzinfo=UTC),
    )
    trend_names = await service._load_trend_names((trend_id,))

    assert loaded == outcomes
    assert trend_names == {trend_id: "Trend A"}
    assert await service._load_trend_names(()) == {}
    assert (
        await service._load_outcomes(
            trend_id=None,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        == outcomes
    )


def test_count_predictions_by_trend_and_coverage_summary_track_non_empty_inputs() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    trend_a = uuid4()
    trend_b = uuid4()
    outcomes = [
        SimpleNamespace(trend_id=trend_a),
        SimpleNamespace(trend_id=trend_a),
        SimpleNamespace(trend_id=trend_b),
    ]

    counts = service._count_predictions_by_trend(outcomes)
    summary = service._build_coverage_summary(
        total_by_trend=counts,
        resolved_by_trend={trend_a: 2, trend_b: 1},
        trend_name_by_id={trend_a: "Trend A", trend_b: "Trend B"},
    )

    assert counts == {trend_a: 2, trend_b: 1}
    assert summary.resolved_predictions == 3
    assert summary.unresolved_predictions == 0
    assert summary.coverage_sufficient is False
    assert summary.trends_meeting_min == 0


@pytest.mark.asyncio
async def test_build_source_reliability_diagnostics_handles_empty_and_populated_inputs() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())

    empty_source, empty_tier = await service._build_source_reliability_diagnostics(
        scored_outcomes=[]
    )
    assert empty_source.rows == []
    assert empty_tier.rows == []

    occurred = SimpleNamespace(
        id=uuid4(),
        predicted_probability=0.8,
        outcome=OutcomeType.OCCURRED.value,
        brier_score=None,
    )
    partial = SimpleNamespace(
        id=uuid4(),
        predicted_probability=0.6,
        outcome=OutcomeType.PARTIAL.value,
        brier_score=0.01,
    )
    ignored = SimpleNamespace(
        id=uuid4(),
        predicted_probability=0.3,
        outcome=OutcomeType.SUPERSEDED.value,
        brier_score=None,
    )
    invalid = SimpleNamespace(
        id=uuid4(),
        predicted_probability=0.4,
        outcome="invalid",
        brier_score=0.2,
    )
    missing = SimpleNamespace(
        id=uuid4(),
        predicted_probability=0.5,
        outcome=None,
        brier_score=0.1,
    )
    ap_source_id = uuid4()
    execute_result = MagicMock()
    execute_result.all.return_value = [
        (occurred.id, uuid4(), "Reuters", "wire"),
        (partial.id, ap_source_id, "AP", None),
        (partial.id, ap_source_id, "AP", None),
    ]
    session.execute = AsyncMock(return_value=execute_result)

    source_summary, tier_summary = await service._build_source_reliability_diagnostics(
        scored_outcomes=[occurred, partial, ignored, invalid, missing]
    )

    assert source_summary.dimension == "source"
    assert len(source_summary.rows) == 2
    assert tier_summary.rows[0].label in {"wire", "unknown"}
    assert all(row.sample_size == 1 for row in source_summary.rows)


@pytest.mark.asyncio
async def test_build_source_reliability_diagnostics_skips_rows_without_brier_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    monkeypatch.setattr(calibration_dashboard_module, "calculate_brier_score", lambda *_: None)

    source_summary, tier_summary = await service._build_source_reliability_diagnostics(
        scored_outcomes=[
            SimpleNamespace(
                id=uuid4(),
                predicted_probability=0.6,
                outcome=OutcomeType.OCCURRED.value,
                brier_score=None,
            )
        ]
    )

    assert source_summary.rows == []
    assert tier_summary.rows == []


@pytest.mark.parametrize(
    ("outcome_type", "expected"),
    [
        (OutcomeType.OCCURRED, 1.0),
        (OutcomeType.DID_NOT_OCCUR, 0.0),
        (OutcomeType.PARTIAL, 0.5),
        (OutcomeType.SUPERSEDED, None),
    ],
)
def test_actual_outcome_value_maps_supported_outcomes(
    outcome_type: OutcomeType, expected: float | None
) -> None:
    assert CalibrationDashboardService._actual_outcome_value(outcome_type) == expected


@pytest.mark.parametrize(
    ("sample_size", "min_sample_size", "expected"),
    [
        (1, 2, "insufficient"),
        (2, 2, "low"),
        (4, 2, "medium"),
        (6, 2, "high"),
    ],
)
def test_confidence_band_scales_with_sample_size(
    sample_size: int, min_sample_size: int, expected: str
) -> None:
    assert (
        CalibrationDashboardService._confidence_band(
            sample_size=sample_size,
            min_sample_size=min_sample_size,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("sample_size", "min_sample_size", "contains"),
    [
        (1, 2, "Sparse sample"),
        (2, 2, "Advisory-only diagnostic"),
    ],
)
def test_advisory_note_reflects_sample_sufficiency(
    sample_size: int, min_sample_size: int, contains: str
) -> None:
    note = CalibrationDashboardService._advisory_note(
        sample_size=sample_size,
        min_sample_size=min_sample_size,
    )
    assert contains in note


def test_scored_outcomes_filters_invalid_and_unscorable_rows() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcomes = [
        SimpleNamespace(predicted_probability=0.8, outcome=OutcomeType.OCCURRED.value),
        SimpleNamespace(predicted_probability=0.1, outcome="invalid"),
        SimpleNamespace(predicted_probability=0.3, outcome=None),
        SimpleNamespace(predicted_probability=0.2, outcome=OutcomeType.SUPERSEDED.value),
    ]

    scored = service._scored_outcomes(outcomes)

    assert scored == [outcomes[0]]


def test_build_reliability_summary_skips_pairs_without_metrics() -> None:
    service = CalibrationDashboardService(session=AsyncMock())

    summary = service._build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=2,
        pairs=[("missing", "Missing", uuid4())],
        outcome_metrics={},
    )

    assert summary.rows == []


def test_build_brier_timeseries_groups_scores_by_week() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcomes = [
        SimpleNamespace(
            prediction_date=datetime(2026, 2, 3, 12, tzinfo=UTC),
            predicted_probability=0.8,
            outcome=OutcomeType.OCCURRED.value,
            brier_score=None,
        ),
        SimpleNamespace(
            prediction_date=datetime(2026, 2, 4, 12, tzinfo=UTC),
            predicted_probability=0.2,
            outcome=OutcomeType.DID_NOT_OCCUR.value,
            brier_score=0.04,
        ),
        SimpleNamespace(
            prediction_date=datetime(2026, 2, 11, 12, tzinfo=UTC),
            predicted_probability=0.6,
            outcome="bad-value",
            brier_score=0.16,
        ),
    ]

    series = service._build_brier_timeseries(
        outcomes,
        period_end=datetime(2026, 2, 28, tzinfo=UTC),
    )

    assert len(series) == 1
    assert series[0].period_start == datetime(2026, 2, 2, tzinfo=UTC)
    assert series[0].sample_size == 2
    assert series[0].mean_brier_score == pytest.approx(0.04)


def test_build_brier_timeseries_skips_missing_and_unscorable_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CalibrationDashboardService(session=AsyncMock())

    def maybe_score(predicted_probability: float, _outcome_type: OutcomeType) -> float | None:
        return None if predicted_probability == 0.6 else 0.04

    monkeypatch.setattr(
        calibration_dashboard_module,
        "calculate_brier_score",
        maybe_score,
    )
    outcomes = [
        SimpleNamespace(
            prediction_date=datetime(2026, 2, 3, 12, tzinfo=UTC),
            predicted_probability=0.6,
            outcome=OutcomeType.OCCURRED.value,
            brier_score=None,
        ),
        SimpleNamespace(
            prediction_date=datetime(2026, 2, 4, 12, tzinfo=UTC),
            predicted_probability=0.2,
            outcome=None,
            brier_score=0.04,
        ),
    ]

    assert (
        service._build_brier_timeseries(
            outcomes,
            period_end=datetime(2026, 2, 28, tzinfo=UTC),
        )
        == []
    )


@pytest.mark.asyncio
async def test_load_trend_movements_assembles_summaries_for_active_trends() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    trend = SimpleNamespace(
        id=uuid4(),
        name="Trend A",
        is_active=True,
        current_log_odds=0.0,
        definition={
            "id": "trend-a",
            "horizon_variant": {
                "theme_key": "shared-theme",
                "label": "7d",
                "window_days": 7,
                "sort_order": 1,
            },
        },
    )
    scalars_result = MagicMock()
    scalars_result.all.return_value = [trend]
    session.scalars = AsyncMock(return_value=scalars_result)
    service._calculate_weekly_change = AsyncMock(return_value=0.15)
    service._load_top_movers = AsyncMock(return_value=["reason"])
    service._build_movement_chart = AsyncMock(return_value="._-")

    movements = await service._load_trend_movements(
        trend_id=trend.id,
        period_end=datetime(2026, 2, 28, tzinfo=UTC),
    )

    assert len(movements) == 1
    assert movements[0].trend_name == "Trend A"
    assert movements[0].horizon_variant == {
        "theme_key": "shared-theme",
        "label": "7d",
        "window_days": 7,
        "sort_order": 1,
    }
    assert movements[0].weekly_change == 0.15
    assert movements[0].top_movers_7d == ["reason"]
    assert movements[0].movement_chart == "._-"


@pytest.mark.asyncio
async def test_load_trend_movements_supports_unfiltered_queries() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    session.scalars = AsyncMock(return_value=scalars_result)

    assert (
        await service._load_trend_movements(
            trend_id=None,
            period_end=datetime(2026, 2, 28, tzinfo=UTC),
        )
        == []
    )


@pytest.mark.asyncio
async def test_calculate_weekly_change_returns_delta_or_zero() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    session.scalar = AsyncMock(side_effect=[None, -0.4054651081])
    trend_id = uuid4()
    as_of = datetime(2026, 2, 28, tzinfo=UTC)

    assert (
        await service._calculate_weekly_change(
            trend_id=trend_id,
            current_probability=0.6,
            as_of=as_of,
        )
        == 0.0
    )
    assert await service._calculate_weekly_change(
        trend_id=trend_id,
        current_probability=0.6,
        as_of=as_of,
    ) == pytest.approx(0.2, rel=0.01)


@pytest.mark.asyncio
async def test_load_top_movers_prefers_reasoning_and_falls_back_to_signal_type() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    rows_with_reasoning = [
        SimpleNamespace(reasoning=" First reason ", signal_type="signal-a"),
        SimpleNamespace(reasoning="", signal_type="signal-b"),
    ]
    rows_without_reasoning = [
        SimpleNamespace(reasoning=None, signal_type="signal-c"),
        SimpleNamespace(reasoning="", signal_type="signal-d"),
    ]
    first_scalars = MagicMock()
    first_scalars.all.return_value = rows_with_reasoning
    second_scalars = MagicMock()
    second_scalars.all.return_value = rows_without_reasoning
    session.scalars = AsyncMock(side_effect=[first_scalars, second_scalars])

    preferred = await service._load_top_movers(
        trend_id=uuid4(),
        as_of=datetime(2026, 2, 28, tzinfo=UTC),
    )
    fallback = await service._load_top_movers(
        trend_id=uuid4(),
        as_of=datetime(2026, 2, 28, tzinfo=UTC),
    )

    assert preferred == ["First reason"]
    assert fallback == ["signal-c", "signal-d"]


@pytest.mark.asyncio
async def test_build_movement_chart_uses_snapshots_and_appends_current_probability() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    scalars_result = MagicMock()
    scalars_result.all.return_value = [-0.8472978604, 0.0]
    session.scalars = AsyncMock(return_value=scalars_result)

    chart = await service._build_movement_chart(
        trend_id=uuid4(),
        current_probability=0.8,
        as_of=datetime(2026, 2, 28, tzinfo=UTC),
        max_points=3,
    )

    assert len(chart) == 3


@pytest.mark.asyncio
async def test_build_movement_chart_handles_empty_snapshot_history() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    session.scalars = AsyncMock(return_value=scalars_result)

    chart = await service._build_movement_chart(
        trend_id=uuid4(),
        current_probability=0.25,
        as_of=datetime(2026, 2, 28, tzinfo=UTC),
    )

    assert chart == "-"


@pytest.mark.asyncio
async def test_build_movement_chart_avoids_duplicate_terminal_probability() -> None:
    session = AsyncMock()
    service = CalibrationDashboardService(session=session, drift_alert_notifier=AsyncMock())
    scalars_result = MagicMock()
    scalars_result.all.return_value = [0.0]
    session.scalars = AsyncMock(return_value=scalars_result)

    chart = await service._build_movement_chart(
        trend_id=uuid4(),
        current_probability=0.5,
        as_of=datetime(2026, 2, 28, tzinfo=UTC),
    )

    assert chart == "-"
