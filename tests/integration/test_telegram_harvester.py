from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.ingestion.telegram_harvester import ChannelConfig, TelegramHarvester
from src.storage.database import async_session_maker
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

pytestmark = pytest.mark.integration


class FakeTelegramClient:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_entity(self, channel: str) -> str:
        return channel

    async def get_messages(self, _entity: str, limit: int) -> list[object]:
        return self._messages[:limit]

    async def iter_messages(
        self,
        _channel: str,
        offset_date: datetime,
        reverse: bool,
        limit: int,
    ):
        del offset_date, reverse
        for message in self._messages[:limit]:
            yield message


@pytest.mark.asyncio
async def test_telegram_harvester_persists_and_deduplicates_messages() -> None:
    now_utc = datetime.now(tz=UTC)
    channel_name = f"Telegram Integration {uuid4()}"
    channel_ref = f"@integration_{uuid4().hex[:10]}"
    text_suffix = uuid4().hex
    media_suffix = uuid4().hex[:8]
    channel = ChannelConfig(
        name=channel_name,
        channel=channel_ref,
        credibility=0.7,
        include_media=True,
        max_messages_per_fetch=20,
        enabled=True,
        language="en",
    )

    messages = [
        SimpleNamespace(
            id=1001,
            message=f"Primary message text {text_suffix}",
            raw_text=f"Primary message text {text_suffix}",
            media=None,
            date=now_utc - timedelta(minutes=15),
            sender_id=1,
            sender=None,
        ),
        SimpleNamespace(
            id=1002,
            message=None,
            raw_text=None,
            media=SimpleNamespace(
                document=SimpleNamespace(
                    attributes=[SimpleNamespace(file_name=f"map_{media_suffix}.png")]
                ),
                photo=object(),
            ),
            date=now_utc - timedelta(minutes=10),
            sender_id=2,
            sender=None,
        ),
    ]

    async with async_session_maker() as session:
        harvester = TelegramHarvester(
            session=session,
            client=FakeTelegramClient(messages=messages),
            min_request_interval_seconds=0.0,
        )

        first = await harvester.collect_channel(channel)
        await session.commit()

        second = await harvester.collect_channel(channel)
        await session.commit()

        backfill = await harvester.backfill_channel(channel, days=3, max_messages=50)
        await session.commit()

        source = await session.scalar(
            select(Source).where(
                Source.type == SourceType.TELEGRAM,
                Source.name == channel_name,
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

        assert first.messages_fetched == 2
        assert first.messages_stored == 2
        assert first.messages_skipped == 0
        assert first.errors == []

        assert second.messages_fetched == 2
        assert second.messages_stored == 0
        assert second.messages_skipped == 2
        assert second.errors == []

        assert backfill.messages_fetched == 2
        assert backfill.messages_stored == 0
        assert backfill.messages_skipped == 2
        assert backfill.errors == []

        assert len(raw_items) == 2
        assert raw_items[0].processing_status == ProcessingStatus.PENDING
        assert raw_items[1].processing_status == ProcessingStatus.PENDING
        assert source.error_count == 0
        assert source.last_error is None
