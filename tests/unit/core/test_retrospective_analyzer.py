from __future__ import annotations

import pytest

from src.core.retrospective_analyzer import RetrospectiveAnalyzer

pytestmark = pytest.mark.unit


def test_fallback_narrative_reports_sparse_coverage() -> None:
    narrative = RetrospectiveAnalyzer._fallback_narrative(
        trend_name="EU-Russia Escalation",
        pivotal_events=[{"event_id": "e1"}],
        predictive_signals=[{"signal_type": "military_movement"}],
        accuracy_assessment={
            "mean_brier_score": 0.22,
            "resolved_rate": 0.25,
        },
    )

    assert "military_movement" in narrative
    assert "25%" in narrative
    assert "Confidence is low" in narrative


def test_fallback_narrative_reports_moderate_coverage() -> None:
    narrative = RetrospectiveAnalyzer._fallback_narrative(
        trend_name="EU-Russia Escalation",
        pivotal_events=[{"event_id": "e1"}, {"event_id": "e2"}],
        predictive_signals=[],
        accuracy_assessment={
            "mean_brier_score": None,
            "resolved_rate": 0.8,
        },
    )

    assert "'none'" in narrative
    assert "80%" in narrative
    assert "Confidence is moderate" in narrative
