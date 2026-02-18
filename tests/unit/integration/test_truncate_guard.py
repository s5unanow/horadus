from __future__ import annotations

import pytest

import tests.integration.conftest as integration_conftest

pytestmark = pytest.mark.unit


def _set_target(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str,
    allow_non_test_db: bool = False,
    allow_remote: bool = False,
) -> None:
    monkeypatch.setattr(integration_conftest.settings, "DATABASE_URL_SYNC", url)
    monkeypatch.setattr(integration_conftest.settings, "DATABASE_URL", url)
    monkeypatch.setattr(
        integration_conftest.settings,
        "INTEGRATION_DB_TRUNCATE_ALLOWED",
        allow_non_test_db,
    )
    monkeypatch.setattr(
        integration_conftest.settings,
        "INTEGRATION_DB_TRUNCATE_ALLOW_REMOTE",
        allow_remote,
    )


def test_truncate_guard_allows_local_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_target(
        monkeypatch,
        url="postgresql+asyncpg://postgres:postgres@localhost:5432/geoint_test",  # pragma: allowlist secret
    )

    target = integration_conftest._assert_safe_integration_truncate_target()

    assert target.database == "geoint_test"
    assert target.host == "localhost"


def test_truncate_guard_rejects_non_test_database_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_target(
        monkeypatch,
        url="postgresql+asyncpg://postgres:postgres@localhost:5432/geoint",  # pragma: allowlist secret
    )

    with pytest.raises(RuntimeError, match="Refusing integration DB truncation for non-test"):
        integration_conftest._assert_safe_integration_truncate_target()


def test_truncate_guard_allows_non_test_database_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_target(
        monkeypatch,
        url="postgresql+asyncpg://postgres:postgres@localhost:5432/geoint",  # pragma: allowlist secret
        allow_non_test_db=True,
    )

    target = integration_conftest._assert_safe_integration_truncate_target()
    assert target.database == "geoint"


def test_truncate_guard_rejects_remote_host_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_target(
        monkeypatch,
        url="postgresql+asyncpg://postgres:postgres@db.internal:5432/geoint_test",  # pragma: allowlist secret
    )

    with pytest.raises(RuntimeError, match="Refusing integration DB truncation for non-local"):
        integration_conftest._assert_safe_integration_truncate_target()


def test_truncate_guard_allows_remote_host_with_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_target(
        monkeypatch,
        url="postgresql+asyncpg://postgres:postgres@db.internal:5432/geoint_test",  # pragma: allowlist secret
        allow_remote=True,
    )

    target = integration_conftest._assert_safe_integration_truncate_target()
    assert target.host == "db.internal"
