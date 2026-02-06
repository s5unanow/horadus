"""Add embedding column for raw items.

Revision ID: 0002_add_raw_item_embedding
Revises: 0001_initial_schema
Create Date: 2026-02-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0002_add_raw_item_embedding"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_items", sa.Column("embedding", Vector(1536), nullable=True))
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_items_embedding
        ON raw_items
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_raw_items_embedding")
    op.drop_column("raw_items", "embedding")
