from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.api.routes._privileged_write_contract as write_contract_module
import src.storage.database as database_module
from src.storage.base import Base

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
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_error = commit_error
        self.info: dict[str, object] = {}

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

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


@pytest.mark.asyncio
async def test_get_session_finalizes_deferred_privileged_write_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    finalize_pending_audits = AsyncMock()
    monkeypatch.setattr(database_module, "async_session_maker", lambda: _SessionContext(session))
    monkeypatch.setattr(
        database_module,
        "_finalize_pending_privileged_write_audits",
        finalize_pending_audits,
    )
    monkeypatch.setattr(
        write_contract_module,
        "_uses_independent_audit_session",
        lambda candidate: candidate is session,
    )

    generator = database_module.get_session()
    yielded = await anext(generator)
    guard = write_contract_module.PrivilegedWriteGuard(route_session=yielded, audit_id="audit-id")
    await guard.succeed(observed_revision_token="rev-1", result_links={"trend_id": "trend-1"})

    assert session.commit_calls == 0
    assert finalize_pending_audits.await_count == 0

    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    finalize_pending_audits.assert_awaited_once()
    assert finalize_pending_audits.await_args.kwargs["outcome"] == "applied"


@pytest.mark.asyncio
async def test_get_session_marks_deferred_privileged_write_rolled_back_on_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(commit_error=RuntimeError("commit failed"))
    finalize_pending_audits = AsyncMock()
    monkeypatch.setattr(database_module, "async_session_maker", lambda: _SessionContext(session))
    monkeypatch.setattr(
        database_module,
        "_finalize_pending_privileged_write_audits",
        finalize_pending_audits,
    )
    monkeypatch.setattr(
        write_contract_module,
        "_uses_independent_audit_session",
        lambda candidate: candidate is session,
    )

    generator = database_module.get_session()
    yielded = await anext(generator)
    guard = write_contract_module.PrivilegedWriteGuard(route_session=yielded, audit_id="audit-id")
    await guard.succeed(observed_revision_token="rev-1", result_links={"trend_id": "trend-1"})

    with pytest.raises(RuntimeError, match="commit failed"):
        await anext(generator)

    assert session.commit_calls == 1
    assert session.rollback_calls == 1
    finalize_pending_audits.assert_awaited_once()
    assert finalize_pending_audits.await_args.kwargs["outcome"] == "rolled_back"
    assert "commit failed" in finalize_pending_audits.await_args.kwargs["detail"]


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


class _AuditSessionContext:
    def __init__(self, audit_session: object) -> None:
        self._audit_session = audit_session

    async def __aenter__(self) -> object:
        return self._audit_session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_update_privileged_write_audit_covers_found_and_missing_records() -> None:
    record = write_contract_module.PrivilegedWriteAudit(
        id="audit-id",
        actor_key="actor",
        action="action",
        request_method="PATCH",
        request_path="/api/v1/test",
        target_type="trend",
        target_identifier="trend-1",
        idempotency_key="idem-key",
        request_fingerprint="fingerprint",
        request_intent={},
        outcome="in_progress",
    )
    audit_session = AsyncMock()
    audit_session.get.side_effect = [record, record, None]
    audit_session.flush = AsyncMock()

    await database_module._update_privileged_write_audit(
        audit_session,
        audit_id="audit-id",
        outcome="applied",
        detail="done",
        observed_revision_token="rev-1",
        result_links={"trend_id": "trend-1"},
    )
    await database_module._update_privileged_write_audit(
        audit_session,
        audit_id="audit-id",
        outcome="rolled_back",
        detail="rollback",
        observed_revision_token=None,
        result_links=None,
    )
    await database_module._update_privileged_write_audit(
        audit_session,
        audit_id="missing",
        outcome="rolled_back",
        detail="missing",
        observed_revision_token=None,
    )

    assert record.outcome == "rolled_back"
    assert record.detail == "rollback"
    assert record.observed_revision_token == "rev-1"
    assert record.result_links == {"trend_id": "trend-1"}
    assert audit_session.flush.await_count == 2


@pytest.mark.asyncio
async def test_finalize_pending_privileged_write_audits_covers_empty_and_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    audit_session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    update_privileged_write_audit = AsyncMock()
    monkeypatch.setattr(
        database_module, "_update_privileged_write_audit", update_privileged_write_audit
    )
    monkeypatch.setattr(
        database_module,
        "async_session_maker",
        lambda: _AuditSessionContext(audit_session),
    )

    await database_module._finalize_pending_privileged_write_audits(session, outcome="applied")

    session.info[database_module._PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY] = [
        SimpleNamespace(
            audit_id="audit-id",
            observed_revision_token="rev-1",
            result_links={"trend_id": "trend-1"},
            detail="done",
        ),
        SimpleNamespace(
            audit_id=None,
            observed_revision_token="ignored",
            result_links={"trend_id": "ignored"},
            detail="ignored",
        ),
    ]

    await database_module._finalize_pending_privileged_write_audits(session, outcome="applied")

    update_privileged_write_audit.assert_awaited_once()
    assert update_privileged_write_audit.await_args.kwargs["audit_id"] == "audit-id"
    assert update_privileged_write_audit.await_args.kwargs["detail"] == "done"
    assert update_privileged_write_audit.await_args.kwargs["result_links"] == {
        "trend_id": "trend-1"
    }
    audit_session.commit.assert_awaited_once()
    audit_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_pending_privileged_write_audits_rolls_back_on_update_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    session.info[database_module._PENDING_PRIVILEGED_WRITE_SUCCESSES_KEY] = [
        SimpleNamespace(
            audit_id="audit-id", observed_revision_token="rev-1", result_links=None, detail=None
        )
    ]
    audit_session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    async def _raise_update(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(database_module, "_update_privileged_write_audit", _raise_update)
    monkeypatch.setattr(
        database_module,
        "async_session_maker",
        lambda: _AuditSessionContext(audit_session),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await database_module._finalize_pending_privileged_write_audits(
            session, outcome="rolled_back"
        )

    audit_session.rollback.assert_awaited_once()
    audit_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_init_db_runs_create_all(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()

    monkeypatch.setattr(
        database_module, "engine", SimpleNamespace(begin=lambda: _BeginContext(conn))
    )
    monkeypatch.setattr(Base.metadata, "create_all", "create-all")

    await database_module.init_db()

    assert conn.calls == ["create-all"]


@pytest.mark.asyncio
async def test_drop_db_runs_drop_all(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection()

    monkeypatch.setattr(
        database_module, "engine", SimpleNamespace(begin=lambda: _BeginContext(conn))
    )
    monkeypatch.setattr(Base.metadata, "drop_all", "drop-all")

    await database_module.drop_db()

    assert conn.calls == ["drop-all"]
