from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text

from src.storage.database import async_session_maker


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


async def _truncate_public_tables() -> None:
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
