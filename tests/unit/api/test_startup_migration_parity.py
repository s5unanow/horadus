from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.api.main as main_module

pytestmark = pytest.mark.unit


class _FakeSession:
    async def execute(self, _query):
        return None


class _FakeSessionContext:
    async def __aenter__(self) -> _FakeSession:
        return _FakeSession()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _fake_session_maker() -> _FakeSessionContext:
    return _FakeSessionContext()


@pytest.mark.asyncio
async def test_lifespan_allows_unhealthy_migration_when_not_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(_session):
        return {"status": "unhealthy", "message": "Database schema revision drift detected"}

    dispose_mock = AsyncMock()

    monkeypatch.setattr(main_module, "async_session_maker", _fake_session_maker)
    monkeypatch.setattr(main_module, "check_migration_parity", fake_check)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_STRICT_STARTUP", False)
    monkeypatch.setattr(main_module, "engine", SimpleNamespace(dispose=dispose_mock))

    async with main_module.lifespan(main_module.app):
        pass

    dispose_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_fails_startup_when_migration_unhealthy_and_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(_session):
        return {"status": "unhealthy", "message": "Database schema revision drift detected"}

    monkeypatch.setattr(main_module, "async_session_maker", _fake_session_maker)
    monkeypatch.setattr(main_module, "check_migration_parity", fake_check)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_CHECK_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "MIGRATION_PARITY_STRICT_STARTUP", True)

    with pytest.raises(RuntimeError, match="Migration parity check failed"):
        async with main_module.lifespan(main_module.app):
            pass
