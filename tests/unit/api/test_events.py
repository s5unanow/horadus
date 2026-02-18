from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.events import get_event, list_events
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _build_event(
    *,
    event_id: UUID | None = None,
    lifecycle_status: str = "confirmed",
    has_contradictions: bool = False,
    contradiction_notes: str | None = None,
) -> Event:
    now = datetime.now(tz=UTC)
    return Event(
        id=event_id or uuid4(),
        canonical_summary="Cross-border force movements reported",
        categories=["military"],
        source_count=4,
        unique_source_count=3,
        lifecycle_status=lifecycle_status,
        has_contradictions=has_contradictions,
        contradiction_notes=contradiction_notes,
        first_seen_at=now - timedelta(hours=6),
        last_mention_at=now,
        extracted_who=["Country A", "Country B"],
        extracted_what="Military units repositioned",
        extracted_where="Border region",
    )


@pytest.mark.asyncio
async def test_list_events_returns_filtered_payload(mock_db_session) -> None:
    event = _build_event(lifecycle_status="confirmed")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [event])

    result = await list_events(
        lifecycle="confirmed",
        contradicted=False,
        category="military",
        trend_id=uuid4(),
        days=7,
        limit=20,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].id == event.id
    assert result[0].lifecycle_status == "confirmed"
    assert result[0].unique_source_count == 3
    assert result[0].summary == event.canonical_summary
    query = mock_db_session.scalars.await_args.args[0]
    query_text = str(query)
    query_text_lower = query_text.lower()
    assert "events.lifecycle_status" in query_text
    assert "events.has_contradictions" in query_text
    assert "exists" in query_text_lower
    assert "trend_evidence.trend_id" in query_text
    assert "trend_evidence.is_invalidated is false" in query_text_lower
    assert "join trend_evidence" not in query_text_lower


@pytest.mark.asyncio
async def test_get_event_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await get_event(event_id=uuid4(), session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_event_returns_detail_with_sources_and_impacts(mock_db_session) -> None:
    event = _build_event(
        has_contradictions=True,
        contradiction_notes="Source narratives conflict on withdrawal timeline.",
    )
    mock_db_session.get.return_value = event
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                ("Reuters", "https://example.com/a1"),
                ("BBC", "https://example.com/a2"),
            ]
        ),
        SimpleNamespace(
            all=lambda: [
                (uuid4(), "military_movement", 0.12),
                (uuid4(), "diplomatic_talks", -0.05),
            ]
        ),
    ]

    result = await get_event(event_id=event.id, session=mock_db_session)

    assert result.id == event.id
    assert result.has_contradictions is True
    assert "conflict" in (result.contradiction_notes or "").lower()
    assert len(result.sources) == 2
    assert result.sources[0]["source_name"] == "Reuters"
    assert len(result.trend_impacts) == 2
    assert result.trend_impacts[0]["direction"] == "escalatory"
    assert result.trend_impacts[1]["direction"] == "de_escalatory"
