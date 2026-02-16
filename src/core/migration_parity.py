"""
Migration parity checks for runtime health/startup safeguards.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = PROJECT_ROOT / "alembic"


@lru_cache(maxsize=1)
def get_expected_migration_heads() -> tuple[str, ...]:
    """Return Alembic head revision identifiers for this repository."""
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    script = ScriptDirectory.from_config(config)
    return tuple(sorted(script.get_heads()))


async def check_migration_parity(session: AsyncSession) -> dict[str, Any]:
    """
    Compare database revision state with Alembic head revisions.

    Returns a structured payload compatible with health checks.
    """
    try:
        heads = get_expected_migration_heads()
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "status": "unhealthy",
            "message": f"Could not determine Alembic head revision: {exc}",
        }

    if not heads:
        return {
            "status": "unhealthy",
            "message": "No Alembic head revisions found",
        }

    if len(heads) > 1:
        return {
            "status": "unhealthy",
            "message": "Multiple Alembic heads detected",
            "expected_heads": list(heads),
        }

    expected_head = heads[0]

    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        current_revisions = tuple(str(value) for value in result.scalars().all() if value)
    except Exception as exc:
        return {
            "status": "unhealthy",
            "message": f"Could not query alembic_version table: {exc}",
            "expected_head": expected_head,
        }

    if not current_revisions:
        return {
            "status": "unhealthy",
            "message": "No database migration revision found in alembic_version",
            "expected_head": expected_head,
        }

    if len(current_revisions) > 1:
        return {
            "status": "unhealthy",
            "message": "Multiple current DB revisions found in alembic_version",
            "expected_head": expected_head,
            "current_revisions": list(current_revisions),
        }

    current_revision = current_revisions[0]
    if current_revision != expected_head:
        return {
            "status": "unhealthy",
            "message": "Database schema revision drift detected",
            "expected_head": expected_head,
            "current_revision": current_revision,
        }

    return {
        "status": "healthy",
        "expected_head": expected_head,
        "current_revision": current_revision,
    }
