from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.api.routes.feedback_event_helpers import (
    build_review_queue_item,
    event_feedback_corrected_value,
    event_feedback_original_value,
)
from src.storage.models import Event, TrendEvidence

pytestmark = pytest.mark.unit


def test_event_feedback_payload_helpers_allow_missing_event_state() -> None:
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )

    original = event_feedback_original_value([evidence])
    corrected = event_feedback_corrected_value(
        action="restate",
        event_id=evidence.event_id,
        at=datetime.now(tz=UTC),
        evidences=[evidence],
        total_compensation_delta=0.1,
    )

    assert "epistemic_state" not in original
    assert original["active_evidence_ids"] == [str(evidence.id)]
    assert "epistemic_state" not in corrected
    assert corrected["affected_evidence_count"] == 1


def test_build_review_queue_item_uses_resolved_fallback_corroboration_counts() -> None:
    now = datetime.now(tz=UTC)
    event = Event(
        id=uuid4(),
        canonical_summary="Fallback event",
        lifecycle_status="emerging",
        created_at=now,
        last_mention_at=now,
        source_count=3,
        unique_source_count=3,
        independent_evidence_count=0,
        corroboration_mode="fallback",
    )
    evidence_row = (
        uuid4(),
        uuid4(),
        "Trend",
        "signal",
        0.4,
        0.8,
        0.0,
    )

    item = build_review_queue_item(
        event=event,
        event_evidence=[evidence_row],
        feedback_actions=[],
    )

    assert item.independent_evidence_count == 3
