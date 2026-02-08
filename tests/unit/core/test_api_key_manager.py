from __future__ import annotations

from pathlib import Path

import pytest

from src.core.api_key_manager import APIKeyManager

pytestmark = pytest.mark.unit


def _build_manager(
    *,
    auth_enabled: bool = True,
    rate_limit_per_minute: int = 5,
    persist_path: str | None = None,
) -> APIKeyManager:
    return APIKeyManager(
        auth_enabled=auth_enabled,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=rate_limit_per_minute,
        persist_path=persist_path,
    )


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


def test_runtime_keys_persist_and_reload(tmp_path: Path) -> None:
    persist_path = str(tmp_path / "api_keys.json")
    manager = _build_manager(persist_path=persist_path)
    _record, raw_key = manager.create_key(name="persisted")

    reloaded_manager = _build_manager(persist_path=persist_path)

    assert reloaded_manager.authenticate(raw_key) is not None


def test_rotate_key_revokes_old_and_returns_new() -> None:
    manager = _build_manager()
    record, raw_key = manager.create_key(name="rotate-me")

    rotated = manager.rotate_key(record.id)

    assert rotated is not None
    new_record, new_raw_key = rotated
    assert new_record.id != record.id
    assert manager.authenticate(raw_key) is None
    assert manager.authenticate(new_raw_key) is not None
