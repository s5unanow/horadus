"""Data ingestion."""

from src.ingestion.gdelt_client import GDELTClient, GDELTCollectionResult, GDELTQueryConfig
from src.ingestion.rss_collector import CollectionResult, FeedConfig, RSSCollector
from src.ingestion.telegram_harvester import (
    ChannelConfig,
    HarvesterSettings,
    HarvestResult,
    TelegramHarvester,
)

__all__ = [
    "ChannelConfig",
    "CollectionResult",
    "FeedConfig",
    "GDELTClient",
    "GDELTCollectionResult",
    "GDELTQueryConfig",
    "HarvestResult",
    "HarvesterSettings",
    "RSSCollector",
    "TelegramHarvester",
]
