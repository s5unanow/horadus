"""Add DB-level constraints for categorical dimension fields.

Revision ID: 0018_dimension_check_constraints
Revises: 0017_trend_definition_versions
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_dimension_check_constraints"
down_revision = "0017_trend_definition_versions"
branch_labels = None
depends_on = None

_SOURCE_TIER_ALLOWED = ("primary", "wire", "major", "regional", "aggregator")
_REPORTING_TYPE_ALLOWED = ("firsthand", "secondary", "aggregator")
_EVENT_LIFECYCLE_ALLOWED = ("emerging", "confirmed", "fading", "archived")


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _assert_no_invalid_dimension_values(
    *,
    table_name: str,
    column_name: str,
    allowed_values: tuple[str, ...],
) -> None:
    conn = op.get_bind()
    allowed_sql = _quoted_values(allowed_values)
    rows = conn.execute(
        sa.text(
            f"""
            SELECT
                {column_name}::text AS value,
                COUNT(*) AS row_count
            FROM {table_name}
            WHERE {column_name} NOT IN ({allowed_sql})
            GROUP BY {column_name}
            ORDER BY row_count DESC, value ASC
            LIMIT 10
            """
        )
    ).mappings()
    invalid_rows = list(rows)
    if not invalid_rows:
        return

    preview = ", ".join(
        f"{row['value']} ({row['row_count']})"
        for row in invalid_rows
    )
    msg = (
        f"Cannot apply CHECK constraint for {table_name}.{column_name}. "
        f"Found invalid values: {preview}. "
        f"Allowed values: {', '.join(allowed_values)}."
    )
    raise RuntimeError(msg)


def upgrade() -> None:
    _assert_no_invalid_dimension_values(
        table_name="sources",
        column_name="source_tier",
        allowed_values=_SOURCE_TIER_ALLOWED,
    )
    _assert_no_invalid_dimension_values(
        table_name="sources",
        column_name="reporting_type",
        allowed_values=_REPORTING_TYPE_ALLOWED,
    )
    _assert_no_invalid_dimension_values(
        table_name="events",
        column_name="lifecycle_status",
        allowed_values=_EVENT_LIFECYCLE_ALLOWED,
    )

    op.create_check_constraint(
        "check_sources_source_tier_allowed",
        "sources",
        f"source_tier IN ({_quoted_values(_SOURCE_TIER_ALLOWED)})",
    )
    op.create_check_constraint(
        "check_sources_reporting_type_allowed",
        "sources",
        f"reporting_type IN ({_quoted_values(_REPORTING_TYPE_ALLOWED)})",
    )
    op.create_check_constraint(
        "check_events_lifecycle_status_allowed",
        "events",
        f"lifecycle_status IN ({_quoted_values(_EVENT_LIFECYCLE_ALLOWED)})",
    )


def downgrade() -> None:
    op.drop_constraint("check_events_lifecycle_status_allowed", "events", type_="check")
    op.drop_constraint("check_sources_reporting_type_allowed", "sources", type_="check")
    op.drop_constraint("check_sources_source_tier_allowed", "sources", type_="check")
