from __future__ import annotations

import pytest

import src.core.migration_parity as migration_parity

pytestmark = pytest.mark.unit


class _FakeScalarResult:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def scalars(self) -> _FakeScalarResult:
        return self

    def all(self) -> list[str]:
        return self._values


class _FakeSession:
    def __init__(
        self, result: _FakeScalarResult | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error

    async def execute(self, _query):
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.asyncio
async def test_check_migration_parity_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(result=_FakeScalarResult(["abc123"]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result["status"] == "healthy"
    assert result["expected_head"] == "abc123"
    assert result["current_revision"] == "abc123"


@pytest.mark.asyncio
async def test_check_migration_parity_detects_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(result=_FakeScalarResult(["def456"]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result["status"] == "unhealthy"
    assert result["expected_head"] == "abc123"
    assert result["current_revision"] == "def456"


@pytest.mark.asyncio
async def test_check_migration_parity_handles_multiple_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migration_parity, "get_expected_migration_heads", lambda: ("abc123", "def456")
    )
    session = _FakeSession(result=_FakeScalarResult(["abc123"]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result["status"] == "unhealthy"
    assert "Multiple Alembic heads" in result["message"]


@pytest.mark.asyncio
async def test_check_migration_parity_handles_query_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(error=RuntimeError("db unavailable"))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result["status"] == "unhealthy"
    assert "Could not query alembic_version" in result["message"]
