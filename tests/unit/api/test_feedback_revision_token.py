from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.api.routes._feedback_write_mutations as feedback_mutations_module
import src.api.routes._privileged_write_contract as write_contract_module
from src.api.routes.feedback import EventFeedbackRequest, create_event_feedback
from src.api.routes.feedback_models import EventRestatementTarget
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_create_event_feedback_restate_updates_event_revision_token(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_updated_at = datetime(2026, 3, 22, 9, 0, tzinfo=UTC)
    event = Event(
        id=uuid4(),
        canonical_summary="Partial correction",
        last_updated_at=original_updated_at,
    )
    trend = Trend(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        baseline_log_odds=-2.0,
        current_log_odds=-1.0,
        indicators={},
        decay_half_life_days=30,
        is_active=True,
    )
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=event.id,
        event_claim_id=uuid4(),
        signal_type="military_movement",
        delta_log_odds=0.4,
    )

    async def _fake_apply(**_kwargs):
        trend.current_log_odds = -1.2
        trend.updated_at = datetime.now(tz=UTC)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(feedback_mutations_module, "apply_compensating_restatement", _fake_apply)
    mock_db_session.get.return_value = event
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [trend]),
    ]
    original_revision_token = write_contract_module.event_revision_token(event)

    result = await create_event_feedback(
        event_id=event.id,
        payload=EventFeedbackRequest(
            action="restate",
            notes="Analyst reduced confidence impact.",
            restatement_targets=[
                EventRestatementTarget(
                    evidence_id=evidence.id,
                    compensation_delta_log_odds=-0.2,
                    notes="Only half the original impact remains.",
                )
            ],
        ),
        session=mock_db_session,
    )

    assert event.last_updated_at is not None
    assert event.last_updated_at > original_updated_at
    assert result.target_revision_token != original_revision_token
