"""Add persisted event-level summary separate from canonical item summary.

Revision ID: 0032_add_event_summary_field
Revises: 0031_privileged_write_audits
Create Date: 2026-03-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0032_add_event_summary_field"
down_revision = "0031_privileged_write_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("event_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "event_summary")
