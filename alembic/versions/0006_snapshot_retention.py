"""Add Timescale retention/compression policies for trend snapshots.

Revision ID: 0006_snapshot_retention
Revises: 0005_add_processing_started_at
Create Date: 2026-02-12
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_snapshot_retention"
down_revision = "0005_add_processing_started_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE trend_snapshots "
        "SET (timescaledb.compress = true, timescaledb.compress_segmentby = 'trend_id');"
    )
    op.execute(
        "SELECT add_compression_policy('trend_snapshots', INTERVAL '30 days', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('trend_snapshots', INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("SELECT remove_compression_policy('trend_snapshots', if_exists => TRUE);")
    op.execute("SELECT remove_retention_policy('trend_snapshots', if_exists => TRUE);")
    op.execute("ALTER TABLE trend_snapshots SET (timescaledb.compress = false);")
