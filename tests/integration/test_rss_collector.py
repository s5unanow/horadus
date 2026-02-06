from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from src.ingestion.rss_collector import FeedConfig, RSSCollector
from src.storage.database import async_session_maker
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_rss_collector_persists_and_deduplicates_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_url = f"https://integration.local/{uuid4()}/rss.xml"
    article_url = f"https://integration.local/{uuid4()}/article/1"
    source_name = f"Integration Feed {uuid4()}"

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{source_name}</title>
    <item>
      <title>Integration Article</title>
      <link>{article_url}</link>
      <description>Fallback summary text</description>
      <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    article_html = """
<html>
  <body>
    <article>
      <h1>Integration Article</h1>
      <p>This is article body extracted by trafilatura wrapper.</p>
    </article>
  </body>
</html>
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == feed_url:
            return httpx.Response(200, text=feed_xml, request=request)
        if url == article_url:
            return httpx.Response(200, text=article_html, request=request)
        return httpx.Response(404, text="Not found", request=request)

    monkeypatch.setattr(
        "src.ingestion.content_extractor.ContentExtractor.extract_text",
        staticmethod(lambda _html: f"Extracted full text {article_url}"),
    )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client,
        async_session_maker() as session,
    ):
        collector = RSSCollector(
            session=session,
            http_client=http_client,
            requests_per_second=1000.0,
        )
        feed = FeedConfig(
            name=source_name,
            url=feed_url,
            credibility=0.9,
            source_tier="wire",
            reporting_type="firsthand",
            max_items_per_fetch=10,
            enabled=True,
        )

        first = await collector.collect_feed(feed)
        await session.commit()

        second = await collector.collect_feed(feed)
        await session.commit()

        source = await session.scalar(
            select(Source).where(
                Source.type == SourceType.RSS,
                Source.url == feed_url,
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

        assert first.items_fetched == 1
        assert first.items_stored == 1
        assert first.items_skipped == 0
        assert first.errors == []

        assert second.items_fetched == 1
        assert second.items_stored == 0
        assert second.items_skipped == 1
        assert second.errors == []

        assert len(raw_items) == 1
        assert raw_items[0].external_id == article_url
        assert raw_items[0].url == article_url
        assert raw_items[0].raw_content == f"Extracted full text {article_url}"
        assert raw_items[0].processing_status == ProcessingStatus.PENDING
        assert source.error_count == 0
        assert source.last_error is None
