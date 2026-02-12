"""
API key authentication and distributed per-key rate limiting.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

import redis
import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class APIKeyRecord:
    id: str
    name: str
    prefix: str
    key_hash: str
    hash_version: str
    is_active: bool
    rate_limit_per_minute: int
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    source: Literal["env", "runtime", "persisted"]


class APIKeyManager:
    """Manage API keys and request rate limits."""

    _HASH_VERSION_SCRYPT_V1 = "scrypt-v1"
    _HASH_VERSION_SHA256_V1 = "sha256-v1"
    _SCRYPT_N = 2**14
    _SCRYPT_R = 8
    _SCRYPT_P = 1
    _SCRYPT_DKLEN = 32
    _RATE_LIMIT_DEGRADE_RETRY_SECONDS = 30

    def __init__(
        self,
        *,
        auth_enabled: bool,
        legacy_api_key: str | None,
        static_api_keys: list[str],
        default_rate_limit_per_minute: int,
        persist_path: str | None = None,
        redis_client: redis.Redis[str] | None = None,
        rate_limit_backend: Literal["auto", "redis", "memory"] = "auto",
        wall_time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._auth_enabled = auth_enabled
        self._default_rate_limit_per_minute = max(1, default_rate_limit_per_minute)
        self._records_by_id: dict[str, APIKeyRecord] = {}
        self._request_windows: dict[str, deque[float]] = {}
        self._lock = RLock()
        self._persist_path = Path(persist_path).expanduser() if persist_path else None
        self._rate_limit_backend = rate_limit_backend
        self._rate_limit_window_seconds = max(1, settings.API_RATE_LIMIT_WINDOW_SECONDS)
        self._rate_limit_redis_prefix = (
            settings.API_RATE_LIMIT_REDIS_PREFIX.strip() or "horadus:api_rate_limit"
        )
        self._redis_client = redis_client
        self._redis_unavailable_until = 0.0
        self._wall_time_fn = wall_time_fn or time.time

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

        with self._lock:
            for record in self._records_by_id.values():
                if not record.is_active:
                    continue
                if not self._verify_key_hash(normalized, record.key_hash):
                    continue

                if record.hash_version != self._HASH_VERSION_SCRYPT_V1:
                    record.key_hash = self._hash_key(normalized)
                    record.hash_version = self._HASH_VERSION_SCRYPT_V1
                    self._save_persisted_keys()

                record.last_used_at = datetime.now(tz=UTC)
                return record
            return None

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
        now = self._wall_time_fn()
        with self._lock:
            record = self._records_by_id.get(key_id)
            if record is None or not record.is_active:
                return (False, None)
            per_minute_limit = record.rate_limit_per_minute

        distributed_result = self._check_rate_limit_distributed(
            key_id=key_id,
            per_minute_limit=per_minute_limit,
            now=now,
        )
        if distributed_result is not None:
            return distributed_result

        with self._lock:
            window = self._request_windows.setdefault(key_id, deque())
            while window and (now - window[0]) >= self._rate_limit_window_seconds:
                window.popleft()

            if len(window) >= per_minute_limit:
                retry_after = int(max(1, self._rate_limit_window_seconds - (now - window[0])))
                return (False, retry_after)

            window.append(now)
            return (True, None)

    def _check_rate_limit_distributed(
        self,
        *,
        key_id: str,
        per_minute_limit: int,
        now: float,
    ) -> tuple[bool, int | None] | None:
        if self._rate_limit_backend == "memory":
            return None
        if now < self._redis_unavailable_until:
            return None

        try:
            redis_client = self._get_redis_client()
            window_start = (
                int(now // self._rate_limit_window_seconds) * self._rate_limit_window_seconds
            )
            window_end = window_start + self._rate_limit_window_seconds
            bucket_key = f"{self._rate_limit_redis_prefix}:{key_id}:{window_start}"

            pipeline = redis_client.pipeline(transaction=True)
            pipeline.incr(bucket_key)
            pipeline.expireat(bucket_key, window_end + 1)
            count_raw, _expire_set = pipeline.execute()
            count = int(count_raw)
            if count <= per_minute_limit:
                return (True, None)

            retry_after = max(1, window_end - int(now))
            return (False, retry_after)
        except Exception:
            self._redis_unavailable_until = now + self._RATE_LIMIT_DEGRADE_RETRY_SECONDS
            logger.warning(
                "Rate limit backend degraded to memory",
                backend=self._rate_limit_backend,
                retry_after_seconds=self._RATE_LIMIT_DEGRADE_RETRY_SECONDS,
            )
            return None

    def _get_redis_client(self) -> redis.Redis[str]:
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
            )
        return self._redis_client

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

        for existing in self._records_by_id.values():
            if not existing.is_active:
                continue
            if self._verify_key_hash(normalized, existing.key_hash):
                return existing

        now = datetime.now(tz=UTC)
        key_id = str(uuid4())
        key_hash = self._hash_key(normalized)
        record = APIKeyRecord(
            id=key_id,
            name=name.strip() or "unnamed",
            prefix=normalized[:8],
            key_hash=key_hash,
            hash_version=self._HASH_VERSION_SCRYPT_V1,
            is_active=True,
            rate_limit_per_minute=max(1, rate_limit_per_minute),
            created_at=now,
            last_used_at=None,
            revoked_at=None,
            source=source,
        )
        self._records_by_id[key_id] = record
        return record

    def _add_record(self, record: APIKeyRecord) -> APIKeyRecord:
        existing = self._records_by_id.get(record.id)
        if existing is not None:
            return existing
        self._records_by_id[record.id] = record
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
                hash_version=self._coerce_hash_version(
                    row.get("hash_version"),
                    key_hash=key_hash,
                ),
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

    @classmethod
    def _coerce_hash_version(cls, value: object, *, key_hash: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {cls._HASH_VERSION_SCRYPT_V1, cls._HASH_VERSION_SHA256_V1}:
                return normalized
        if cls._is_scrypt_hash(key_hash):
            return cls._HASH_VERSION_SCRYPT_V1
        return cls._HASH_VERSION_SHA256_V1

    @classmethod
    def _is_scrypt_hash(cls, key_hash: str) -> bool:
        return key_hash.startswith(f"{cls._HASH_VERSION_SCRYPT_V1}$")

    @classmethod
    def _hash_key(cls, raw_key: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            raw_key.encode("utf-8"),
            salt=salt,
            n=cls._SCRYPT_N,
            r=cls._SCRYPT_R,
            p=cls._SCRYPT_P,
            dklen=cls._SCRYPT_DKLEN,
        )
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
        digest_b64 = base64.urlsafe_b64encode(derived).decode("ascii")
        return (
            f"{cls._HASH_VERSION_SCRYPT_V1}$"
            f"{cls._SCRYPT_N}${cls._SCRYPT_R}${cls._SCRYPT_P}$"
            f"{salt_b64}${digest_b64}"
        )

    @classmethod
    def _verify_key_hash(cls, raw_key: str, key_hash: str) -> bool:
        if cls._is_scrypt_hash(key_hash):
            parts = key_hash.split("$")
            if len(parts) != 6:
                return False
            _scheme, n_raw, r_raw, p_raw, salt_b64, digest_b64 = parts
            try:
                n = int(n_raw)
                r = int(r_raw)
                p = int(p_raw)
                salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
                expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            except (ValueError, binascii.Error):
                return False

            derived = hashlib.scrypt(
                raw_key.encode("utf-8"),
                salt=salt,
                n=n,
                r=r,
                p=p,
                dklen=len(expected),
            )
            return secrets.compare_digest(derived, expected)

        expected_sha256 = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return secrets.compare_digest(expected_sha256, key_hash)


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
