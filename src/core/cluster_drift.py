"""Cluster drift sentinel computations and artifact persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ClusterEventSample:
    item_count: int
    has_contradictions: bool
    languages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClusterDriftThresholds:
    singleton_rate_warn: float
    large_cluster_rate_warn: float
    contradiction_rate_warn: float
    language_drift_warn: float
    large_cluster_size: int


def _normalize_distribution(raw_counts: dict[str, int]) -> dict[str, float]:
    total = sum(max(0, count) for count in raw_counts.values())
    if total <= 0:
        return {}
    return {
        key: max(0, value) / total
        for key, value in sorted(raw_counts.items(), key=lambda row: row[0])
    }


def _language_drift_score(
    *,
    current_distribution: dict[str, float],
    baseline_distribution: dict[str, float],
) -> float:
    all_languages = set(current_distribution) | set(baseline_distribution)
    if not all_languages:
        return 0.0
    total_delta = 0.0
    for language in all_languages:
        total_delta += abs(
            current_distribution.get(language, 0.0) - baseline_distribution.get(language, 0.0)
        )
    return total_delta / 2.0


def compute_cluster_drift_summary(
    *,
    event_samples: list[ClusterEventSample],
    thresholds: ClusterDriftThresholds,
    baseline_language_distribution: dict[str, float] | None,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, object]:
    total_events = len(event_samples)
    singleton_events = sum(1 for sample in event_samples if sample.item_count <= 1)
    large_cluster_events = sum(
        1 for sample in event_samples if sample.item_count >= max(2, thresholds.large_cluster_size)
    )
    contradiction_events = sum(1 for sample in event_samples if sample.has_contradictions)

    language_counts: dict[str, int] = {}
    for sample in event_samples:
        for language in sample.languages:
            normalized_language = language.strip().lower() or "unknown"
            language_counts[normalized_language] = language_counts.get(normalized_language, 0) + 1

    singleton_rate = (singleton_events / total_events) if total_events else 0.0
    large_cluster_rate = (large_cluster_events / total_events) if total_events else 0.0
    contradiction_rate = (contradiction_events / total_events) if total_events else 0.0
    current_distribution = _normalize_distribution(language_counts)
    baseline_distribution = baseline_language_distribution or {}
    language_drift_score = _language_drift_score(
        current_distribution=current_distribution,
        baseline_distribution=baseline_distribution,
    )

    warnings: list[str] = []
    if singleton_rate > thresholds.singleton_rate_warn:
        warnings.append("singleton_rate")
    if large_cluster_rate > thresholds.large_cluster_rate_warn:
        warnings.append("large_cluster_tail")
    if contradiction_rate > thresholds.contradiction_rate_warn:
        warnings.append("contradiction_incidence")
    if language_drift_score > thresholds.language_drift_warn:
        warnings.append("language_distribution_drift")

    return {
        "generated_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "window_start": window_start.replace(microsecond=0).isoformat(),
        "window_end": window_end.replace(microsecond=0).isoformat(),
        "event_count": total_events,
        "singleton_rate": round(singleton_rate, 6),
        "large_cluster_rate": round(large_cluster_rate, 6),
        "contradiction_rate": round(contradiction_rate, 6),
        "large_cluster_size": max(2, thresholds.large_cluster_size),
        "language_distribution": current_distribution,
        "baseline_language_distribution": baseline_distribution,
        "language_drift_score": round(language_drift_score, 6),
        "warning_keys": warnings,
        "thresholds": {
            "singleton_rate_warn": thresholds.singleton_rate_warn,
            "large_cluster_rate_warn": thresholds.large_cluster_rate_warn,
            "contradiction_rate_warn": thresholds.contradiction_rate_warn,
            "language_drift_warn": thresholds.language_drift_warn,
        },
    }


def load_latest_language_distribution(artifact_dir: Path) -> dict[str, float] | None:
    if not artifact_dir.exists():
        return None
    artifacts = sorted(artifact_dir.glob("*.json"))
    if not artifacts:
        return None
    latest = artifacts[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    distribution = payload.get("language_distribution")
    if isinstance(distribution, dict):
        normalized: dict[str, float] = {}
        for key, value in distribution.items():
            try:
                normalized[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return normalized
    return None


def write_cluster_drift_artifact(*, artifact_dir: Path, summary: dict[str, object]) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    window_end_raw = str(summary.get("window_end", ""))
    try:
        window_end = datetime.fromisoformat(window_end_raw.replace("Z", "+00:00"))
    except ValueError:
        window_end = datetime.now(tz=UTC)
    filename = f"{window_end.date().isoformat()}.json"
    output_path = artifact_dir / filename
    output_path.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
