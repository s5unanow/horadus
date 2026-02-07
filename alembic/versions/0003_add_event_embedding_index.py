"""Add ivfflat index for events embedding.

Revision ID: 0003_add_event_embedding_index
Revises: 0002_add_raw_item_embedding
Create Date: 2026-02-07
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_event_embedding_index"
down_revision = "0002_add_raw_item_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_embedding
        ON events
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_embedding")
