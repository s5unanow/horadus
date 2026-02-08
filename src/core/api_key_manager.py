"""
API key authentication and in-memory per-key rate limiting.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
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
    source: Literal["env", "runtime", "persisted"]


class APIKeyManager:
    """Manage API keys and request rate limits."""

    def __init__(
        self,
        *,
        auth_enabled: bool,
        legacy_api_key: str | None,
        static_api_keys: list[str],
        default_rate_limit_per_minute: int,
        persist_path: str | None = None,
    ) -> None:
        self._auth_enabled = auth_enabled
        self._default_rate_limit_per_minute = max(1, default_rate_limit_per_minute)
        self._records_by_id: dict[str, APIKeyRecord] = {}
        self._id_by_hash: dict[str, str] = {}
        self._request_windows: dict[str, deque[float]] = {}
        self._lock = RLock()
        self._persist_path = Path(persist_path).expanduser() if persist_path else None

        bootstrap_keys = [key for key in [legacy_api_key, *static_api_keys] if key]
        for index, raw_key in enumerate(bootstrap_keys, start=1):
            self._add_key(
                raw_key=raw_key,
                name=f"env-key-{index}",
                source="env",
                rate_limit_per_minute=self._default_rate_limit_per_minute,
            )
        self._load_persisted_keys()

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
            self._save_persisted_keys()
        return (record, raw_key)

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return False
            record.is_active = False
            record.revoked_at = datetime.now(tz=UTC)
            self._request_windows.pop(key_id, None)
            self._save_persisted_keys()
            return True

    def rotate_key(self, key_id: str) -> tuple[APIKeyRecord, str] | None:
        with self._lock:
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return None

            replacement_raw_key = f"geo_{secrets.token_urlsafe(24)}"
            replacement_record = self._add_key(
                raw_key=replacement_raw_key,
                name=record.name,
                source="runtime",
                rate_limit_per_minute=record.rate_limit_per_minute,
            )
            record.is_active = False
            record.revoked_at = datetime.now(tz=UTC)
            self._request_windows.pop(record.id, None)
            self._save_persisted_keys()
            return replacement_record, replacement_raw_key

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

    def _add_record(self, record: APIKeyRecord) -> APIKeyRecord:
        existing_id = self._id_by_hash.get(record.key_hash)
        if existing_id is not None:
            return self._records_by_id[existing_id]
        self._records_by_id[record.id] = record
        self._id_by_hash[record.key_hash] = record.id
        return record

    def _load_persisted_keys(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return

        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return

        for row in payload:
            if not isinstance(row, dict):
                continue
            key_hash = str(row.get("key_hash", "")).strip()
            if not key_hash:
                continue
            try:
                rate_limit = max(1, int(row.get("rate_limit_per_minute", 1)))
            except (TypeError, ValueError):
                continue

            created_at = self._parse_datetime(row.get("created_at")) or datetime.now(tz=UTC)
            last_used_at = self._parse_datetime(row.get("last_used_at"))
            revoked_at = self._parse_datetime(row.get("revoked_at"))
            record = APIKeyRecord(
                id=str(row.get("id") or uuid4()),
                name=str(row.get("name") or "unnamed"),
                prefix=str(row.get("prefix") or "")[:8],
                key_hash=key_hash,
                is_active=bool(row.get("is_active", True)),
                rate_limit_per_minute=rate_limit,
                created_at=created_at,
                last_used_at=last_used_at,
                revoked_at=revoked_at,
                source="persisted",
            )
            self._add_record(record)

    def _save_persisted_keys(self) -> None:
        if self._persist_path is None:
            return

        persisted = [
            record
            for record in self._records_by_id.values()
            if record.source in {"runtime", "persisted"}
        ]
        rows = []
        for record in persisted:
            row = asdict(record)
            row["created_at"] = record.created_at.isoformat()
            row["last_used_at"] = record.last_used_at.isoformat() if record.last_used_at else None
            row["revoked_at"] = record.revoked_at.isoformat() if record.revoked_at else None
            rows.append(row)

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._persist_path.with_suffix(f"{self._persist_path.suffix}.tmp")
        tmp_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._persist_path)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

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
        persist_path=settings.API_KEYS_PERSIST_PATH,
    )
