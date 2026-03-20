from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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


class FakeEntityLookupClient(FakeTelegramClient):
    def __init__(self, messages: list[object] | None = None) -> None:
        super().__init__(messages=messages)
        self.entities: list[str] = []

    async def get_entity(self, channel: str) -> str:
        self.entities.append(channel)
        return channel


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
async def test_load_config_returns_early_when_mtime_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_db_session,
) -> None:
    config_path = tmp_path / "telegram.yaml"
    config_path.write_text("settings: {}\nchannels: []\n", encoding="utf-8")
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
        config_path=str(config_path),
    )

    await harvester.load_config(force=True)
    monkeypatch.setattr(harvester, "_parse_settings", lambda _raw: pytest.fail("should not parse"))
    monkeypatch.setattr(
        harvester, "_parse_channels", lambda *_args: pytest.fail("should not parse")
    )

    await harvester.load_config(force=False)


@pytest.mark.asyncio
async def test_load_config_validates_file_and_top_level_shapes(
    tmp_path: Path,
    mock_db_session,
) -> None:
    missing_harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
        config_path=str(tmp_path / "missing.yaml"),
    )
    invalid_top_level = tmp_path / "invalid_top_level.yaml"
    invalid_top_level.write_text("- item\n", encoding="utf-8")
    invalid_settings = tmp_path / "invalid_settings.yaml"
    invalid_settings.write_text("settings: []\nchannels: []\n", encoding="utf-8")
    invalid_channels = tmp_path / "invalid_channels.yaml"
    invalid_channels.write_text("settings: {}\nchannels: {}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Telegram config file not found"):
        await missing_harvester.load_config()

    with pytest.raises(ValueError, match="expected mapping"):
        await TelegramHarvester(
            session=mock_db_session,
            client=FakeTelegramClient(),
            config_path=str(invalid_top_level),
        ).load_config()

    with pytest.raises(ValueError, match="Invalid Telegram settings format"):
        await TelegramHarvester(
            session=mock_db_session,
            client=FakeTelegramClient(),
            config_path=str(invalid_settings),
        ).load_config()

    with pytest.raises(ValueError, match="Invalid Telegram channel list format"):
        await TelegramHarvester(
            session=mock_db_session,
            client=FakeTelegramClient(),
            config_path=str(invalid_channels),
        ).load_config()


def test_create_client_requires_credentials(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_session,
) -> None:
    monkeypatch.setattr("src.ingestion.telegram_harvester.settings.TELEGRAM_API_ID", None)
    monkeypatch.setattr("src.ingestion.telegram_harvester.settings.TELEGRAM_API_HASH", None)

    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )

    with pytest.raises(ValueError, match="TELEGRAM_API_ID and TELEGRAM_API_HASH are required"):
        harvester._create_client()


def test_create_client_uses_configured_settings(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_session,
) -> None:
    captured: dict[str, object] = {}

    def fake_client(session_name: str, api_id: int, api_hash: str) -> object:
        captured.update(
            {
                "session_name": session_name,
                "api_id": api_id,
                "api_hash": api_hash,
            }
        )
        return SimpleNamespace(session_name=session_name)

    monkeypatch.setattr(
        "src.ingestion.telegram_harvester.settings.TELEGRAM_SESSION_NAME", "telegram-test"
    )
    monkeypatch.setattr("src.ingestion.telegram_harvester.settings.TELEGRAM_API_ID", 42)
    monkeypatch.setattr("src.ingestion.telegram_harvester.settings.TELEGRAM_API_HASH", "hash")
    monkeypatch.setattr("src.ingestion.telegram_harvester.TelegramClient", fake_client)

    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )

    client = harvester._create_client()

    assert client.session_name == "telegram-test"
    assert captured == {
        "session_name": "telegram-test",
        "api_id": 42,
        "api_hash": "hash",
    }


@pytest.mark.asyncio
async def test_collect_all_processes_only_enabled_channels_and_disconnects_owned_client(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_session,
) -> None:
    client = FakeTelegramClient()
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    harvester._owns_client = True
    harvester._channels = [
        ChannelConfig(name="One", channel="@one", credibility=0.7, enabled=True),
        ChannelConfig(name="Two", channel="@two", credibility=0.7, enabled=False),
        ChannelConfig(name="Three", channel="@three", credibility=0.7, enabled=True),
    ]
    collect_calls: list[str] = []
    sleep_calls: list[float] = []

    async def fake_load_config(force: bool = False) -> None:
        del force

    async def fake_collect_channel(channel: ChannelConfig) -> object:
        collect_calls.append(channel.name)
        return {"channel": channel.name}

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(harvester, "load_config", fake_load_config)
    monkeypatch.setattr(harvester, "collect_channel", fake_collect_channel)
    monkeypatch.setattr("src.ingestion.telegram_harvester.asyncio.sleep", fake_sleep)

    results = await harvester.collect_all()

    assert results == [{"channel": "One"}, {"channel": "Three"}]
    assert collect_calls == ["One", "Three"]
    assert sleep_calls == [1.0]
    assert client.is_connected() is False


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


@pytest.mark.asyncio
async def test_collect_channel_records_failures(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeTelegramClient()
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    channel = ChannelConfig(name="Channel One", channel="@channel_one", credibility=0.8)
    source = SimpleNamespace(error_count=1)
    failures: list[str] = []

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_record_failure(_source, error: str) -> None:
        failures.append(error)

    async def failing_get_entity(_channel: str) -> str:
        raise RuntimeError("connectivity")

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_record_source_failure", fake_record_failure)
    monkeypatch.setattr(client, "get_entity", failing_get_entity)

    result = await harvester.collect_channel(channel)

    assert result.messages_fetched == 0
    assert result.messages_stored == 0
    assert result.errors == ["Telegram harvest failed: connectivity"]
    assert failures == ["Telegram harvest failed: connectivity"]


@pytest.mark.asyncio
async def test_backfill_channel_counts_messages_and_applies_maximums(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    client = FakeTelegramClient(messages=messages)
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    channel = ChannelConfig(name="Channel One", channel="@channel_one", credibility=0.8)
    source = SimpleNamespace(error_count=0)

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_process_message(_source, _channel: ChannelConfig, message: object) -> bool:
        return message.id != 2

    async def fake_record_success(_source) -> None:
        return None

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_process_message", fake_process_message)
    monkeypatch.setattr(harvester, "_record_source_success", fake_record_success)

    result = await harvester.backfill_channel(channel, days=0, max_messages=2)

    assert result.messages_fetched == 2
    assert result.messages_stored == 1
    assert result.messages_skipped == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_backfill_channel_records_failures(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeTelegramClient()
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    channel = ChannelConfig(name="Channel One", channel="@channel_one", credibility=0.8)
    source = SimpleNamespace(error_count=0)
    recorded: list[str] = []

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_record_failure(_source, error: str) -> None:
        recorded.append(error)

    async def failing_iter_messages(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_record_source_failure", fake_record_failure)
    monkeypatch.setattr(client, "iter_messages", failing_iter_messages)

    result = await harvester.backfill_channel(channel)

    assert result.messages_stored == 0
    assert result.errors == ["Telegram backfill failed: boom"]
    assert recorded == ["Telegram backfill failed: boom"]


@pytest.mark.asyncio
async def test_stream_channel_processes_only_newer_message_ids(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeEntityLookupClient(messages=[SimpleNamespace(id=3), SimpleNamespace(id=2)])
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    channel = ChannelConfig(
        name="Channel One",
        channel="@channel_one",
        credibility=0.8,
        max_messages_per_fetch=3,
    )
    source = SimpleNamespace(error_count=0)
    sleep_calls: list[float] = []

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_process_message(_source, _channel: ChannelConfig, message: object) -> bool:
        return message.id == 3

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_process_message", fake_process_message)
    monkeypatch.setattr("src.ingestion.telegram_harvester.asyncio.sleep", fake_sleep)

    result = await harvester.stream_channel(channel, poll_interval_seconds=0.1, max_polls=1)

    assert result.messages_fetched == 2
    assert result.messages_stored == 1
    assert result.messages_skipped == 1
    assert client.entities == ["@channel_one"]
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_stream_channel_skips_messages_without_new_ids(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeEntityLookupClient(messages=[SimpleNamespace(id=3), SimpleNamespace(id="bad")])
    harvester = TelegramHarvester(session=mock_db_session, client=client)
    channel = ChannelConfig(
        name="Channel One",
        channel="@channel_one",
        credibility=0.8,
        max_messages_per_fetch=2,
    )
    source = SimpleNamespace(error_count=0)

    async def fake_get_or_create_source(_channel: ChannelConfig) -> SimpleNamespace:
        return source

    async def fake_process_message(_source, _channel: ChannelConfig, message: object) -> bool:
        return message.id == 3

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(harvester, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(harvester, "_process_message", fake_process_message)
    monkeypatch.setattr("src.ingestion.telegram_harvester.asyncio.sleep", fake_sleep)

    result = await harvester.stream_channel(channel, poll_interval_seconds=0.1, max_polls=1)

    assert result.messages_fetched == 1
    assert result.messages_stored == 1
    assert result.messages_skipped == 0


@pytest.mark.asyncio
async def test_process_message_skips_invalid_duplicate_and_empty_content_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harvester = TelegramHarvester(session=mock_db_session, client=FakeTelegramClient())
    source = SimpleNamespace(id=uuid4())
    channel = ChannelConfig(name="Channel One", channel="@channel_one", credibility=0.8)

    assert await harvester._process_message(source, channel, SimpleNamespace(id="bad")) is False

    message_without_content = SimpleNamespace(id=1, message=None, raw_text=None, media=None)
    assert await harvester._process_message(source, channel, message_without_content) is False

    async def fake_is_duplicate(**_kwargs) -> bool:
        return True

    monkeypatch.setattr(harvester, "_is_duplicate", fake_is_duplicate)
    assert (
        await harvester._process_message(source, channel, SimpleNamespace(id=2, message="dup"))
        is False
    )


@pytest.mark.asyncio
async def test_process_message_stores_valid_items(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harvester = TelegramHarvester(session=mock_db_session, client=FakeTelegramClient())
    source = SimpleNamespace(id=uuid4())
    channel = ChannelConfig(
        name="Channel One",
        channel="@channel_one",
        credibility=0.8,
        language="en",
    )
    stored_payload: dict[str, object] = {}

    async def fake_is_duplicate(**_kwargs) -> bool:
        return False

    async def fake_store_item(**kwargs):
        stored_payload.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(harvester, "_is_duplicate", fake_is_duplicate)
    monkeypatch.setattr(harvester, "_store_item", fake_store_item)

    was_stored = await harvester._process_message(
        source,
        channel,
        SimpleNamespace(
            id=9,
            message="Headline\nMore body",
            sender=SimpleNamespace(username="reporter"),
            date=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
        ),
    )

    assert was_stored is True
    assert stored_payload["title"] == "Headline"
    assert stored_payload["author"] == "reporter"
    assert stored_payload["language"] == "en"


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


def test_extract_message_text_handles_textless_media_and_media_disabled() -> None:
    media_only_message = SimpleNamespace(
        message=None,
        raw_text=None,
        media=type("", (), {})(),
    )
    assert TelegramHarvester._extract_message_text(media_only_message, include_media=False) is None
    assert TelegramHarvester._extract_message_text(media_only_message, include_media=True) is None


def test_message_url_from_username_channel() -> None:
    channel = ChannelConfig(name="C", channel="@intel_feed", credibility=0.7)
    url = TelegramHarvester._message_url(channel, message_id=123)
    assert url == "https://t.me/intel_feed/123"


def test_message_and_channel_url_variants() -> None:
    https_channel = ChannelConfig(name="C", channel="https://t.me/intel_feed", credibility=0.7)
    bare_channel = ChannelConfig(name="C", channel="t.me/intel_feed", credibility=0.7)
    unknown_channel = ChannelConfig(name="C", channel="intel_feed", credibility=0.7)

    assert TelegramHarvester._message_url(https_channel, 1) == "https://t.me/intel_feed/1"
    assert TelegramHarvester._message_url(bare_channel, 2) == "https://t.me/intel_feed/2"
    assert TelegramHarvester._message_url(unknown_channel, 3) is None
    assert TelegramHarvester._channel_url("@intel_feed") == "https://t.me/intel_feed"
    assert TelegramHarvester._channel_url("https://t.me/intel_feed/") == "https://t.me/intel_feed"
    assert TelegramHarvester._channel_url("t.me/intel_feed/") == "https://t.me/intel_feed"
    assert TelegramHarvester._channel_url("intel_feed") is None


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


@pytest.mark.asyncio
async def test_store_item_returns_none_on_insert_race(mock_db_session) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    source = SimpleNamespace(id=uuid4())

    @asynccontextmanager
    async def fake_begin_nested():
        yield

    mock_db_session.begin_nested = fake_begin_nested
    mock_db_session.flush.side_effect = IntegrityError("insert", {}, Exception("boom"))

    item = await harvester._store_item(
        source=source,
        external_id="@intel_feed:6",
        url=None,
        title=None,
        author=None,
        published_at=None,
        raw_content="Message body",
        content_hash="abc123",
        language=None,
    )

    assert item is None


@pytest.mark.asyncio
async def test_get_or_create_source_creates_and_updates_records(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    channel = ChannelConfig(
        name="Intel Feed",
        channel="@intel_feed",
        credibility=0.9,
        categories=["conflict"],
        check_interval_minutes=20,
        max_messages_per_fetch=50,
        include_media=False,
        language="en",
        source_tier="tier1",
        reporting_type="primary",
        enabled=False,
        extra={"region": "EMEA"},
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.telegram_harvester.refresh_events_for_source", refresh_mock)
    mock_db_session.scalar.return_value = None

    created = await harvester._get_or_create_source(channel)

    assert created.name == "Intel Feed"
    assert created.url == "https://t.me/intel_feed"
    assert created.credibility_score == 0.9
    assert created.config["region"] == "EMEA"
    assert created.is_active is False
    refresh_mock.assert_not_awaited()

    existing = SimpleNamespace(
        id=uuid4(),
        name="Old Feed",
        url=None,
        credibility_score=0.1,
        source_tier="regional",
        reporting_type="secondary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    updated = await harvester._get_or_create_source(channel)

    assert updated is existing
    assert existing.url == "https://t.me/intel_feed"
    assert existing.credibility_score == 0.9
    assert existing.source_tier == "tier1"
    assert existing.reporting_type == "primary"
    assert existing.config["categories"] == ["conflict"]
    assert existing.is_active is False
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)


@pytest.mark.asyncio
async def test_get_or_create_source_skips_provenance_refresh_when_metadata_is_unchanged(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    channel = ChannelConfig(
        name="Intel Feed",
        channel="@intel_feed",
        credibility=0.9,
        categories=["conflict"],
        check_interval_minutes=20,
        max_messages_per_fetch=50,
        include_media=False,
        language="en",
        source_tier="tier1",
        reporting_type="primary",
        enabled=False,
        extra={"region": "EMEA"},
    )
    refresh_mock = AsyncMock(return_value=0)
    monkeypatch.setattr("src.ingestion.telegram_harvester.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Intel Feed",
        url="https://t.me/intel_feed",
        credibility_score=channel.credibility,
        source_tier="tier1",
        reporting_type="primary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    updated = await harvester._get_or_create_source(channel)

    assert updated is existing
    refresh_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_source_refreshes_provenance_when_credibility_changes(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harvester = TelegramHarvester(
        session=mock_db_session,
        client=FakeTelegramClient(),
    )
    channel = ChannelConfig(
        name="Intel Feed",
        channel="@intel_feed",
        credibility=0.9,
        source_tier="tier1",
        reporting_type="primary",
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.telegram_harvester.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Intel Feed",
        url="https://t.me/intel_feed",
        credibility_score=0.1,
        source_tier="tier1",
        reporting_type="primary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    await harvester._get_or_create_source(channel)

    assert existing.credibility_score == pytest.approx(0.9)
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)


@pytest.mark.asyncio
async def test_record_source_success_and_failure_update_state(mock_db_session) -> None:
    harvester = TelegramHarvester(session=mock_db_session, client=FakeTelegramClient())
    source = SimpleNamespace(last_fetched_at=None, error_count=3, last_error="old")

    await harvester._record_source_success(source)

    assert source.last_fetched_at is not None
    assert source.error_count == 0
    assert source.last_error is None

    await harvester._record_source_failure(source, "x" * 1200)

    assert source.error_count == 1
    assert len(source.last_error) == 1000
    assert mock_db_session.flush.await_count == 2


@pytest.mark.asyncio
async def test_connection_helpers_respect_client_ownership(mock_db_session) -> None:
    client = FakeTelegramClient()
    harvester = TelegramHarvester(session=mock_db_session, client=client)

    await harvester._ensure_connected()
    await harvester._ensure_connected()
    assert client.is_connected() is True

    await harvester._disconnect_if_owned()
    assert client.is_connected() is True

    harvester._owns_client = True
    await harvester._disconnect_if_owned()
    assert client.is_connected() is False


def test_parse_channels_and_message_helpers_cover_normalization() -> None:
    channels = TelegramHarvester._parse_channels(
        {"default_check_interval_minutes": 30, "default_max_messages_per_fetch": 40},
        [
            {
                "name": " Intel ",
                "channel": " @intel_feed ",
                "credibility": "0.8",
                "categories": ["conflict", " ", 7],
                "include_media": 0,
                "language": " en ",
                "source_tier": "tier1",
                "reporting_type": "primary",
                "enabled": 0,
                "region": "EMEA",
            },
            {"name": None, "channel": "@skip"},
            "skip",
        ],
    )

    assert len(channels) == 1
    assert channels[0].name == "Intel"
    assert channels[0].channel == "@intel_feed"
    assert channels[0].categories == ["conflict", "7"]
    assert channels[0].check_interval_minutes == 30
    assert channels[0].max_messages_per_fetch == 40
    assert channels[0].include_media is False
    assert channels[0].language == "en"
    assert channels[0].enabled is False
    assert channels[0].extra == {"region": "EMEA"}

    assert TelegramHarvester._message_id(SimpleNamespace(id=5)) == 5
    assert TelegramHarvester._message_id(SimpleNamespace(id="5")) is None
    assert (
        TelegramHarvester._message_author(
            SimpleNamespace(sender=SimpleNamespace(username="user", first_name="Name"))
        )
        == "user"
    )
    assert (
        TelegramHarvester._message_author(
            SimpleNamespace(sender=SimpleNamespace(username=" ", first_name="Name"))
        )
        == "Name"
    )
    assert (
        TelegramHarvester._message_author(
            SimpleNamespace(
                sender=SimpleNamespace(username=" ", first_name=" "),
                sender_id=42,
            )
        )
        == "42"
    )
    assert TelegramHarvester._message_author(SimpleNamespace(sender_id=42)) == "42"
    assert TelegramHarvester._message_author(SimpleNamespace(sender_id="42")) is None

    message = SimpleNamespace(
        message=None,
        raw_text=None,
        media=SimpleNamespace(
            document=SimpleNamespace(
                attributes=[SimpleNamespace(file_name=" "), SimpleNamespace(file_name="clip.mp4")]
            )
        ),
    )
    assert "clip.mp4" in TelegramHarvester._extract_message_text(message, include_media=True)


def test_datetime_title_hash_and_safe_str_helpers() -> None:
    aware = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
    naive = aware.replace(tzinfo=None)

    assert TelegramHarvester._message_datetime(SimpleNamespace(date=naive)) == naive.replace(
        tzinfo=UTC
    )
    assert TelegramHarvester._message_datetime(SimpleNamespace(date=aware)) == aware
    assert TelegramHarvester._message_datetime(SimpleNamespace(date="bad")) is None
    assert TelegramHarvester._build_title("Headline\nSecond line") == "Headline"
    assert len(TelegramHarvester._compute_hash("abc")) == 64
    assert TelegramHarvester._safe_str(None) is None
    assert TelegramHarvester._safe_str("  ") is None
    assert TelegramHarvester._safe_str(" value ") == "value"
