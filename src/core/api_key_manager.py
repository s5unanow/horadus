"""
API key authentication and in-memory per-key rate limiting.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from threading import RLock
from typing import Literal
from uuid import uuid4

from src.core.config import settings


@dataclass(slots=True)
class APIKeyRecord:
    id: str
    name: str
    prefix: str
    key_hash: str
    is_active: bool
    rate_limit_per_minute: int
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    source: Literal["env", "runtime"]


class APIKeyManager:
    """Manage API keys and request rate limits."""

    def __init__(
        self,
        *,
        auth_enabled: bool,
        legacy_api_key: str | None,
        static_api_keys: list[str],
        default_rate_limit_per_minute: int,
    ) -> None:
        self._auth_enabled = auth_enabled
        self._default_rate_limit_per_minute = max(1, default_rate_limit_per_minute)
        self._records_by_id: dict[str, APIKeyRecord] = {}
        self._id_by_hash: dict[str, str] = {}
        self._request_windows: dict[str, deque[float]] = {}
        self._lock = RLock()

        bootstrap_keys = [key for key in [legacy_api_key, *static_api_keys] if key]
        for index, raw_key in enumerate(bootstrap_keys, start=1):
            self._add_key(
                raw_key=raw_key,
                name=f"env-key-{index}",
                source="env",
                rate_limit_per_minute=self._default_rate_limit_per_minute,
            )

    @property
    def auth_required(self) -> bool:
        return self._auth_enabled or bool(self._records_by_id)

    def authenticate(self, raw_key: str) -> APIKeyRecord | None:
        normalized = raw_key.strip()
        if not normalized:
            return None

        key_hash = self._hash_key(normalized)
        with self._lock:
            key_id = self._id_by_hash.get(key_hash)
            if key_id is None:
                return None
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return None
            record.last_used_at = datetime.now(tz=UTC)
            return record

    def list_keys(self) -> list[APIKeyRecord]:
        with self._lock:
            return sorted(
                self._records_by_id.values(),
                key=lambda record: record.created_at,
            )

    def create_key(
        self,
        *,
        name: str,
        rate_limit_per_minute: int | None = None,
    ) -> tuple[APIKeyRecord, str]:
        raw_key = f"geo_{secrets.token_urlsafe(24)}"
        configured_limit = (
            self._default_rate_limit_per_minute
            if rate_limit_per_minute is None
            else max(1, rate_limit_per_minute)
        )
        with self._lock:
            record = self._add_key(
                raw_key=raw_key,
                name=name,
                source="runtime",
                rate_limit_per_minute=configured_limit,
            )
        return (record, raw_key)

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return False
            record.is_active = False
            record.revoked_at = datetime.now(tz=UTC)
            self._request_windows.pop(key_id, None)
            return True

    def check_rate_limit(self, key_id: str) -> tuple[bool, int | None]:
        now = time.monotonic()
        with self._lock:
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return (False, None)

            window = self._request_windows.setdefault(key_id, deque())
            while window and (now - window[0]) >= 60.0:
                window.popleft()

            if len(window) >= record.rate_limit_per_minute:
                retry_after = int(max(1, 60 - (now - window[0])))
                return (False, retry_after)

            window.append(now)
            return (True, None)

    def _add_key(
        self,
        *,
        raw_key: str,
        name: str,
        source: Literal["env", "runtime"],
        rate_limit_per_minute: int,
    ) -> APIKeyRecord:
        normalized = raw_key.strip()
        if not normalized:
            msg = "API key cannot be blank"
            raise ValueError(msg)

        key_hash = self._hash_key(normalized)
        existing_id = self._id_by_hash.get(key_hash)
        if existing_id is not None:
            return self._records_by_id[existing_id]

        now = datetime.now(tz=UTC)
        key_id = str(uuid4())
        record = APIKeyRecord(
            id=key_id,
            name=name.strip() or "unnamed",
            prefix=normalized[:8],
            key_hash=key_hash,
            is_active=True,
            rate_limit_per_minute=max(1, rate_limit_per_minute),
            created_at=now,
            last_used_at=None,
            revoked_at=None,
            source=source,
        )
        self._records_by_id[key_id] = record
        self._id_by_hash[key_hash] = key_id
        return record

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@lru_cache
def get_api_key_manager() -> APIKeyManager:
    """Get singleton API key manager configured from settings."""
    return APIKeyManager(
        auth_enabled=settings.API_AUTH_ENABLED,
        legacy_api_key=settings.API_KEY,
        static_api_keys=settings.API_KEYS,
        default_rate_limit_per_minute=settings.API_RATE_LIMIT_PER_MINUTE,
    )
