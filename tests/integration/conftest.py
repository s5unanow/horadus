from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

from src.core.config import settings
from src.storage.database import async_session_maker

_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True, slots=True)
class IntegrationTruncateTarget:
    rendered_url: str
    database: str | None
    host: str | None


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


def _is_explicit_test_database(database_name: str | None) -> bool:
    if not database_name:
        return False
    normalized = database_name.strip().lower()
    return normalized.endswith("_test") or normalized.startswith("test_") or normalized == "test"


def _resolve_integration_truncate_target() -> IntegrationTruncateTarget:
    resolved_url = settings.DATABASE_URL_SYNC.strip() or settings.DATABASE_URL.strip()
    parsed = make_url(resolved_url)
    return IntegrationTruncateTarget(
        rendered_url=parsed.render_as_string(hide_password=True),
        database=parsed.database,
        host=parsed.host,
    )


def _assert_safe_integration_truncate_target() -> IntegrationTruncateTarget:
    target = _resolve_integration_truncate_target()
    is_test_database = _is_explicit_test_database(target.database)
    if not is_test_database and not settings.INTEGRATION_DB_TRUNCATE_ALLOWED:
        msg = (
            "Refusing integration DB truncation for non-test database target. "
            f"Resolved target={target.rendered_url} (database={target.database!r}, host={target.host!r}). "
            "Use a test database name (for example *_test) or set "
            "INTEGRATION_DB_TRUNCATE_ALLOWED=true to override."
        )
        raise RuntimeError(msg)

    normalized_host = (target.host or "").strip().lower()
    is_local_host = normalized_host in _LOCAL_DB_HOSTS or normalized_host == ""
    if not is_local_host and not settings.INTEGRATION_DB_TRUNCATE_ALLOW_REMOTE:
        msg = (
            "Refusing integration DB truncation for non-local host target. "
            f"Resolved target={target.rendered_url} (database={target.database!r}, host={target.host!r}). "
            "Use localhost/127.0.0.1/::1 or set INTEGRATION_DB_TRUNCATE_ALLOW_REMOTE=true to override."
        )
        raise RuntimeError(msg)

    return target


async def _truncate_public_tables() -> None:
    _assert_safe_integration_truncate_target()
    async with async_session_maker() as session:
        table_names = (
            await session.scalars(
                text(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename != 'alembic_version'
                    """
                )
            )
        ).all()

        if table_names:
            quoted_table_names = ", ".join(_quote_identifier(name) for name in table_names)
            await session.execute(
                text(f"TRUNCATE TABLE {quoted_table_names} RESTART IDENTITY CASCADE")
            )

        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def reset_integration_database() -> AsyncIterator[None]:
    await _truncate_public_tables()
    yield
    await _truncate_public_tables()
