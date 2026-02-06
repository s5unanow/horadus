from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.ingestion.telegram_harvester import ChannelConfig, TelegramHarvester
from src.storage.models import ProcessingStatus

pytestmark = pytest.mark.unit


class FakeTelegramClient:
    def __init__(self, messages: list[object] | None = None) -> None:
        self._connected = False
        self._messages = messages or []

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
async def test_load_config_parses_settings_and_channels(
    tmp_path: Path,
    mock_db_session,
) -> None:
    config_path = tmp_path / "telegram.yaml"
    config_path.write_text(
        """
settings:
  default_check_interval_minutes: 20
  default_max_messages_per_fetch: 50
channels:
  - name: "Channel One"
    channel: "@channel_one"
    credibility: 0.8
    include_media: true
    enabled: true
  - name: ""
    channel: ""
""",
        encoding="utf-8",
    )

    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
        config_path=str(config_path),
    )

    await harvester.load_config(force=True)

    assert harvester.settings.default_check_interval_minutes == 20
    assert harvester.settings.default_max_messages_per_fetch == 50
    assert len(harvester.channels) == 1
    assert harvester.channels[0].name == "Channel One"
    assert harvester.channels[0].max_messages_per_fetch == 50


@pytest.mark.asyncio
async def test_collect_channel_counts_stored_and_skipped(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(messages=messages),
    )
    channel = ChannelConfig(
        name="Channel One",
        channel="@channel_one",
        credibility=0.8,
        max_messages_per_fetch=10,
    )
    source = SimpleNamespace(error_count=0)

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_process_message(_source, _channel: ChannelConfig, message: object) -> bool:
        return getattr(message, "id", 0) == 1

    async def fake_record_success(_source) -> None:
        return None

    async def fake_record_failure(_source, _error: str) -> None:
        return None

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_process_message", fake_process_message)
    monkeypatch.setattr(harvester, "_record_source_success", fake_record_success)
    monkeypatch.setattr(harvester, "_record_source_failure", fake_record_failure)

    result = await harvester.collect_channel(channel)

    assert result.channel_name == "Channel One"
    assert result.messages_fetched == 2
    assert result.messages_stored == 1
    assert result.messages_skipped == 1
    assert result.errors == []


def test_extract_message_text_from_media_fallback() -> None:
    message = SimpleNamespace(
        message=None,
        raw_text=None,
        media=SimpleNamespace(
            document=SimpleNamespace(attributes=[SimpleNamespace(file_name="map.png")]),
            photo=object(),
        ),
    )

    extracted = TelegramHarvester._extract_message_text(message, include_media=True)

    assert extracted is not None
    assert "map.png" in extracted


def test_message_url_from_username_channel() -> None:
    channel = ChannelConfig(name="C", channel="@intel_feed", credibility=0.7)
    url = TelegramHarvester._message_url(channel, message_id=123)
    assert url == "https://t.me/intel_feed/123"


@pytest.mark.asyncio
async def test_is_duplicate_checks_recent_window(mock_db_session) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    mock_db_session.scalar.return_value = uuid4()

    duplicate = await harvester._is_duplicate(
        external_id="@intel_feed:1",
        url="https://t.me/intel_feed/1",
        content_hash="deadbeef",
    )

    assert duplicate is True
    assert mock_db_session.scalar.await_count == 1


@pytest.mark.asyncio
async def test_store_item_sets_pending_status(mock_db_session) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    source = SimpleNamespace(id=uuid4())

    item = await harvester._store_item(
        source=source,
        external_id="@intel_feed:5",
        url="https://t.me/intel_feed/5",
        title="Headline",
        author="1000",
        published_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
        raw_content="Message body",
        content_hash="abc123",
        language="en",
    )

    assert item is not None
    assert item.processing_status == ProcessingStatus.PENDING
    assert item.external_id == "@intel_feed:5"
    assert mock_db_session.add.call_count == 1
