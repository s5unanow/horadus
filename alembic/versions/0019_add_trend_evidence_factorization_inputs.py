"""Persist trend-evidence factorization inputs for auditability.

Revision ID: 0019_trend_evidence_factorization
Revises: 0018_dimension_check_constraints
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0019_trend_evidence_factorization"
down_revision = "0018_dimension_check_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trend_evidence",
        sa.Column("base_weight", sa.Numeric(10, 6), nullable=True),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("direction_multiplier", sa.Numeric(3, 1), nullable=True),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("trend_definition_hash", sa.String(length=64), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE trend_evidence
            SET direction_multiplier = CASE
                WHEN delta_log_odds > 0 THEN 1.0
                WHEN delta_log_odds < 0 THEN -1.0
                ELSE 0.0
            END
            WHERE direction_multiplier IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("trend_evidence", "trend_definition_hash")
    op.drop_column("trend_evidence", "direction_multiplier")
    op.drop_column("trend_evidence", "base_weight")
