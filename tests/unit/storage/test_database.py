from __future__ import annotations

import pytest

import src.storage.database as database_module

pytestmark = pytest.mark.unit


def test_create_engine_sets_pool_timeout_in_production(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "engine"

    monkeypatch.setattr(database_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(database_module.settings, "DATABASE_URL", "postgresql+asyncpg://db")
    monkeypatch.setattr(database_module.settings, "SQL_ECHO", False)
    monkeypatch.setattr(database_module.settings, "DATABASE_POOL_SIZE", 7)
    monkeypatch.setattr(database_module.settings, "DATABASE_MAX_OVERFLOW", 11)
    monkeypatch.setattr(database_module.settings, "DATABASE_POOL_TIMEOUT_SECONDS", 42)
    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)

    result = database_module.create_engine()

    assert result == "engine"
    assert captured["url"] == "postgresql+asyncpg://db"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 11
    assert kwargs["pool_timeout"] == 42


def test_create_engine_uses_nullpool_in_development(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "engine"

    monkeypatch.setattr(database_module.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(database_module.settings, "DATABASE_URL", "postgresql+asyncpg://db")
    monkeypatch.setattr(database_module.settings, "SQL_ECHO", True)
    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)

    result = database_module.create_engine()

    assert result == "engine"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["poolclass"] is database_module.NullPool
    assert "pool_timeout" not in kwargs
