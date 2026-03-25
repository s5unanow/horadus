"""Add stable provider keys for source identity.

Revision ID: 0035_add_source_provider_keys
Revises: 0034_add_coverage_snapshots
Create Date: 2026-03-25
"""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_add_source_provider_keys"
down_revision = "0034_add_coverage_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("provider_source_key", sa.String(length=255), nullable=True))

    bind = op.get_bind()
    metadata = sa.MetaData()
    sources = sa.Table(
        "sources",
        metadata,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("provider_source_key", sa.String(length=255), nullable=True),
    )

    duplicate_keys: dict[tuple[str, str], list[str]] = {}
    rows = bind.execute(
        sa.select(
            sources.c.id,
            sources.c.type,
            sources.c.url,
            sources.c.config,
        )
    ).mappings()
    for row in rows:
        provider_source_key = _provider_source_key(
            source_type=row["type"],
            config=row["config"],
            url=row["url"],
        )
        if provider_source_key is None:
            continue
        bind.execute(
            sa.update(sources)
            .where(sources.c.id == row["id"])
            .values(provider_source_key=provider_source_key)
        )
        duplicate_key = (row["type"], provider_source_key)
        duplicate_keys.setdefault(duplicate_key, []).append(str(row["id"]))

    collisions = {
        key: ids for key, ids in duplicate_keys.items() if len(ids) > 1
    }
    if collisions:
        details = "; ".join(
            f"{source_type}/{provider_key}: {', '.join(ids)}"
            for (source_type, provider_key), ids in sorted(collisions.items())
        )
        msg = f"Cannot backfill unique provider_source_key values for sources: {details}"
        raise RuntimeError(msg)

    op.create_index(
        "uq_sources_type_provider_source_key",
        "sources",
        ["type", "provider_source_key"],
        unique=True,
        postgresql_where=sa.text("provider_source_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sources_type_provider_source_key", table_name="sources")
    op.drop_column("sources", "provider_source_key")


def _provider_source_key(
    *,
    source_type: str,
    config: dict[str, object] | None,
    url: str | None,
) -> str | None:
    if source_type == "gdelt":
        return _gdelt_provider_source_key(config or {})
    if source_type == "telegram":
        channel_ref = (config or {}).get("channel")
        if not isinstance(channel_ref, str):
            channel_ref = url
        return _telegram_provider_source_key(channel_ref)
    return None


def _gdelt_provider_source_key(config: dict[str, object]) -> str:
    payload = {
        "query": _normalize_text(config.get("query")) or "",
        "themes": _normalize_list(config.get("themes")),
        "actors": _normalize_list(config.get("actors")),
        "countries": _normalize_list(config.get("countries")),
        "languages": _normalize_list(config.get("languages")),
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"gdelt:{hashlib.sha256(rendered.encode('utf-8')).hexdigest()}"


def _telegram_provider_source_key(channel_ref: object) -> str | None:
    handle = _normalize_telegram_channel_handle(channel_ref)
    if handle is None:
        return None
    return f"telegram:{handle}"


def _normalize_telegram_channel_handle(channel_ref: object) -> str | None:
    normalized = _normalize_text(channel_ref)
    if normalized is None:
        return None
    prefixes = ("@", "https://t.me/", "http://t.me/", "t.me/")
    for prefix in prefixes:
        if normalized.startswith(prefix):
            handle = normalized.removeprefix(prefix).split("/", 1)[0].strip()
            return handle or None
    return None


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_normalize_text(item) for item in value if _normalize_text(item)})


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split()).lower()
    return normalized or None
