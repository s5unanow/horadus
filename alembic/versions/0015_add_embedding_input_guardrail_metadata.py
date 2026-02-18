"""Add embedding input guardrail metadata columns.

Revision ID: 0015_embed_input_guardrails
Revises: 0014_evidence_invalidation
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_embed_input_guardrails"
down_revision = "0014_evidence_invalidation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_items", sa.Column("embedding_input_tokens", sa.Integer(), nullable=True))
    op.add_column("raw_items", sa.Column("embedding_retained_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "raw_items",
        sa.Column(
            "embedding_was_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "raw_items",
        sa.Column("embedding_truncation_strategy", sa.String(length=20), nullable=True),
    )

    op.add_column("events", sa.Column("embedding_input_tokens", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("embedding_retained_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "embedding_was_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "events",
        sa.Column("embedding_truncation_strategy", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "embedding_truncation_strategy")
    op.drop_column("events", "embedding_was_truncated")
    op.drop_column("events", "embedding_retained_tokens")
    op.drop_column("events", "embedding_input_tokens")

    op.drop_column("raw_items", "embedding_truncation_strategy")
    op.drop_column("raw_items", "embedding_was_truncated")
    op.drop_column("raw_items", "embedding_retained_tokens")
    op.drop_column("raw_items", "embedding_input_tokens")
