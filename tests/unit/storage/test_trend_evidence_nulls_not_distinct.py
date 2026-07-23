from __future__ import annotations

import pytest

from src.storage.models import TrendEvidence

pytestmark = pytest.mark.unit


def test_active_evidence_index_is_nulls_not_distinct_per_trend() -> None:
    evidence_index = next(
        index
        for index in TrendEvidence.__table__.indexes
        if index.name == "uq_trend_event_claim_signal_active"
    )

    assert tuple(column.name for column in evidence_index.columns) == (
        "trend_id",
        "state_version_id",
        "event_claim_id",
        "signal_type",
    )
    assert evidence_index.dialect_options["postgresql"]["nulls_not_distinct"] is True
