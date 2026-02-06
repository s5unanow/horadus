"""Data ingestion."""

from src.ingestion.gdelt_client import GDELTClient, GDELTCollectionResult, GDELTQueryConfig
from src.ingestion.rss_collector import CollectionResult, FeedConfig, RSSCollector

__all__ = [
    "CollectionResult",
    "FeedConfig",
    "GDELTClient",
    "GDELTCollectionResult",
    "GDELTQueryConfig",
    "RSSCollector",
]
