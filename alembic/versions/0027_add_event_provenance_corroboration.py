"""Add event-level provenance-aware corroboration fields.

Revision ID: 0027_event_provenance
Revises: 0026_split_event_state_axes
Create Date: 2026-03-20 17:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_event_provenance"
down_revision = "0026_split_event_state_axes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "independent_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="1.00",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_mode",
            sa.String(length=20),
            nullable=False,
            server_default="fallback",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "provenance_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE events
        SET independent_evidence_count = COALESCE(NULLIF(unique_source_count, 0), NULLIF(source_count, 0), 1),
            corroboration_score = COALESCE(NULLIF(unique_source_count, 0), NULLIF(source_count, 0), 1),
            corroboration_mode = 'fallback',
            provenance_summary = jsonb_build_object(
                'method', 'fallback',
                'reason', 'migration_backfill',
                'raw_source_count', COALESCE(source_count, 0),
                'unique_source_count', COALESCE(unique_source_count, 0),
                'independent_evidence_count', COALESCE(NULLIF(unique_source_count, 0), NULLIF(source_count, 0), 1),
                'weighted_corroboration_score', COALESCE(NULLIF(unique_source_count, 0), NULLIF(source_count, 0), 1),
                'source_family_count', 0,
                'syndication_group_count', 0,
                'near_duplicate_group_count', 0,
                'groups', '[]'::jsonb
            )
        """
    )
    op.alter_column("events", "independent_evidence_count", server_default=None)
    op.alter_column("events", "corroboration_score", server_default=None)
    op.alter_column("events", "corroboration_mode", server_default=None)
    op.alter_column("events", "provenance_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("events", "provenance_summary")
    op.drop_column("events", "corroboration_mode")
    op.drop_column("events", "corroboration_score")
    op.drop_column("events", "independent_evidence_count")
