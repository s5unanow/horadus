"""Enforce one-event-per-item invariant on event_items.

Revision ID: 0016_event_item_unique_item
Revises: 0015_embed_input_guardrails
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_event_item_unique_item"
down_revision = "0015_embed_input_guardrails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            """
            SELECT
                item_id::text AS item_id,
                COUNT(*) AS link_count,
                ARRAY_AGG(event_id::text ORDER BY added_at ASC) AS event_ids
            FROM event_items
            GROUP BY item_id
            HAVING COUNT(*) > 1
            ORDER BY link_count DESC, item_id
            LIMIT 10
            """
        )
    ).mappings()
    duplicate_rows = list(duplicates)
    if duplicate_rows:
        preview = "; ".join(
            f"item_id={row['item_id']} links={row['link_count']} events={row['event_ids']}"
            for row in duplicate_rows
        )
        msg = (
            "Cannot enforce uq_event_items_item_id: duplicate event-item links detected. "
            f"Resolve duplicates first. Sample: {preview}"
        )
        raise RuntimeError(msg)

    op.create_unique_constraint(
        "uq_event_items_item_id",
        "event_items",
        ["item_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_event_items_item_id", "event_items", type_="unique")
