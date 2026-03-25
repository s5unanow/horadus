from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.api.routes.event_review_metadata import load_event_review_metadata
from src.storage.restatement_models import EventAdjudication

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_event_review_metadata_returns_empty_for_no_ids(mock_db_session) -> None:
    assert await load_event_review_metadata(session=mock_db_session, event_ids=[]) == {}
    mock_db_session.execute.assert_not_awaited()
    mock_db_session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_event_review_metadata_combines_gap_and_adjudication_state(
    mock_db_session,
) -> None:
    first_event_id = uuid4()
    second_event_id = uuid4()
    unrelated_event_id = uuid4()
    now = datetime.now(tz=UTC)
    older = now.replace(minute=max(0, now.minute - 1))
    mock_db_session.execute.return_value = SimpleNamespace(
        all=lambda: [(first_event_id, 2), (unrelated_event_id, 5)]
    )
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [
            EventAdjudication(
                id=uuid4(),
                event_id=first_event_id,
                outcome="confirm",
                review_status="resolved",
                override_intent="pin_event",
                resulting_effect={},
                created_at=now,
            ),
            EventAdjudication(
                id=uuid4(),
                event_id=first_event_id,
                outcome="restate",
                review_status="resolved",
                override_intent="apply_restatement",
                resulting_effect={},
                created_at=older,
            ),
            EventAdjudication(
                id=uuid4(),
                event_id=second_event_id,
                outcome="escalate_taxonomy_review",
                review_status="needs_taxonomy_review",
                override_intent="taxonomy_escalation",
                resulting_effect={},
                created_at=now,
            ),
            EventAdjudication(
                id=uuid4(),
                event_id=unrelated_event_id,
                outcome="confirm",
                review_status="resolved",
                override_intent="pin_event",
                resulting_effect={},
                created_at=now,
            ),
        ]
    )

    result = await load_event_review_metadata(
        session=mock_db_session,
        event_ids=[first_event_id, second_event_id],
    )

    assert result[first_event_id].open_taxonomy_gap_count == 2
    assert result[first_event_id].adjudication_count == 2
    assert result[first_event_id].latest_adjudication_outcome == "confirm"
    assert result[first_event_id].review_status == "resolved"
    assert result[second_event_id].review_status == "needs_taxonomy_review"
    assert result[second_event_id].adjudication_count == 1
