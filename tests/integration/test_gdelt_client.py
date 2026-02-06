from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from src.ingestion.gdelt_client import GDELTClient, GDELTQueryConfig
from src.storage.database import async_session_maker
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_gdelt_client_persists_and_deduplicates_items() -> None:
    source_name = f"GDELT Integration {uuid4()}"
    query = GDELTQueryConfig(
        name=source_name,
        query="ukraine",
        themes=["MILITARY"],
        actors=["NATO"],
        lookback_hours=72,
        max_records_per_page=2,
        max_pages=2,
        credibility=0.6,
        enabled=True,
    )

    now_utc = datetime.now(tz=UTC)
    first_seen = (now_utc - timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
    second_seen = (now_utc - timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")

    page_one = {
        "articles": [
            {
                "url": f"https://integration.local/{uuid4()}/article/1",
                "title": "Relevant military update",
                "themes": "MILITARY;SECURITY",
                "persons": "NATO",
                "language": "English",
                "sourcecountry": "UA",
                "seendate": first_seen,
                "domain": "integration.local",
            },
            {
                "url": f"https://integration.local/{uuid4()}/article/2",
                "title": "Irrelevant economy update",
                "themes": "ECONOMY",
                "persons": "NATO",
                "language": "English",
                "sourcecountry": "UA",
                "seendate": first_seen,
                "domain": "integration.local",
            },
        ]
    }
    duplicate_url = page_one["articles"][0]["url"]
    page_two = {
        "articles": [
            {
                "url": duplicate_url,
                "title": "Relevant military update",
                "themes": "MILITARY",
                "persons": "NATO",
                "language": "English",
                "sourcecountry": "UA",
                "seendate": second_seen,
                "domain": "integration.local",
            }
        ]
    }

    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        payload = page_one if calls["count"] % 2 == 1 else page_two
        return httpx.Response(200, json=payload, request=request)

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client,
        async_session_maker() as session,
    ):
        client = GDELTClient(
            session=session,
            http_client=http_client,
            api_url="https://gdelt.mock/api/v2/doc/doc",
            requests_per_second=1000.0,
        )

        first = await client.collect_query(query)
        await session.commit()

        second = await client.collect_query(query)
        await session.commit()

        source = await session.scalar(
            select(Source).where(
                Source.type == SourceType.GDELT,
                Source.name == source_name,
            )
        )
        assert source is not None

        raw_items = (
            await session.scalars(
                select(RawItem)
                .where(RawItem.source_id == source.id)
                .order_by(RawItem.fetched_at.asc())
            )
        ).all()

        assert first.pages_fetched == 2
        assert first.items_fetched == 3
        assert first.items_stored == 1
        assert first.items_skipped == 2
        assert first.errors == []

        assert second.pages_fetched == 2
        assert second.items_fetched == 3
        assert second.items_stored == 0
        assert second.items_skipped == 3
        assert second.errors == []

        assert len(raw_items) == 1
        assert raw_items[0].url == duplicate_url
        assert raw_items[0].processing_status == ProcessingStatus.PENDING
        assert source.error_count == 0
        assert source.last_error is None
