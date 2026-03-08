from __future__ import annotations

from types import SimpleNamespace

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


def test_create_engine_uses_pooling_in_staging(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "engine"

    monkeypatch.setattr(database_module.settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(database_module.settings, "DATABASE_URL", "postgresql+asyncpg://db")
    monkeypatch.setattr(database_module.settings, "SQL_ECHO", False)
    monkeypatch.setattr(database_module.settings, "DATABASE_POOL_SIZE", 9)
    monkeypatch.setattr(database_module.settings, "DATABASE_MAX_OVERFLOW", 4)
    monkeypatch.setattr(database_module.settings, "DATABASE_POOL_TIMEOUT_SECONDS", 25)
    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)

    result = database_module.create_engine()

    assert result == "engine"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["pool_size"] == 9
    assert kwargs["max_overflow"] == 4
    assert kwargs["pool_timeout"] == 25
    assert "poolclass" not in kwargs


class _SessionContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_get_session_commits_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(database_module, "async_session_maker", lambda: _SessionContext(session))

    generator = database_module.get_session()
    yielded = await anext(generator)

    assert yielded is session

    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    assert session.commit_calls == 1
    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(database_module, "async_session_maker", lambda: _SessionContext(session))

    generator = database_module.get_session()
    yielded = await anext(generator)

    assert yielded is session

    with pytest.raises(RuntimeError, match="boom"):
        await generator.athrow(RuntimeError("boom"))

    assert session.commit_calls == 0
    assert session.rollback_calls == 1


class _BeginContext:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def run_sync(self, fn) -> None:
        self.calls.append(fn)


@pytest.mark.asyncio
async def test_init_db_runs_create_all(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()
    fake_base = SimpleNamespace(metadata=SimpleNamespace(create_all="create-all"))

    monkeypatch.setattr(
        database_module, "engine", SimpleNamespace(begin=lambda: _BeginContext(conn))
    )
    monkeypatch.setattr("src.storage.models.Base", fake_base)

    await database_module.init_db()

    assert conn.calls == ["create-all"]


@pytest.mark.asyncio
async def test_drop_db_runs_drop_all(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()
    fake_base = SimpleNamespace(metadata=SimpleNamespace(drop_all="drop-all"))

    monkeypatch.setattr(
        database_module, "engine", SimpleNamespace(begin=lambda: _BeginContext(conn))
    )
    monkeypatch.setattr("src.storage.models.Base", fake_base)

    await database_module.drop_db()

    assert conn.calls == ["drop-all"]
