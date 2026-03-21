"""Add runtime provenance and scoring-version contract columns.

Revision ID: 0028_runtime_provenance_contract
Revises: 0027_event_provenance
Create Date: 2026-03-21 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_runtime_provenance_contract"
down_revision = "0027_event_provenance"
branch_labels = None
depends_on = None

_CURRENT_SCORING_MATH_VERSION = "trend-scoring-v1"
_CURRENT_SCORING_PARAMETER_SET = "stable-default-v1"
_LEGACY_SCORING_VERSION = "legacy-unversioned"
_LEGACY_SCORING_PARAMETER_SET = "legacy-unversioned"


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "extraction_provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "generation_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("scoring_math_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("scoring_parameter_set", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "trend_restatements",
        sa.Column("scoring_math_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "trend_restatements",
        sa.Column("scoring_parameter_set", sa.String(length=64), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE events
            SET extraction_provenance = CASE
                WHEN extracted_what IS NOT NULL
                    OR categories IS NOT NULL
                    OR extracted_claims IS NOT NULL
                THEN '{"status":"legacy_unversioned","stage":"tier2"}'::jsonb
                ELSE '{}'::jsonb
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE reports
            SET generation_manifest = '{"status":"legacy_unversioned"}'::jsonb
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE trend_evidence
            SET scoring_math_version = :legacy_math_version,
                scoring_parameter_set = :legacy_parameter_set
            """
        ).bindparams(
            legacy_math_version=_LEGACY_SCORING_VERSION,
            legacy_parameter_set=_LEGACY_SCORING_PARAMETER_SET,
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE trend_restatements
            SET scoring_math_version = :legacy_math_version,
                scoring_parameter_set = :legacy_parameter_set
            """
        ).bindparams(
            legacy_math_version=_LEGACY_SCORING_VERSION,
            legacy_parameter_set=_LEGACY_SCORING_PARAMETER_SET,
        )
    )

    op.alter_column(
        "trend_evidence",
        "scoring_math_version",
        nullable=False,
        server_default=sa.text(f"'{_CURRENT_SCORING_MATH_VERSION}'"),
    )
    op.alter_column(
        "trend_evidence",
        "scoring_parameter_set",
        nullable=False,
        server_default=sa.text(f"'{_CURRENT_SCORING_PARAMETER_SET}'"),
    )
    op.alter_column(
        "trend_restatements",
        "scoring_math_version",
        nullable=False,
        server_default=sa.text(f"'{_CURRENT_SCORING_MATH_VERSION}'"),
    )
    op.alter_column(
        "trend_restatements",
        "scoring_parameter_set",
        nullable=False,
        server_default=sa.text(f"'{_CURRENT_SCORING_PARAMETER_SET}'"),
    )


def downgrade() -> None:
    op.drop_column("trend_restatements", "scoring_parameter_set")
    op.drop_column("trend_restatements", "scoring_math_version")
    op.drop_column("trend_evidence", "scoring_parameter_set")
    op.drop_column("trend_evidence", "scoring_math_version")
    op.drop_column("reports", "generation_manifest")
    op.drop_column("events", "extraction_provenance")
