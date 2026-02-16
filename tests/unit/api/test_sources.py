from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

import src.api.routes.sources as sources_route
from src.api.routes.sources import (
    SourceCreate,
    SourceUpdate,
    create_source,
    delete_source,
    get_source,
    get_source_freshness,
    list_sources,
    update_source,
)
from src.core.source_freshness import SourceFreshnessReport, SourceFreshnessRow
from src.storage.models import Source, SourceType

pytestmark = pytest.mark.unit


def _build_source(
    *,
    source_id: UUID | None = None,
    name: str = "Test Source",
    source_type: SourceType = SourceType.RSS,
    is_active: bool = True,
) -> Source:
    return Source(
        id=source_id or uuid4(),
        type=source_type,
        name=name,
        url="https://example.com/feed.xml",
        credibility_score=0.8,
        source_tier="regional",
        reporting_type="secondary",
        config={"interval": 30},
        is_active=is_active,
        last_fetched_at=datetime.now(tz=UTC),
        error_count=0,
    )


@pytest.mark.asyncio
async def test_list_sources_returns_response_models(mock_db_session) -> None:
    first_source = _build_source(name="First")
    second_source = _build_source(name="Second")
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [first_source, second_source]
    )

    result = await list_sources(session=mock_db_session)

    assert [source.name for source in result] == ["First", "Second"]
    assert result[0].type == SourceType.RSS
    assert mock_db_session.scalars.await_count == 1


@pytest.mark.asyncio
async def test_create_source_persists_new_record(mock_db_session) -> None:
    created_id = uuid4()

    async def flush_side_effect() -> None:
        source_record = mock_db_session.add.call_args.args[0]
        source_record.id = created_id

    mock_db_session.flush.side_effect = flush_side_effect

    result = await create_source(
        source=SourceCreate(
            type=SourceType.RSS,
            name="Created",
            url="https://example.com/rss",
            credibility_score=0.9,
            config={"a": 1},
        ),
        session=mock_db_session,
    )

    added_source = mock_db_session.add.call_args.args[0]
    assert result.id == created_id
    assert added_source.source_tier == "regional"
    assert added_source.reporting_type == "secondary"
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_get_source_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc_info:
        await get_source(source_id=uuid4(), session=mock_db_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_source_returns_source(mock_db_session) -> None:
    source = _build_source(name="Known Source")
    mock_db_session.get.return_value = source

    result = await get_source(source_id=source.id, session=mock_db_session)

    assert result.id == source.id
    assert result.name == "Known Source"


@pytest.mark.asyncio
async def test_update_source_updates_fields(mock_db_session) -> None:
    source = _build_source(name="Old Name")
    mock_db_session.get.return_value = source

    result = await update_source(
        source_id=source.id,
        source=SourceUpdate(name="New Name", credibility_score=0.95, is_active=False),
        session=mock_db_session,
    )

    assert source.name == "New Name"
    assert float(source.credibility_score) == pytest.approx(0.95)
    assert source.is_active is False
    assert result.name == "New Name"
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_delete_source_deactivates_source(mock_db_session) -> None:
    source = _build_source(is_active=True)
    mock_db_session.get.return_value = source

    await delete_source(source_id=source.id, session=mock_db_session)

    assert source.is_active is False
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_delete_source_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc_info:
        await delete_source(source_id=uuid4(), session=mock_db_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_source_freshness_returns_report(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_at = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    report = SourceFreshnessReport(
        checked_at=checked_at,
        stale_multiplier=2.0,
        rows=(
            SourceFreshnessRow(
                source_id=uuid4(),
                source_name="Stale RSS",
                collector="rss",
                last_fetched_at=checked_at,
                age_seconds=7201,
                stale_after_seconds=7200,
                is_stale=True,
            ),
        ),
    )
    monkeypatch.setattr(sources_route.settings, "ENABLE_RSS_INGESTION", True)
    monkeypatch.setattr(sources_route.settings, "ENABLE_GDELT_INGESTION", True)
    monkeypatch.setattr(sources_route.settings, "SOURCE_FRESHNESS_MAX_CATCHUP_DISPATCHES", 2)
    monkeypatch.setattr(
        sources_route,
        "build_source_freshness_report",
        AsyncMock(return_value=report),
    )

    result = await get_source_freshness(session=mock_db_session)

    assert result.checked_at == checked_at
    assert result.stale_multiplier == pytest.approx(2.0)
    assert result.stale_count == 1
    assert result.stale_collectors == ["rss"]
    assert result.catchup_dispatch_budget == 2
    assert result.catchup_candidates == ["rss"]
    assert len(result.rows) == 1
    assert result.rows[0].source_name == "Stale RSS"
    assert result.rows[0].is_stale is True
