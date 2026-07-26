"""Source-family enum kept separate from the legacy aggregate model module."""

from __future__ import annotations

import enum


class SourceType(enum.StrEnum):
    """Types of data sources."""

    RSS = "rss"
    TELEGRAM = "telegram"
    GDELT = "gdelt"
    API = "api"
    SCRAPER = "scraper"
