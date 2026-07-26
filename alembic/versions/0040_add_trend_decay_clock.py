"""Add a decay-only clock to trend state.

Revision ID: 0040_trend_decay_clock
Revises: 0039_evidence_null_state_unique
Create Date: 2026-07-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0040_trend_decay_clock"
down_revision = "0039_evidence_null_state_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trends",
        sa.Column("last_decayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE trends
            SET last_decayed_at = updated_at
            WHERE last_decayed_at IS NULL
            """
        )
    )
    op.alter_column(
        "trends",
        "last_decayed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.drop_column("trends", "last_decayed_at")
