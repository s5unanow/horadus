from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.core.api_key_manager import APIKeyManager

pytestmark = pytest.mark.unit


def _build_manager(
    *,
    auth_enabled: bool = True,
    rate_limit_per_minute: int = 5,
    persist_path: str | None = None,
    redis_client: Any | None = None,
    rate_limit_backend: str = "auto",
    rate_limit_strategy: str = "fixed_window",
    wall_time_fn: Any | None = None,
) -> APIKeyManager:
    return APIKeyManager(
        auth_enabled=auth_enabled,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=rate_limit_per_minute,
        persist_path=persist_path,
        redis_client=redis_client,
        rate_limit_backend=rate_limit_backend,
        rate_limit_strategy=rate_limit_strategy,
        wall_time_fn=wall_time_fn,
    )


class _FakeRedisPipeline:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client
        self._commands: list[tuple[str, str, int | None]] = []

    def incr(self, key: str) -> _FakeRedisPipeline:
        self._commands.append(("incr", key, None))
        return self

    def expireat(self, key: str, when: int) -> _FakeRedisPipeline:
        self._commands.append(("expireat", key, when))
        return self

    def execute(self) -> list[int | bool]:
        results: list[int | bool] = []
        for action, key, arg in self._commands:
            if action == "incr":
                results.append(self._client.incr(key))
            elif action == "expireat":
                assert arg is not None
                results.append(self._client.expireat(key, arg))
        return results


class _FakeRedisClient:
    def __init__(self, now_fn) -> None:
        self._now_fn = now_fn
        self._values: dict[str, int] = {}
        self._expire_at: dict[str, int] = {}
        self._zset_values: dict[str, dict[str, int]] = {}

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        _ = transaction
        return _FakeRedisPipeline(self)

    def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        self._values[key] = self._values.get(key, 0) + 1
        return self._values[key]

    def expireat(self, key: str, when: int) -> bool:
        self._expire_at[key] = when
        return True

    def eval(
        self,
        script: str,
        numkeys: int,
        key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member: str,
    ) -> list[int]:
        _ = script
        if numkeys != 1:
            raise ValueError("fake redis eval only supports one key")

        cutoff = now_ms - window_ms
        zset = self._zset_values.setdefault(key, {})
        stale_members = [entry for entry, score in zset.items() if score <= cutoff]
        for stale_member in stale_members:
            zset.pop(stale_member, None)

        if len(zset) < limit:
            zset[member] = now_ms
            return [1, 0]

        oldest_score = min(zset.values()) if zset else now_ms
        retry_after_ms = max(1, window_ms - (now_ms - oldest_score))
        return [0, retry_after_ms]

    def _purge_if_expired(self, key: str) -> None:
        expires = self._expire_at.get(key)
        if expires is None:
            return
        if int(self._now_fn()) >= expires:
            self._values.pop(key, None)
            self._expire_at.pop(key, None)


def test_authenticate_accepts_configured_keys() -> None:
    manager = _build_manager()
    _record1, credential1 = manager.create_key(name="first")
    _record2, credential2 = manager.create_key(name="second")

    legacy = manager.authenticate(credential1)
    secondary = manager.authenticate(credential2)
    missing = manager.authenticate("unknown")

    assert legacy is not None
    assert secondary is not None
    assert missing is None
    assert manager.auth_required is True
    assert legacy.hash_version == "scrypt-v1"
    assert legacy.key_hash.startswith("scrypt-v1$")


def test_create_and_revoke_key() -> None:
    manager = _build_manager()
    record, raw_key = manager.create_key(name="dashboard")

    assert record.is_active is True
    assert manager.authenticate(raw_key) is not None

    revoked = manager.revoke_key(record.id)

    assert revoked is True
    assert manager.authenticate(raw_key) is None


def test_per_key_rate_limit_blocks_after_threshold() -> None:
    manager = _build_manager(rate_limit_per_minute=2)
    record, credential = manager.create_key(name="rate-limited")
    authenticated = manager.authenticate(credential)
    assert authenticated is not None

    allowed1, retry1 = manager.check_rate_limit(record.id)
    allowed2, retry2 = manager.check_rate_limit(record.id)
    blocked, retry3 = manager.check_rate_limit(record.id)

    assert allowed1 is True
    assert retry1 is None
    assert allowed2 is True
    assert retry2 is None
    assert blocked is False
    assert retry3 is not None
    assert retry3 > 0


def test_fixed_window_allows_boundary_burst() -> None:
    now = [59.9]
    manager = _build_manager(
        rate_limit_per_minute=1,
        rate_limit_backend="memory",
        rate_limit_strategy="fixed_window",
        wall_time_fn=lambda: now[0],
    )
    record, credential = manager.create_key(name="fixed-window")
    assert manager.authenticate(credential) is not None

    allowed_first, _retry_first = manager.check_rate_limit(record.id)
    now[0] = 60.1
    allowed_second, retry_second = manager.check_rate_limit(record.id)

    assert allowed_first is True
    assert allowed_second is True
    assert retry_second is None


def test_sliding_window_blocks_boundary_burst() -> None:
    now = [59.9]
    manager = _build_manager(
        rate_limit_per_minute=1,
        rate_limit_backend="memory",
        rate_limit_strategy="sliding_window",
        wall_time_fn=lambda: now[0],
    )
    record, credential = manager.create_key(name="sliding-window")
    assert manager.authenticate(credential) is not None

    allowed_first, retry_first = manager.check_rate_limit(record.id)
    assert allowed_first is True
    assert retry_first is None

    now[0] = 60.1
    allowed_second, retry_second = manager.check_rate_limit(record.id)
    assert allowed_second is False
    assert retry_second is not None
    assert retry_second > 0


def test_runtime_keys_persist_and_reload(tmp_path: Path) -> None:
    persist_path = str(tmp_path / "api_keys.json")
    manager = _build_manager(persist_path=persist_path)
    _record, raw_key = manager.create_key(name="persisted")

    reloaded_manager = _build_manager(persist_path=persist_path)

    assert reloaded_manager.authenticate(raw_key) is not None


def test_authenticate_migrates_legacy_sha256_hash(tmp_path: Path) -> None:
    persist_path = tmp_path / "api_keys.json"
    raw_key = "geo_legacy_key"
    legacy_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    payload = [
        {
            "id": "legacy-id",
            "name": "legacy",
            "prefix": raw_key[:8],
            "key_hash": legacy_hash,
            "is_active": True,
            "rate_limit_per_minute": 5,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "last_used_at": None,
            "revoked_at": None,
            "source": "persisted",
        }
    ]
    persist_path.write_text(json.dumps(payload), encoding="utf-8")

    manager = _build_manager(persist_path=str(persist_path))
    record = manager.authenticate(raw_key)

    assert record is not None
    assert record.hash_version == "scrypt-v1"
    assert record.key_hash != legacy_hash
    assert record.key_hash.startswith("scrypt-v1$")

    refreshed = json.loads(persist_path.read_text(encoding="utf-8"))
    assert refreshed[0]["hash_version"] == "scrypt-v1"
    assert refreshed[0]["key_hash"].startswith("scrypt-v1$")


def test_rotate_key_revokes_old_and_returns_new() -> None:
    manager = _build_manager()
    record, raw_key = manager.create_key(name="rotate-me")

    rotated = manager.rotate_key(record.id)

    assert rotated is not None
    new_record, new_raw_key = rotated
    assert new_record.id != record.id
    assert manager.authenticate(raw_key) is None
    assert manager.authenticate(new_raw_key) is not None


def test_distributed_rate_limit_is_shared_across_manager_instances(tmp_path: Path) -> None:
    now = [1_700_000_000.0]
    redis_client = _FakeRedisClient(now_fn=lambda: now[0])
    persist_path = str(tmp_path / "api_keys.json")
    manager_one = _build_manager(
        persist_path=persist_path,
        redis_client=redis_client,
        rate_limit_backend="redis",
        wall_time_fn=lambda: now[0],
    )
    _record, credential = manager_one.create_key(name="shared-limit", rate_limit_per_minute=1)

    manager_two = _build_manager(
        persist_path=persist_path,
        redis_client=redis_client,
        rate_limit_backend="redis",
        wall_time_fn=lambda: now[0],
    )
    record_one = manager_one.authenticate(credential)
    record_two = manager_two.authenticate(credential)
    assert record_one is not None
    assert record_two is not None

    allowed_first, retry_first = manager_one.check_rate_limit(record_one.id)
    allowed_second, retry_second = manager_two.check_rate_limit(record_two.id)

    assert allowed_first is True
    assert retry_first is None
    assert allowed_second is False
    assert retry_second is not None
    assert retry_second > 0


def test_distributed_rate_limit_retry_after_is_deterministic() -> None:
    now = [120.0]
    redis_client = _FakeRedisClient(now_fn=lambda: now[0])
    manager = _build_manager(
        redis_client=redis_client,
        rate_limit_backend="redis",
        wall_time_fn=lambda: now[0],
        rate_limit_per_minute=1,
    )
    record, credential = manager.create_key(name="edge-limit", rate_limit_per_minute=1)
    assert manager.authenticate(credential) is not None

    allowed_first, retry_first = manager.check_rate_limit(record.id)
    blocked_second, retry_second = manager.check_rate_limit(record.id)

    assert allowed_first is True
    assert retry_first is None
    assert blocked_second is False
    assert retry_second == 60

    now[0] = 179.0
    blocked_third, retry_third = manager.check_rate_limit(record.id)
    assert blocked_third is False
    assert retry_third == 1


def test_distributed_sliding_window_is_shared_across_manager_instances(tmp_path: Path) -> None:
    now = [59.9]
    redis_client = _FakeRedisClient(now_fn=lambda: now[0])
    persist_path = str(tmp_path / "api_keys.json")
    manager_one = _build_manager(
        persist_path=persist_path,
        redis_client=redis_client,
        rate_limit_backend="redis",
        rate_limit_strategy="sliding_window",
        wall_time_fn=lambda: now[0],
    )
    _record, credential = manager_one.create_key(name="shared-sliding", rate_limit_per_minute=1)
    manager_two = _build_manager(
        persist_path=persist_path,
        redis_client=redis_client,
        rate_limit_backend="redis",
        rate_limit_strategy="sliding_window",
        wall_time_fn=lambda: now[0],
    )
    record_one = manager_one.authenticate(credential)
    record_two = manager_two.authenticate(credential)
    assert record_one is not None
    assert record_two is not None

    allowed_first, retry_first = manager_one.check_rate_limit(record_one.id)
    assert allowed_first is True
    assert retry_first is None

    now[0] = 60.1
    blocked_second, retry_second = manager_two.check_rate_limit(record_two.id)
    assert blocked_second is False
    assert retry_second is not None
    assert retry_second > 0
