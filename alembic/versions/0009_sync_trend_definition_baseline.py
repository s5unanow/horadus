"""Backfill trend definition baseline_probability from canonical baseline_log_odds.

Revision ID: 0009_trend_baseline_sync
Revises: 0008_vector_index_profile
Create Date: 2026-02-16
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_trend_baseline_sync"
down_revision = "0008_vector_index_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE trends
        SET definition =
            CASE
                WHEN jsonb_typeof(definition) = 'object' THEN jsonb_set(
                    definition,
                    '{baseline_probability}',
                    to_jsonb(
                        round(
                            (1.0 / (1.0 + exp(-baseline_log_odds::double precision)))::numeric,
                            6
                        )::double precision
                    ),
                    true
                )
                ELSE jsonb_build_object(
                    'baseline_probability',
                    round(
                        (1.0 / (1.0 + exp(-baseline_log_odds::double precision)))::numeric,
                        6
                    )::double precision
                )
            END
        """
    )


def downgrade() -> None:
    # Data synchronization only; keep values unchanged on downgrade.
    pass
