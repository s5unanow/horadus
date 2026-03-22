"""Add durable privileged-write audit and idempotency records.

Revision ID: 0031_privileged_write_audits
Revises: 0030_trend_state_versions
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0031_privileged_write_audits"
down_revision = "0030_trend_state_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privileged_write_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_key", sa.String(length=255), nullable=False),
        sa.Column("actor_api_key_id", sa.String(length=255), nullable=True),
        sa.Column("actor_api_key_name", sa.String(length=255), nullable=True),
        sa.Column("operator_identity", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("request_method", sa.String(length=10), nullable=False),
        sa.Column("request_path", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_identifier", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "request_intent",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expected_revision_token", sa.String(length=128), nullable=True),
        sa.Column("observed_revision_token", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "result_links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "replay_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_privileged_write_audits_action_seen",
        "privileged_write_audits",
        ["action", "first_seen_at"],
        unique=False,
    )
    op.create_index(
        "idx_privileged_write_audits_target",
        "privileged_write_audits",
        ["target_type", "target_identifier"],
        unique=False,
    )
    op.create_index(
        "uq_privileged_write_audits_actor_action_idempotency",
        "privileged_write_audits",
        ["actor_key", "action", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_privileged_write_audits_actor_action_idempotency",
        table_name="privileged_write_audits",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("idx_privileged_write_audits_target", table_name="privileged_write_audits")
    op.drop_index("idx_privileged_write_audits_action_seen", table_name="privileged_write_audits")
    op.drop_table("privileged_write_audits")
