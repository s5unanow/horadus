"""Allow multiple invalidated evidence versions per trend/event/signal key.

Revision ID: 0022_evidence_active_unique
Revises: 0021_runtime_trend_id_uniqueness
Create Date: 2026-03-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0022_evidence_active_unique"
down_revision = "0021_runtime_trend_id_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_trend_event_signal", "trend_evidence", type_="unique")
    op.create_index(
        "uq_trend_event_signal_active",
        "trend_evidence",
        ["trend_id", "event_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_trend_event_signal_active", table_name="trend_evidence")
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY trend_id, event_id, signal_type
                        ORDER BY is_invalidated ASC, created_at DESC, id DESC
                    ) AS row_num
                FROM trend_evidence
            )
            DELETE FROM trend_evidence
            USING ranked
            WHERE trend_evidence.id = ranked.id
              AND ranked.row_num > 1
            """
        )
    )
    op.create_unique_constraint(
        "uq_trend_event_signal",
        "trend_evidence",
        ["trend_id", "event_id", "signal_type"],
    )
