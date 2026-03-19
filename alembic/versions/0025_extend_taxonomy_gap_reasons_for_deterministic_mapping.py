"""extend taxonomy gap reasons for deterministic mapping

Revision ID: 0025_extend_taxonomy_gap_reasons
Revises: 0024_trend_restatement_ledger
Create Date: 2026-03-19 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0025_extend_taxonomy_gap_reasons"
down_revision = "0024_trend_restatement_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE taxonomy_gap_reason ADD VALUE IF NOT EXISTS 'ambiguous_mapping'")
    op.execute("ALTER TYPE taxonomy_gap_reason ADD VALUE IF NOT EXISTS 'no_matching_indicator'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE taxonomy_gaps
        SET reason = 'unknown_signal_type'
        WHERE reason IN ('ambiguous_mapping', 'no_matching_indicator')
        """
    )
    op.execute("ALTER TYPE taxonomy_gap_reason RENAME TO taxonomy_gap_reason_old")
    taxonomy_gap_reason = postgresql.ENUM(
        "unknown_trend_id",
        "unknown_signal_type",
        name="taxonomy_gap_reason",
    )
    taxonomy_gap_reason.create(op.get_bind(), checkfirst=False)
    op.execute(
        """
        ALTER TABLE taxonomy_gaps
        ALTER COLUMN reason TYPE taxonomy_gap_reason
        USING reason::text::taxonomy_gap_reason
        """
    )
    op.execute("DROP TYPE taxonomy_gap_reason_old")
