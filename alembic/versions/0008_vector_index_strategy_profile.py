"""Tune default vector index profile for current dataset regime.

Revision ID: 0008_vector_index_strategy_profile
Revises: 0007_evidence_decay_fields
Create Date: 2026-02-12
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_vector_index_strategy_profile"
down_revision = "0007_evidence_decay_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_raw_items_embedding")
    op.execute("DROP INDEX IF EXISTS idx_events_embedding")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_items_embedding
        ON raw_items
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 64)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_embedding
        ON events
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_raw_items_embedding")
    op.execute("DROP INDEX IF EXISTS idx_events_embedding")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_items_embedding
        ON raw_items
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_embedding
        ON events
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
