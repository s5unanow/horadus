from __future__ import annotations

import hashlib
import json
import stat
from base64 import urlsafe_b64encode
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import src.core.api_key_manager as api_key_manager_module
from src.core.api_key_manager import APIKeyManager, APIKeyRecord, get_api_key_manager

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


def test_runtime_keys_persist_and_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "api_keys.json"
    observed: dict[str, int] = {}
    original_replace = api_key_manager_module.os.replace

    def _record_tmp_mode(src: str | bytes, dst: str | bytes) -> None:
        observed["tmp_mode"] = stat.S_IMODE(Path(src).stat().st_mode)
        original_replace(src, dst)

    manager = _build_manager(persist_path=str(persist_path))
    monkeypatch.setattr(
        api_key_manager_module.os,
        "replace",
        _record_tmp_mode,
    )
    _record, raw_key = manager.create_key(name="persisted")

    reloaded_manager = _build_manager(persist_path=str(persist_path))

    assert reloaded_manager.authenticate(raw_key) is not None
    assert observed["tmp_mode"] == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(persist_path.stat().st_mode) == 0o600


def test_runtime_key_persistence_fails_closed_when_directory_hardening_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "persist" / "api_keys.json"
    original_chmod = Path.chmod

    def _fail_directory_chmod(self: Path, mode: int) -> None:
        if self == persist_path.parent:
            raise OSError("chmod blocked")
        original_chmod(self, mode)

    monkeypatch.setattr(Path, "chmod", _fail_directory_chmod)
    manager = _build_manager(persist_path=str(persist_path))

    with pytest.raises(
        api_key_manager_module.APIKeyPersistenceError,
        match="API key persist directory",
    ):
        manager.create_key(name="persisted")

    assert not persist_path.exists()


def test_set_fd_mode_and_verify_falls_back_to_path_chmod_without_fchmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "api_keys.json"
    persist_path.write_text("[]", encoding="utf-8")
    manager = _build_manager(persist_path=str(persist_path))

    monkeypatch.delattr(api_key_manager_module.os, "fchmod", raising=False)
    with persist_path.open("r+", encoding="utf-8") as handle:
        manager._set_fd_mode_and_verify(
            handle.fileno(),
            path=persist_path,
            expected_mode=0o600,
            label="persisted API key store",
        )

    assert stat.S_IMODE(persist_path.stat().st_mode) == 0o600


def test_set_fd_mode_and_verify_raises_when_fallback_chmod_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "api_keys.json"
    persist_path.write_text("[]", encoding="utf-8")
    manager = _build_manager(persist_path=str(persist_path))
    original_chmod = Path.chmod

    def _fail_chmod(self: Path, mode: int) -> None:
        if self == persist_path:
            raise OSError("chmod blocked")
        original_chmod(self, mode)

    monkeypatch.delattr(api_key_manager_module.os, "fchmod", raising=False)
    monkeypatch.setattr(Path, "chmod", _fail_chmod)
    with (
        persist_path.open("r+", encoding="utf-8") as handle,
        pytest.raises(
            api_key_manager_module.APIKeyPersistenceError,
            match="persisted API key store",
        ),
    ):
        manager._set_fd_mode_and_verify(
            handle.fileno(),
            path=persist_path,
            expected_mode=0o600,
            label="persisted API key store",
        )


def test_verify_path_mode_raises_when_stat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "api_keys.json"
    persist_path.write_text("[]", encoding="utf-8")
    original_stat = Path.stat

    def _fail_stat(self: Path, *args: object, **kwargs: object):
        if self == persist_path:
            raise OSError("stat blocked")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _fail_stat)

    with pytest.raises(
        api_key_manager_module.APIKeyPersistenceError,
        match="Could not verify mode",
    ):
        APIKeyManager._verify_path_mode(
            persist_path,
            expected_mode=0o600,
            label="persisted API key store",
        )


def test_verify_path_mode_raises_when_mode_does_not_match(tmp_path: Path) -> None:
    persist_path = tmp_path / "api_keys.json"
    persist_path.write_text("[]", encoding="utf-8")
    persist_path.chmod(0o644)

    with pytest.raises(
        api_key_manager_module.APIKeyPersistenceError,
        match="actual mode is 0o644",
    ):
        APIKeyManager._verify_path_mode(
            persist_path,
            expected_mode=0o600,
            label="persisted API key store",
        )


def test_save_persisted_keys_logs_when_temp_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_path = tmp_path / "api_keys.json"
    manager = _build_manager(persist_path=str(persist_path))
    warning_logger = MagicMock()
    original_unlink = Path.unlink

    def _raise_persistence_error(
        fd: int,
        *,
        path: Path,
        expected_mode: int,
        label: str,
    ) -> None:
        _ = (fd, path, expected_mode, label)
        raise api_key_manager_module.APIKeyPersistenceError("temp hardening failed")

    def _fail_tmp_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.parent == tmp_path and self.suffix == ".tmp":
            raise OSError("unlink blocked")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(api_key_manager_module, "logger", warning_logger)
    monkeypatch.setattr(manager, "_set_fd_mode_and_verify", _raise_persistence_error)
    monkeypatch.setattr(Path, "unlink", _fail_tmp_unlink)

    with pytest.raises(
        api_key_manager_module.APIKeyPersistenceError,
        match="temp hardening failed",
    ):
        manager.create_key(name="persisted")

    warning_logger.warning.assert_called_once()


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


def test_constructor_validates_strategy_and_bootstraps_env_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_key_manager_module.settings, "API_RATE_LIMIT_STRATEGY", "fixed_window")

    with pytest.raises(ValueError, match="API rate limit strategy must be one of"):
        _build_manager(rate_limit_strategy="invalid")

    manager = APIKeyManager(
        auth_enabled=False,
        legacy_api_key=" legacy-key ",
        static_api_keys=["static-key"],
        default_rate_limit_per_minute=3,
    )

    assert manager.auth_required is True
    assert len(manager.list_keys()) == 2
    assert manager.authenticate("legacy-key") is not None


def test_auth_required_false_without_keys_and_blank_authentication() -> None:
    manager = _build_manager(auth_enabled=False)

    assert manager.auth_required is False
    assert manager.authenticate("   ") is None


def test_list_keys_sorted_and_create_key_normalizes_name_and_limit() -> None:
    manager = _build_manager(rate_limit_per_minute=5)
    created_one, _raw_one = manager.create_key(name="  ", rate_limit_per_minute=0)
    created_two, _raw_two = manager.create_key(name="second", rate_limit_per_minute=None)

    listed = manager.list_keys()

    assert listed[0].id == created_one.id
    assert listed[0].name == "unnamed"
    assert listed[0].rate_limit_per_minute == 1
    assert listed[1].id == created_two.id
    assert listed[1].rate_limit_per_minute == 5


def test_revoke_and_rotate_return_falsey_for_missing_or_inactive_keys() -> None:
    manager = _build_manager()
    record, _raw = manager.create_key(name="revoke")
    assert manager.revoke_key("missing") is False
    assert manager.rotate_key("missing") is None
    assert manager.revoke_key(record.id) is True
    assert manager.revoke_key(record.id) is False
    assert manager.rotate_key(record.id) is None


def test_check_rate_limit_returns_false_for_unknown_or_revoked_keys() -> None:
    manager = _build_manager()
    record, _raw = manager.create_key(name="revoked")
    manager.revoke_key(record.id)

    assert manager.check_rate_limit("missing") == (False, None)
    assert manager.check_rate_limit(record.id) == (False, None)


def test_check_rate_limit_falls_back_to_memory_when_distributed_backend_returns_none() -> None:
    now = [1.0]
    manager = _build_manager(
        rate_limit_per_minute=1,
        rate_limit_backend="auto",
        rate_limit_strategy="sliding_window",
        wall_time_fn=lambda: now[0],
    )
    record, _raw = manager.create_key(name="fallback")
    manager._check_rate_limit_distributed = lambda **_: None

    assert manager.check_rate_limit(record.id) == (True, None)
    assert manager.check_rate_limit(record.id)[0] is False


def test_distributed_rate_limit_respects_memory_backend_and_degraded_retry_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _build_manager(rate_limit_backend="memory")
    assert manager._check_rate_limit_distributed(key_id="x", per_minute_limit=1, now=1.0) is None

    manager = _build_manager(rate_limit_backend="redis")
    manager._redis_unavailable_until = 10.0
    assert manager._check_rate_limit_distributed(key_id="x", per_minute_limit=1, now=5.0) is None

    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(
        api_key_manager_module.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )
    manager._check_rate_limit_distributed_fixed_window = lambda **_: (_ for _ in ()).throw(
        RuntimeError("redis down")
    )

    assert manager._check_rate_limit_distributed(key_id="x", per_minute_limit=1, now=20.0) is None
    assert manager._redis_unavailable_until == 50.0
    assert warnings[0]["event"] == "Rate limit backend degraded to memory"


def test_distributed_sliding_window_handles_invalid_redis_result_and_blocked_case() -> None:
    now = [10.0]
    redis_client = _FakeRedisClient(now_fn=lambda: now[0])
    manager = _build_manager(
        redis_client=redis_client,
        rate_limit_backend="redis",
        rate_limit_strategy="sliding_window",
        wall_time_fn=lambda: now[0],
    )

    redis_client.eval = lambda *_args, **_kwargs: [0, 1]
    assert manager._check_rate_limit_distributed_sliding_window(
        key_id="id",
        per_minute_limit=1,
        now=10.0,
    ) == (False, 1)

    redis_client.eval = lambda *_args, **_kwargs: "bad"
    with pytest.raises(RuntimeError, match="Invalid Redis sliding-window result"):
        manager._check_rate_limit_distributed_sliding_window(
            key_id="id",
            per_minute_limit=1,
            now=10.0,
        )


def test_get_redis_client_uses_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = object()
    manager = _build_manager(redis_client=None)
    monkeypatch.setattr(api_key_manager_module.settings, "REDIS_URL", "redis://example")

    def from_url(*_args: object, **_kwargs: object) -> object:
        return fake_client

    monkeypatch.setattr(api_key_manager_module.redis, "from_url", from_url)

    assert manager._get_redis_client() is fake_client
    assert manager._get_redis_client() is fake_client


def test_add_key_rejects_blank_and_returns_existing_for_duplicates() -> None:
    manager = _build_manager()
    with pytest.raises(ValueError, match="API key cannot be blank"):
        manager._add_key(raw_key="   ", name="bad", source="runtime", rate_limit_per_minute=1)

    first = manager._add_key(
        raw_key="duplicate-key",
        name="first",
        source="runtime",
        rate_limit_per_minute=1,
    )
    duplicate = manager._add_key(
        raw_key="duplicate-key",
        name="second",
        source="runtime",
        rate_limit_per_minute=5,
    )
    first.is_active = False
    replacement = manager._add_key(
        raw_key="duplicate-key",
        name="replacement",
        source="runtime",
        rate_limit_per_minute=2,
    )

    assert duplicate is first
    assert replacement is not first


def test_add_record_preserves_existing_instance() -> None:
    manager = _build_manager()
    record = APIKeyRecord(
        id="id-1",
        name="name",
        prefix="prefix",
        key_hash="hash",
        hash_version="sha256-v1",
        is_active=True,
        rate_limit_per_minute=1,
        created_at=datetime.now(tz=UTC),
        last_used_at=None,
        revoked_at=None,
        source="persisted",
    )

    assert manager._add_record(record) is record
    replacement = APIKeyRecord(
        id=record.id,
        name="replacement",
        prefix=record.prefix,
        key_hash=record.key_hash,
        hash_version=record.hash_version,
        is_active=record.is_active,
        rate_limit_per_minute=record.rate_limit_per_minute,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        source=record.source,
    )
    assert manager._add_record(replacement) is record


def test_load_persisted_keys_skips_invalid_rows(tmp_path: Path) -> None:
    persist_path = tmp_path / "api_keys.json"
    persist_path.write_text(
        json.dumps(
            [
                "bad-row",
                {"id": "missing-hash"},
                {"id": "bad-rate", "key_hash": "hash", "rate_limit_per_minute": "NaN"},
                {
                    "id": "good",
                    "name": "good",
                    "prefix": "prefix123",
                    "key_hash": "abc123",
                    "rate_limit_per_minute": 0,
                    "created_at": "2026-03-08T12:00:00",
                    "last_used_at": "2026-03-08T12:01:00+00:00",
                    "revoked_at": "bad-date",
                    "source": "runtime",
                },
            ]
        ),
        encoding="utf-8",
    )

    manager = _build_manager(persist_path=str(persist_path))

    records = manager.list_keys()
    assert len(records) == 1
    assert records[0].id == "good"
    assert records[0].rate_limit_per_minute == 1
    assert records[0].prefix == "prefix12"


def test_load_persisted_keys_ignores_missing_or_invalid_payload(tmp_path: Path) -> None:
    missing = _build_manager(persist_path=str(tmp_path / "missing.json"))
    assert missing.list_keys() == []

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    assert _build_manager(persist_path=str(invalid_json)).list_keys() == []

    invalid_list = tmp_path / "invalid-list.json"
    invalid_list.write_text(json.dumps({"not": "a-list"}), encoding="utf-8")
    assert _build_manager(persist_path=str(invalid_list)).list_keys() == []


def test_save_persisted_keys_ignores_env_records(tmp_path: Path) -> None:
    persist_path = tmp_path / "keys.json"
    manager = _build_manager(persist_path=str(persist_path))
    runtime_record, _raw = manager.create_key(name="runtime")
    env_record = APIKeyRecord(
        id="env-id",
        name="env",
        prefix="env",
        key_hash="hash",
        hash_version="sha256-v1",
        is_active=True,
        rate_limit_per_minute=1,
        created_at=datetime.now(tz=UTC),
        last_used_at=None,
        revoked_at=None,
        source="env",
    )
    manager._records_by_id[env_record.id] = env_record

    manager._save_persisted_keys()

    payload = json.loads(persist_path.read_text(encoding="utf-8"))
    assert [row["id"] for row in payload] == [runtime_record.id]


@pytest.mark.parametrize(
    ("value", "expected_none"),
    [
        (None, True),
        ("not-a-date", True),
        (123, True),
    ],
)
def test_parse_datetime_handles_invalid_values(value: object, expected_none: bool) -> None:
    parsed = APIKeyManager._parse_datetime(value)
    assert (parsed is None) is expected_none


def test_parse_datetime_normalizes_strings_and_datetimes() -> None:
    aware = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    naive_str = "2026-03-08T12:00:00"
    aware_str = "2026-03-08T12:00:00+00:00"

    assert APIKeyManager._parse_datetime(aware) is aware
    assert APIKeyManager._parse_datetime(naive_str) == aware
    assert APIKeyManager._parse_datetime(aware_str) == aware


def test_hash_version_helpers_and_hash_roundtrip() -> None:
    raw_key = "geo_test_key"
    hashed = APIKeyManager._hash_key(raw_key)
    sha_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    assert APIKeyManager._coerce_hash_version(" SCRYPT-V1 ", key_hash=hashed) == "scrypt-v1"
    assert APIKeyManager._coerce_hash_version(None, key_hash=hashed) == "scrypt-v1"
    assert APIKeyManager._coerce_hash_version(None, key_hash=sha_hash) == "sha256-v1"
    assert APIKeyManager._is_scrypt_hash(hashed) is True
    assert APIKeyManager._verify_key_hash(raw_key, hashed) is True
    assert APIKeyManager._verify_key_hash(raw_key, sha_hash) is True
    assert APIKeyManager._verify_key_hash("wrong", sha_hash) is False


def test_hash_version_falls_back_for_unknown_value() -> None:
    raw_key = "geo_test_key"
    hashed = APIKeyManager._hash_key(raw_key)

    assert APIKeyManager._coerce_hash_version("unknown", key_hash=hashed) == "scrypt-v1"


def test_verify_key_hash_rejects_malformed_scrypt_payloads() -> None:
    raw_key = "geo_test_key"
    malformed_parts = "scrypt-v1$1$2$3$only-five-parts"
    digest = urlsafe_b64encode(b"digest").decode("ascii")
    salt = urlsafe_b64encode(b"salt").decode("ascii")
    malformed_numbers = f"scrypt-v1$bad$2$3${salt}${digest}"

    assert APIKeyManager._verify_key_hash(raw_key, malformed_parts) is False
    assert APIKeyManager._verify_key_hash(raw_key, malformed_numbers) is False


def test_memory_fixed_window_helper_blocks_when_count_reaches_limit() -> None:
    manager = _build_manager(rate_limit_backend="memory")
    manager._fixed_window_counts["key"] = (0, 1)

    assert manager._check_rate_limit_memory_fixed_window(
        key_id="key",
        per_minute_limit=1,
        now=1.0,
    ) == (False, 59)


def test_memory_sliding_window_helper_discards_stale_requests() -> None:
    manager = _build_manager(rate_limit_backend="memory")
    manager._request_windows["key"] = api_key_manager_module.deque([-61.0, 0.0])

    assert manager._check_rate_limit_memory_sliding_window(
        key_id="key",
        per_minute_limit=2,
        now=61.0,
    ) == (True, None)
    assert list(manager._request_windows["key"]) == [61.0]


def test_get_api_key_manager_uses_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    get_api_key_manager.cache_clear()
    monkeypatch.setattr(api_key_manager_module.settings, "API_AUTH_ENABLED", True)
    monkeypatch.setattr(api_key_manager_module.settings, "API_KEY", "legacy")
    monkeypatch.setattr(api_key_manager_module.settings, "API_KEYS", ["static"])
    monkeypatch.setattr(api_key_manager_module.settings, "API_RATE_LIMIT_PER_MINUTE", 7)
    monkeypatch.setattr(api_key_manager_module.settings, "API_KEYS_PERSIST_PATH", None)

    manager_one = get_api_key_manager()
    manager_two = get_api_key_manager()

    assert manager_one is manager_two
    assert len(manager_one.list_keys()) == 2
    get_api_key_manager.cache_clear()
