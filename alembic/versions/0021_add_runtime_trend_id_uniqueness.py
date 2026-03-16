"""Persist and enforce unique runtime trend identifiers for trends.

Revision ID: 0021_runtime_trend_id_uniqueness
Revises: 0020_add_llm_replay_queue
Create Date: 2026-03-16
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_runtime_trend_id_uniqueness"
down_revision = "0020_llm_replay_queue"
branch_labels = None
depends_on = None
_MAX_RUNTIME_TREND_ID_LENGTH = 255


_TRENDS_TABLE = sa.table(
    "trends",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String(length=255)),
    sa.column("definition", postgresql.JSONB(astext_type=sa.Text())),
    sa.column("runtime_trend_id", sa.String(length=255)),
)


def _slugify_name(name: str) -> str:
    normalized = "-".join(name.lower().strip().split())
    return normalized.replace("/", "-").replace("_", "-")


def _resolve_runtime_trend_id(*, name: str, definition: Any) -> str:
    runtime_trend_id: str | None = None
    if isinstance(definition, dict):
        raw_id = definition.get("id")
        if isinstance(raw_id, str):
            normalized_id = raw_id.strip()
            if normalized_id:
                runtime_trend_id = normalized_id

    if runtime_trend_id is None:
        runtime_trend_id = _slugify_name(name)
        if not runtime_trend_id:
            msg = "Cannot backfill runtime_trend_id for trend with blank name and blank definition.id"
            raise RuntimeError(msg)

    if len(runtime_trend_id) > _MAX_RUNTIME_TREND_ID_LENGTH:
        msg = (
            "Cannot backfill runtime_trend_id longer than "
            f"{_MAX_RUNTIME_TREND_ID_LENGTH} characters"
        )
        raise RuntimeError(msg)
    return runtime_trend_id


def upgrade() -> None:
    op.add_column("trends", sa.Column("runtime_trend_id", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    rows = list(
        conn.execute(
            sa.text(
                """
                SELECT
                    id,
                    name,
                    definition
                FROM trends
                ORDER BY created_at ASC NULLS LAST, name ASC, id ASC
                """
            )
        ).mappings()
    )

    seen_runtime_ids: dict[str, dict[str, Any]] = {}
    duplicate_rows: list[tuple[str, str, str, str]] = []
    updates: list[dict[str, Any]] = []
    for row in rows:
        trend_id = str(row["id"])
        trend_name = row["name"] or ""
        definition = row["definition"] if isinstance(row["definition"], dict) else {}
        runtime_trend_id = _resolve_runtime_trend_id(name=trend_name, definition=definition)

        existing = seen_runtime_ids.get(runtime_trend_id)
        if existing is not None:
            duplicate_rows.append(
                (
                    runtime_trend_id,
                    existing["id"],
                    existing["name"],
                    trend_id,
                )
            )
            continue
        seen_runtime_ids[runtime_trend_id] = {"id": trend_id, "name": trend_name}

        updated_definition = dict(definition)
        updated_definition["id"] = runtime_trend_id
        updates.append(
            {
                "trend_id": row["id"],
                "runtime_trend_id": runtime_trend_id,
                "definition": updated_definition,
            }
        )

    if duplicate_rows:
        preview = "; ".join(
            (
                "runtime_trend_id="
                f"{runtime_trend_id} existing={existing_id}:{existing_name} duplicate={duplicate_id}"
            )
            for runtime_trend_id, existing_id, existing_name, duplicate_id in duplicate_rows[:10]
        )
        msg = (
            "Cannot enforce uq_trends_runtime_trend_id: duplicate runtime trend identifiers "
            f"detected. Resolve duplicates first. Sample: {preview}"
        )
        raise RuntimeError(msg)

    if updates:
        conn.execute(
            _TRENDS_TABLE.update()
            .where(_TRENDS_TABLE.c.id == sa.bindparam("trend_id"))
            .values(
                runtime_trend_id=sa.bindparam("runtime_trend_id"),
                definition=sa.bindparam("definition"),
            ),
            updates,
        )

    op.alter_column(
        "trends",
        "runtime_trend_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_trends_runtime_trend_id",
        "trends",
        ["runtime_trend_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_trends_runtime_trend_id", "trends", type_="unique")
    op.drop_column("trends", "runtime_trend_id")
