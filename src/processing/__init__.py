"""Data processing services."""

from src.processing.deduplication_service import DeduplicationResult, DeduplicationService
from src.processing.embedding_service import EmbeddingRunResult, EmbeddingService
from src.processing.event_clusterer import ClusterResult, EventClusterer
from src.processing.tier1_classifier import (
    Tier1Classifier,
    Tier1ItemResult,
    Tier1RunResult,
    Tier1Usage,
    TrendRelevanceScore,
)
from src.processing.tier2_classifier import (
    Tier2Classifier,
    Tier2EventResult,
    Tier2RunResult,
    Tier2Usage,
    TrendImpact,
)

__all__ = [
    "ClusterResult",
    "DeduplicationResult",
    "DeduplicationService",
    "EmbeddingRunResult",
    "EmbeddingService",
    "EventClusterer",
    "Tier1Classifier",
    "Tier1ItemResult",
    "Tier1RunResult",
    "Tier1Usage",
    "Tier2Classifier",
    "Tier2EventResult",
    "Tier2RunResult",
    "Tier2Usage",
    "TrendImpact",
    "TrendRelevanceScore",
]
