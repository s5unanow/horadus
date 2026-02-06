"""
Telegram channel harvesting with deduplication and persistence.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
import yaml
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from src.core.config import settings
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ChannelConfig:
    """Telegram channel configuration loaded from YAML."""

    name: str
    channel: str
    credibility: float
    categories: list[str] = field(default_factory=list)
    check_interval_minutes: int = 15
    max_messages_per_fetch: int = 100
    include_media: bool = True
    language: str | None = None
    source_tier: str = "regional"
    reporting_type: str = "secondary"
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HarvesterSettings:
    """Global Telegram harvester settings from YAML."""

    default_check_interval_minutes: int = 15
    default_max_messages_per_fetch: int = 100


@dataclass(slots=True)
class HarvestResult:
    """Outcome metrics for one channel harvest run."""

    channel_name: str
    messages_fetched: int = 0
    messages_stored: int = 0
    messages_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class TelegramHarvester:
    """
    Collect and normalize messages from configured Telegram channels.
    """

    def __init__(
        self,
        session: AsyncSession,
        client: TelegramClient | Any | None = None,
        config_path: str = "config/sources/telegram_channels.yaml",
        min_request_interval_seconds: float = 1.0,
    ) -> None:
        self.session = session
        self.config_path = Path(config_path)
        self.min_request_interval_seconds = max(0.0, min_request_interval_seconds)
        self.settings = HarvesterSettings()
        self._channels: list[ChannelConfig] = []
        self._config_mtime: float | None = None

        self.client = client or self._create_client()
        self._owns_client = client is None

        self.dedup_window_days = 7
        self.max_backfill_messages = 1000

    @property
    def channels(self) -> list[ChannelConfig]:
        """Returns the currently loaded channel configs."""
        return list(self._channels)

    def _create_client(self) -> TelegramClient:
        if settings.TELEGRAM_API_ID is None or settings.TELEGRAM_API_HASH is None:
            msg = "TELEGRAM_API_ID and TELEGRAM_API_HASH are required for TelegramHarvester"
            raise ValueError(msg)

        # Session name provides persistent auth/session state across restarts.
        return TelegramClient(
            settings.TELEGRAM_SESSION_NAME,
            settings.TELEGRAM_API_ID,
            settings.TELEGRAM_API_HASH,
        )

    async def load_config(self, force: bool = False) -> None:
        """Load or hot-reload Telegram channel config from YAML."""
        if not self.config_path.exists():
            msg = f"Telegram config file not found: {self.config_path}"
            raise FileNotFoundError(msg)

        mtime = self.config_path.stat().st_mtime
        if not force and self._config_mtime is not None and mtime == self._config_mtime:
            return

        raw_config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_config, dict):
            msg = "Invalid Telegram config format: expected mapping at top-level"
            raise ValueError(msg)

        settings_config = raw_config.get("settings", {})
        channels_config = raw_config.get("channels", [])
        if not isinstance(settings_config, dict):
            msg = "Invalid Telegram settings format"
            raise ValueError(msg)
        if not isinstance(channels_config, list):
            msg = "Invalid Telegram channel list format"
            raise ValueError(msg)

        self.settings = self._parse_settings(settings_config)
        self._channels = self._parse_channels(settings_config, channels_config)
        self._config_mtime = mtime

        logger.info(
            "Telegram configuration loaded",
            config_path=str(self.config_path),
            channels=len(self._channels),
        )

    async def collect_all(self) -> list[HarvestResult]:
        """Collect messages from all enabled channels."""
        await self.load_config()
        await self._ensure_connected()

        results: list[HarvestResult] = []
        enabled_channels = [channel for channel in self._channels if channel.enabled]
        for index, channel in enumerate(enabled_channels):
            results.append(await self.collect_channel(channel))
            if index + 1 < len(enabled_channels):
                await asyncio.sleep(self.min_request_interval_seconds)

        await self._disconnect_if_owned()
        return results

    async def collect_channel(
        self,
        channel: ChannelConfig,
        limit: int | None = None,
    ) -> HarvestResult:
        """Collect recent messages from one channel."""
        started = time.monotonic()
        result = HarvestResult(channel_name=channel.name)
        source = await self._get_or_create_source(channel)

        try:
            await self._ensure_connected()
            entity = await self.client.get_entity(channel.channel)
            max_items = limit or channel.max_messages_per_fetch
            messages = await self.client.get_messages(entity, limit=max_items)
            message_list = list(messages) if messages is not None else []
            result.messages_fetched = len(message_list)

            for message in message_list:
                was_stored = await self._process_message(source, channel, message)
                if was_stored:
                    result.messages_stored += 1
                else:
                    result.messages_skipped += 1
        except Exception as exc:
            error_message = f"Telegram harvest failed: {exc}"
            logger.warning(
                "Telegram channel harvest failed",
                channel_name=channel.name,
                channel_ref=channel.channel,
                error=str(exc),
            )
            result.errors.append(error_message)
            await self._record_source_failure(source, error_message)
        else:
            await self._record_source_success(source)

        result.duration_seconds = round(time.monotonic() - started, 3)
        return result

    async def backfill_channel(
        self,
        channel: ChannelConfig,
        days: int = 7,
        max_messages: int | None = None,
    ) -> HarvestResult:
        """
        Backfill historical messages from one channel.
        """
        started = time.monotonic()
        result = HarvestResult(channel_name=channel.name)
        source = await self._get_or_create_source(channel)
        since = datetime.now(tz=UTC) - timedelta(days=max(1, days))
        message_limit = max_messages or self.max_backfill_messages

        try:
            await self._ensure_connected()
            async for message in self.client.iter_messages(
                channel.channel,
                offset_date=since,
                reverse=True,
                limit=message_limit,
            ):
                result.messages_fetched += 1
                was_stored = await self._process_message(source, channel, message)
                if was_stored:
                    result.messages_stored += 1
                else:
                    result.messages_skipped += 1
        except Exception as exc:
            error_message = f"Telegram backfill failed: {exc}"
            logger.warning(
                "Telegram channel backfill failed",
                channel_name=channel.name,
                channel_ref=channel.channel,
                error=str(exc),
            )
            result.errors.append(error_message)
            await self._record_source_failure(source, error_message)
        else:
            await self._record_source_success(source)

        result.duration_seconds = round(time.monotonic() - started, 3)
        return result

    async def stream_channel(
        self,
        channel: ChannelConfig,
        poll_interval_seconds: float = 5.0,
        max_polls: int | None = None,
    ) -> HarvestResult:
        """
        Near real-time polling mode for one channel.

        `max_polls=None` runs continuously.
        """
        result = HarvestResult(channel_name=channel.name)
        source = await self._get_or_create_source(channel)
        polls = 0
        last_seen_id = 0

        await self._ensure_connected()
        while max_polls is None or polls < max_polls:
            polls += 1
            entity = await self.client.get_entity(channel.channel)
            messages = await self.client.get_messages(
                entity,
                limit=channel.max_messages_per_fetch,
            )
            message_list = list(messages) if messages is not None else []
            for message in reversed(message_list):
                message_id = self._message_id(message)
                if message_id is None or message_id <= last_seen_id:
                    continue

                result.messages_fetched += 1
                was_stored = await self._process_message(source, channel, message)
                if was_stored:
                    result.messages_stored += 1
                else:
                    result.messages_skipped += 1
                last_seen_id = message_id

            await asyncio.sleep(max(self.min_request_interval_seconds, poll_interval_seconds))

        return result

    async def _process_message(
        self,
        source: Source,
        channel: ChannelConfig,
        message: Any,
    ) -> bool:
        message_id = self._message_id(message)
        if message_id is None:
            return False

        external_id = f"{channel.channel}:{message_id}"
        url = self._message_url(channel, message_id)
        content = self._extract_message_text(message, include_media=channel.include_media)
        if content is None:
            return False

        content_hash = self._compute_hash(content)
        if await self._is_duplicate(external_id=external_id, url=url, content_hash=content_hash):
            return False

        title = self._build_title(content)
        item = await self._store_item(
            source=source,
            external_id=external_id,
            url=url,
            title=title,
            author=self._message_author(message),
            published_at=self._message_datetime(message),
            raw_content=content,
            content_hash=content_hash,
            language=channel.language,
        )
        return item is not None

    async def _store_item(
        self,
        source: Source,
        external_id: str,
        url: str | None,
        title: str | None,
        author: str | None,
        published_at: datetime | None,
        raw_content: str,
        content_hash: str,
        language: str | None,
    ) -> RawItem | None:
        item = RawItem(
            source_id=source.id,
            external_id=external_id,
            url=url,
            title=title,
            author=author,
            published_at=published_at,
            raw_content=raw_content,
            content_hash=content_hash,
            language=language,
            processing_status=ProcessingStatus.PENDING,
        )

        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            logger.debug("Duplicate Telegram item skipped on insert race", external_id=external_id)
            return None
        return item

    async def _is_duplicate(
        self,
        external_id: str,
        url: str | None,
        content_hash: str,
    ) -> bool:
        window_start = datetime.now(tz=UTC) - timedelta(days=self.dedup_window_days)
        conditions: list[Any] = [
            RawItem.external_id == external_id,
            RawItem.content_hash == content_hash,
        ]
        if url is not None:
            conditions.append(RawItem.url == url)

        duplicate_query = (
            select(RawItem.id)
            .where(RawItem.fetched_at >= window_start)
            .where(or_(*conditions))
            .limit(1)
        )
        return await self.session.scalar(duplicate_query) is not None

    async def _get_or_create_source(self, channel: ChannelConfig) -> Source:
        source_query = select(Source).where(
            Source.type == SourceType.TELEGRAM,
            Source.name == channel.name,
        )
        source = await self.session.scalar(source_query)
        config_payload = {
            "channel": channel.channel,
            "categories": channel.categories,
            "check_interval_minutes": channel.check_interval_minutes,
            "max_messages_per_fetch": channel.max_messages_per_fetch,
            "include_media": channel.include_media,
            "language": channel.language,
            **channel.extra,
        }
        channel_url = self._channel_url(channel.channel)

        if source is None:
            source = Source(
                type=SourceType.TELEGRAM,
                name=channel.name,
                url=channel_url,
                credibility_score=channel.credibility,
                source_tier=channel.source_tier,
                reporting_type=channel.reporting_type,
                config=config_payload,
                is_active=channel.enabled,
            )
            self.session.add(source)
            await self.session.flush()
            return source

        source.url = channel_url
        source.credibility_score = channel.credibility
        source.source_tier = channel.source_tier
        source.reporting_type = channel.reporting_type
        source.config = config_payload
        source.is_active = channel.enabled
        return source

    async def _record_source_success(self, source: Source) -> None:
        source.last_fetched_at = datetime.now(tz=UTC)
        source.error_count = 0
        source.last_error = None
        await self.session.flush()

    async def _record_source_failure(self, source: Source, error: str) -> None:
        source.error_count = source.error_count + 1
        source.last_error = error[:1000]
        await self.session.flush()

    async def _ensure_connected(self) -> None:
        is_connected_fn = getattr(self.client, "is_connected", None)
        is_connected = is_connected_fn() if callable(is_connected_fn) else False
        if is_connected:
            return
        await self.client.connect()

    async def _disconnect_if_owned(self) -> None:
        if self._owns_client:
            await self.client.disconnect()

    @staticmethod
    def _parse_settings(raw_settings: dict[str, Any]) -> HarvesterSettings:
        return HarvesterSettings(
            default_check_interval_minutes=int(
                raw_settings.get("default_check_interval_minutes", 15)
            ),
            default_max_messages_per_fetch=int(
                raw_settings.get("default_max_messages_per_fetch", 100)
            ),
        )

    @staticmethod
    def _parse_channels(
        raw_settings: dict[str, Any],
        raw_channels: list[Any],
    ) -> list[ChannelConfig]:
        default_interval = int(raw_settings.get("default_check_interval_minutes", 15))
        default_max_messages = int(raw_settings.get("default_max_messages_per_fetch", 100))

        channels: list[ChannelConfig] = []
        for raw_channel in raw_channels:
            if not isinstance(raw_channel, dict):
                continue

            name = TelegramHarvester._safe_str(raw_channel.get("name"))
            channel_ref = TelegramHarvester._safe_str(raw_channel.get("channel"))
            if name is None or channel_ref is None:
                continue

            categories_raw = raw_channel.get("categories", [])
            categories = (
                [str(category).strip() for category in categories_raw if str(category).strip()]
                if isinstance(categories_raw, list)
                else []
            )
            known_keys = {
                "name",
                "channel",
                "credibility",
                "categories",
                "check_interval_minutes",
                "max_messages_per_fetch",
                "include_media",
                "language",
                "source_tier",
                "reporting_type",
                "enabled",
            }
            extra = {key: value for key, value in raw_channel.items() if key not in known_keys}

            channels.append(
                ChannelConfig(
                    name=name,
                    channel=channel_ref,
                    credibility=float(raw_channel.get("credibility", 0.5)),
                    categories=categories,
                    check_interval_minutes=int(
                        raw_channel.get("check_interval_minutes", default_interval)
                    ),
                    max_messages_per_fetch=int(
                        raw_channel.get("max_messages_per_fetch", default_max_messages)
                    ),
                    include_media=bool(raw_channel.get("include_media", True)),
                    language=TelegramHarvester._safe_str(raw_channel.get("language")),
                    source_tier=str(raw_channel.get("source_tier", "regional")),
                    reporting_type=str(raw_channel.get("reporting_type", "secondary")),
                    enabled=bool(raw_channel.get("enabled", True)),
                    extra=extra,
                )
            )

        return channels

    @staticmethod
    def _message_id(message: Any) -> int | None:
        raw_message_id = getattr(message, "id", None)
        if isinstance(raw_message_id, int):
            return raw_message_id
        return None

    @staticmethod
    def _message_url(channel: ChannelConfig, message_id: int) -> str | None:
        channel_ref = channel.channel.strip()
        if channel_ref.startswith("@"):
            return f"https://t.me/{channel_ref[1:]}/{message_id}"
        if channel_ref.startswith("https://t.me/"):
            return f"{channel_ref.rstrip('/')}/{message_id}"
        if channel_ref.startswith("t.me/"):
            return f"https://{channel_ref.rstrip('/')}/{message_id}"
        return None

    @staticmethod
    def _channel_url(channel_ref: str) -> str | None:
        normalized = channel_ref.strip()
        if normalized.startswith("@"):
            return f"https://t.me/{normalized[1:]}"
        if normalized.startswith("https://t.me/"):
            return normalized.rstrip("/")
        if normalized.startswith("t.me/"):
            return f"https://{normalized.rstrip('/')}"
        return None

    @staticmethod
    def _message_author(message: Any) -> str | None:
        sender = getattr(message, "sender", None)
        if sender is not None:
            username = TelegramHarvester._safe_str(getattr(sender, "username", None))
            if username:
                return username
            first_name = TelegramHarvester._safe_str(getattr(sender, "first_name", None))
            if first_name:
                return first_name
        sender_id = getattr(message, "sender_id", None)
        if isinstance(sender_id, int):
            return str(sender_id)
        return None

    @staticmethod
    def _message_datetime(message: Any) -> datetime | None:
        raw_date = getattr(message, "date", None)
        if not isinstance(raw_date, datetime):
            return None
        if raw_date.tzinfo is None:
            return raw_date.replace(tzinfo=UTC)
        return raw_date.astimezone(UTC)

    @staticmethod
    def _extract_message_text(message: Any, include_media: bool) -> str | None:
        text = TelegramHarvester._safe_str(
            getattr(message, "message", None) or getattr(message, "raw_text", None)
        )
        if text is not None:
            return text

        if not include_media:
            return None

        media = getattr(message, "media", None)
        if media is None:
            return None

        parts: list[str] = []
        media_class = media.__class__.__name__
        if media_class:
            parts.append(media_class)

        document = getattr(media, "document", None)
        attributes = getattr(document, "attributes", None)
        if isinstance(attributes, list):
            for attribute in attributes:
                file_name = TelegramHarvester._safe_str(getattr(attribute, "file_name", None))
                if file_name:
                    parts.append(file_name)

        if getattr(media, "photo", None) is not None:
            parts.append("photo")

        if not parts:
            return None
        return " ".join(parts)

    @staticmethod
    def _build_title(content: str) -> str:
        first_line = content.splitlines()[0].strip()
        return first_line[:200]

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        as_str = str(value).strip()
        return as_str or None
