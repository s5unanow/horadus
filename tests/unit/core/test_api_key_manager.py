from __future__ import annotations

import pytest

from src.core.api_key_manager import APIKeyManager

pytestmark = pytest.mark.unit


def _build_manager(*, auth_enabled: bool = True, rate_limit_per_minute: int = 5) -> APIKeyManager:
    return APIKeyManager(
        auth_enabled=auth_enabled,
        legacy_api_key=None,
        static_api_keys=[],
        default_rate_limit_per_minute=rate_limit_per_minute,
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
