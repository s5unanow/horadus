from __future__ import annotations

import sys
import types

import pytest

import src.core.migration_parity as migration_parity

pytestmark = pytest.mark.unit


def test_get_expected_migration_heads_reads_alembic_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_instances: list[object] = []

    class _FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path
            self.options: dict[str, str] = {}
            config_instances.append(self)

        def set_main_option(self, key: str, value: str) -> None:
            self.options[key] = value

    fake_script_directory = types.SimpleNamespace(
        from_config=lambda _config: types.SimpleNamespace(get_heads=lambda: ["b", "a"])
    )

    monkeypatch.setitem(sys.modules, "alembic", types.ModuleType("alembic"))
    monkeypatch.setitem(
        sys.modules,
        "alembic.config",
        types.SimpleNamespace(Config=_FakeConfig),
    )
    monkeypatch.setitem(
        sys.modules,
        "alembic.script",
        types.SimpleNamespace(ScriptDirectory=fake_script_directory),
    )
    migration_parity.get_expected_migration_heads.cache_clear()

    heads = migration_parity.get_expected_migration_heads()

    assert heads == ("a", "b")
    assert config_instances[0].path == str(migration_parity.ALEMBIC_INI_PATH)
    assert config_instances[0].options["script_location"] == str(
        migration_parity.ALEMBIC_SCRIPT_PATH
    )

    migration_parity.get_expected_migration_heads.cache_clear()


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
async def test_check_migration_parity_handles_missing_head_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ())
    session = _FakeSession(result=_FakeScalarResult(["abc123"]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result == {
        "status": "unhealthy",
        "message": "No Alembic head revisions found",
    }


@pytest.mark.asyncio
async def test_check_migration_parity_handles_query_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(error=RuntimeError("db unavailable"))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result["status"] == "unhealthy"
    assert "Could not query alembic_version" in result["message"]


@pytest.mark.asyncio
async def test_check_migration_parity_handles_missing_database_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(result=_FakeScalarResult([]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result == {
        "status": "unhealthy",
        "message": "No database migration revision found in alembic_version",
        "expected_head": "abc123",
    }


@pytest.mark.asyncio
async def test_check_migration_parity_handles_multiple_database_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migration_parity, "get_expected_migration_heads", lambda: ("abc123",))
    session = _FakeSession(result=_FakeScalarResult(["abc123", "def456"]))

    result = await migration_parity.check_migration_parity(session)  # type: ignore[arg-type]

    assert result == {
        "status": "unhealthy",
        "message": "Multiple current DB revisions found in alembic_version",
        "expected_head": "abc123",
        "current_revisions": ["abc123", "def456"],
    }
