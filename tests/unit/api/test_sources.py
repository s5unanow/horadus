from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.sources import (
    SourceCreate,
    SourceUpdate,
    create_source,
    delete_source,
    get_source,
    list_sources,
    update_source,
)
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
