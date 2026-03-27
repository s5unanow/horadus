from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core import source_reliability_diagnostics as reliability_module
from src.core.source_reliability_diagnostics import (
    OutcomeReliabilityMetrics,
    advisory_note,
    build_reliability_summary_from_pairs,
    build_source_reliability_diagnostics,
)
from src.storage.models import OutcomeType

pytestmark = pytest.mark.unit


def test_build_reliability_summary_marks_stable_recent_window() -> None:
    outcome_ids = [uuid4() for _ in range(4)]
    summary = build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=2,
        pairs=[("source-a", "Reuters", outcome_id) for outcome_id in outcome_ids],
        outcome_metrics={
            outcome_ids[0]: OutcomeReliabilityMetrics(
                0.6, 0.5, 0.01, datetime(2025, 11, 1, tzinfo=UTC)
            ),
            outcome_ids[1]: OutcomeReliabilityMetrics(
                0.6, 0.5, 0.01, datetime(2025, 11, 15, tzinfo=UTC)
            ),
            outcome_ids[2]: OutcomeReliabilityMetrics(
                0.6, 0.5, 0.01, datetime(2026, 1, 10, tzinfo=UTC)
            ),
            outcome_ids[3]: OutcomeReliabilityMetrics(
                0.6, 0.5, 0.01, datetime(2026, 1, 20, tzinfo=UTC)
            ),
        },
        reference_credibility_by_key={"source-a": 0.82},
    )

    row = summary.rows[0]
    assert row.drift_state == "stable"
    assert row.advisory_delta == pytest.approx(0.0)
    assert row.advisory_effective_credibility == pytest.approx(0.82)


def test_build_reliability_summary_surfaces_bounded_degrading_adjustment() -> None:
    outcome_ids = [uuid4() for _ in range(5)]
    summary = build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=3,
        pairs=[("source-a", "Reuters", outcome_id) for outcome_id in outcome_ids],
        outcome_metrics={
            outcome_ids[0]: OutcomeReliabilityMetrics(
                0.8, 1.0, 0.04, datetime(2025, 10, 1, tzinfo=UTC)
            ),
            outcome_ids[1]: OutcomeReliabilityMetrics(
                0.8, 1.0, 0.04, datetime(2025, 10, 15, tzinfo=UTC)
            ),
            outcome_ids[2]: OutcomeReliabilityMetrics(
                0.8, 1.0, 0.04, datetime(2025, 11, 1, tzinfo=UTC)
            ),
            outcome_ids[3]: OutcomeReliabilityMetrics(
                0.8, 0.0, 0.64, datetime(2026, 1, 10, tzinfo=UTC)
            ),
            outcome_ids[4]: OutcomeReliabilityMetrics(
                0.8, 0.0, 0.64, datetime(2026, 1, 20, tzinfo=UTC)
            ),
        },
        reference_credibility_by_key={"source-a": 0.9},
    )

    row = summary.rows[0]
    assert row.drift_state == "degrading"
    assert row.advisory_delta == pytest.approx(-0.12)
    assert row.configured_effective_credibility == pytest.approx(0.9)
    assert row.advisory_effective_credibility == pytest.approx(0.78)


def test_build_reliability_summary_suppresses_sparse_recent_window() -> None:
    outcome_ids = [uuid4() for _ in range(4)]
    summary = build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=3,
        pairs=[("source-a", "Reuters", outcome_id) for outcome_id in outcome_ids],
        outcome_metrics={
            outcome_ids[0]: OutcomeReliabilityMetrics(
                0.7, 1.0, 0.09, datetime(2025, 10, 1, tzinfo=UTC)
            ),
            outcome_ids[1]: OutcomeReliabilityMetrics(
                0.7, 1.0, 0.09, datetime(2025, 10, 15, tzinfo=UTC)
            ),
            outcome_ids[2]: OutcomeReliabilityMetrics(
                0.7, 1.0, 0.09, datetime(2025, 11, 1, tzinfo=UTC)
            ),
            outcome_ids[3]: OutcomeReliabilityMetrics(
                0.7, 0.0, 0.49, datetime(2026, 1, 20, tzinfo=UTC)
            ),
        },
        reference_credibility_by_key={"source-a": 0.88},
    )

    row = summary.rows[0]
    assert row.recent_sample_size == 1
    assert row.drift_state == "insufficient_recent_data"
    assert row.advisory_delta is None
    assert "suppressed" in row.advisory_note


def test_advisory_note_handles_missing_delta_for_nonstable_state() -> None:
    note = advisory_note(
        sample_size=4,
        min_sample_size=2,
        drift_state="improving",
        advisory_delta=None,
    )

    assert "Requires analyst review" in note


def test_helper_branches_cover_improving_and_normalizer_edges() -> None:
    assert reliability_module._time_varying_signal(
        min_sample_size=3,
        recent_min_sample_size=2,
        recent_sample_size=2,
        baseline_sample_size=3,
        recent_observed_rate=None,
        baseline_observed_rate=0.4,
    ) == ("insufficient_recent_data", None)
    assert reliability_module._time_varying_signal(
        min_sample_size=3,
        recent_min_sample_size=2,
        recent_sample_size=2,
        baseline_sample_size=3,
        recent_observed_rate=1.0,
        baseline_observed_rate=0.0,
    ) == ("improving", 0.12)
    assert reliability_module._normalize_geography("   ") is None
    assert reliability_module._normalize_topics("not-a-list") == []
    assert reliability_module._normalize_topics(["conflict", " ", "europe"]) == [
        "conflict",
        "europe",
    ]


@pytest.mark.asyncio
async def test_build_source_reliability_diagnostics_populates_topic_and_geography() -> None:
    session = AsyncMock()
    outcome_ids = [uuid4() for _ in range(5)]
    source_id = uuid4()
    scored_outcomes = [
        SimpleNamespace(
            id=outcome_ids[0],
            predicted_probability=0.8,
            outcome=OutcomeType.OCCURRED.value,
            brier_score=None,
            prediction_date=datetime(2025, 10, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=outcome_ids[1],
            predicted_probability=0.8,
            outcome=OutcomeType.OCCURRED.value,
            brier_score=None,
            prediction_date=datetime(2025, 10, 15, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=outcome_ids[2],
            predicted_probability=0.8,
            outcome=OutcomeType.OCCURRED.value,
            brier_score=None,
            prediction_date=datetime(2025, 11, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=outcome_ids[3],
            predicted_probability=0.8,
            outcome=OutcomeType.DID_NOT_OCCUR.value,
            brier_score=None,
            prediction_date=datetime(2026, 1, 10, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=outcome_ids[4],
            predicted_probability=0.8,
            outcome=OutcomeType.DID_NOT_OCCUR.value,
            brier_score=None,
            prediction_date=datetime(2026, 1, 20, tzinfo=UTC),
        ),
    ]
    execute_result = MagicMock()
    execute_result.all.return_value = [
        (outcome_id, source_id, "Reuters", 0.95, "wire", "firsthand", "Kyiv, Ukraine", ["conflict"])
        for outcome_id in outcome_ids
    ]
    session.execute = AsyncMock(return_value=execute_result)

    bundle = await build_source_reliability_diagnostics(
        session=session,
        scored_outcomes=scored_outcomes,
    )

    assert bundle.source_reliability.rows[0].configured_effective_credibility == pytest.approx(
        0.9025
    )
    assert bundle.source_reliability.rows[0].drift_state == "no_baseline_window"
    assert bundle.geography_reliability.dimension == "geography"
    assert bundle.geography_reliability.rows[0].label == "Ukraine"
    assert bundle.topic_family_reliability.dimension == "topic_family"
    assert bundle.topic_family_reliability.rows[0].label == "conflict"
