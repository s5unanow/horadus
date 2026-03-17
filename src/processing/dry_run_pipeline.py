"""Deterministic offline pipeline dry-run over fixture items."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from src.core.trend_config import TrendConfig, validate_trend_config_payload
from src.core.trend_engine import calculate_evidence_delta, logodds_to_prob, prob_to_logodds
from src.processing.deduplication_service import DeduplicationService

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True, slots=True)
class FixtureItem:
    item_id: str
    title: str
    url: str
    published_at: datetime
    content: str
    source: str


def _parse_datetime(raw_value: str) -> datetime:
    normalized = raw_value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _item_signature(item: FixtureItem) -> str:
    tokens = [
        token
        for token in _WORD_RE.findall(item.title.lower())
        if token not in _STOPWORDS and len(token) > 2
    ]
    if not tokens:
        return "misc"
    return "-".join(tokens[:4])


def _load_fixture_items(path: Path) -> list[FixtureItem]:
    items: list[FixtureItem] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            msg = f"Fixture line {line_number} must be an object"
            raise ValueError(msg)

        item_id_raw = payload.get("id")
        title_raw = payload.get("title")
        url_raw = payload.get("url")
        published_at_raw = payload.get("published_at")
        content_raw = payload.get("content")
        source_raw = payload.get("source")

        item_id = str(item_id_raw or f"fixture-{line_number:03d}").strip()
        title = str(title_raw or "").strip()
        url = str(url_raw or "").strip()
        published_at = _parse_datetime(str(published_at_raw or datetime.now(tz=UTC).isoformat()))
        content = str(content_raw or "").strip()
        source = str(source_raw or "fixture").strip() or "fixture"

        items.append(
            FixtureItem(
                item_id=item_id,
                title=title,
                url=url,
                published_at=published_at,
                content=content,
                source=source,
            )
        )

    items.sort(key=lambda item: (item.published_at, item.item_id))
    return items


def _deduplicate(
    items: list[FixtureItem],
) -> tuple[list[FixtureItem], list[dict[str, str]]]:
    kept_items: list[FixtureItem] = []
    duplicates: list[dict[str, str]] = []

    by_url: dict[str, str] = {}
    by_hash: dict[str, str] = {}

    for item in items:
        normalized_url = DeduplicationService.normalize_url(item.url)
        content_hash = DeduplicationService.compute_content_hash(
            f"{item.title}\n{item.content}".strip()
        )

        if normalized_url and normalized_url in by_url:
            duplicates.append(
                {
                    "item_id": item.item_id,
                    "duplicate_of": by_url[normalized_url],
                    "reason": "url",
                }
            )
            continue

        if content_hash in by_hash:
            duplicates.append(
                {
                    "item_id": item.item_id,
                    "duplicate_of": by_hash[content_hash],
                    "reason": "content_hash",
                }
            )
            continue

        kept_items.append(item)
        if normalized_url:
            by_url[normalized_url] = item.item_id
        by_hash[content_hash] = item.item_id

    return kept_items, duplicates


def _cluster_items(items: list[FixtureItem]) -> list[dict[str, Any]]:
    groups: dict[str, list[FixtureItem]] = {}
    for item in items:
        key = f"{item.published_at.date().isoformat()}::{_item_signature(item)}"
        groups.setdefault(key, []).append(item)

    clusters: list[dict[str, Any]] = []
    for cluster_key, cluster_items in sorted(groups.items()):
        cluster_items.sort(key=lambda item: item.item_id)
        cluster_id = hashlib.sha256(cluster_key.encode("utf-8")).hexdigest()[:12]
        clusters.append(
            {
                "cluster_id": cluster_id,
                "cluster_key": cluster_key,
                "item_ids": [item.item_id for item in cluster_items],
                "source_count": len({item.source for item in cluster_items}),
                "text": "\n".join(
                    f"{item.title} {item.content}".strip() for item in cluster_items
                ).strip(),
            }
        )

    return clusters


def _load_trend_configs(trend_config_dir: Path) -> list[tuple[str, TrendConfig]]:
    loaded: list[tuple[str, TrendConfig]] = []
    for config_path in sorted(trend_config_dir.glob("*.yaml")):
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        validated = validate_trend_config_payload(payload)
        trend_id = str(payload.get("id") or config_path.stem)
        loaded.append((trend_id, validated))
    return loaded


def _score_trends(
    *,
    clusters: list[dict[str, Any]],
    trend_configs: list[tuple[str, TrendConfig]],
) -> list[dict[str, Any]]:
    trend_scores: list[dict[str, Any]] = []

    for trend_id, trend_config in trend_configs:
        baseline_log_odds = prob_to_logodds(float(trend_config.baseline_probability))
        total_delta = 0.0
        matched_signals: list[dict[str, Any]] = []

        for cluster in clusters:
            cluster_text = str(cluster["text"]).lower()
            corroboration_count = max(1, int(cluster["source_count"]))

            for signal_type in sorted(trend_config.indicators.keys()):
                indicator = trend_config.indicators[signal_type]
                keyword_hits = 0
                for keyword in indicator.keywords:
                    normalized_keyword = keyword.strip().lower()
                    if not normalized_keyword:
                        continue
                    keyword_hits += cluster_text.count(normalized_keyword)

                if keyword_hits <= 0:
                    continue

                severity = min(1.0, 0.2 * keyword_hits)
                delta, _factors = calculate_evidence_delta(
                    signal_type=signal_type,
                    indicator_weight=float(indicator.weight),
                    source_credibility=0.7,
                    corroboration_count=float(corroboration_count),
                    novelty_score=1.0,
                    direction=indicator.direction,
                    severity=severity,
                    confidence=1.0,
                )
                total_delta += delta
                matched_signals.append(
                    {
                        "cluster_id": str(cluster["cluster_id"]),
                        "signal_type": signal_type,
                        "keyword_hits": keyword_hits,
                        "delta_log_odds": round(float(delta), 6),
                    }
                )

        projected_probability = logodds_to_prob(baseline_log_odds + total_delta)
        trend_scores.append(
            {
                "trend_id": trend_id,
                "baseline_probability": round(float(trend_config.baseline_probability), 6),
                "delta_log_odds": round(total_delta, 6),
                "projected_probability": round(projected_probability, 6),
                "matched_signals": sorted(
                    matched_signals,
                    key=lambda item: (
                        str(item["cluster_id"]),
                        str(item["signal_type"]),
                    ),
                ),
            }
        )

    trend_scores.sort(key=lambda row: str(row["trend_id"]))
    return trend_scores


def run_pipeline_dry_run(
    *,
    fixture_path: Path,
    trend_config_dir: Path,
    output_path: Path,
) -> Path:
    items = _load_fixture_items(fixture_path)
    deduplicated_items, duplicates = _deduplicate(items)
    clusters = _cluster_items(deduplicated_items)
    trend_configs = _load_trend_configs(trend_config_dir)
    trend_scores = _score_trends(clusters=clusters, trend_configs=trend_configs)

    payload: dict[str, Any] = {
        "fixture_path": str(fixture_path),
        "trend_config_dir": str(trend_config_dir),
        "generated_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "items_total": len(items),
        "items_after_dedup": len(deduplicated_items),
        "duplicates": duplicates,
        "clusters": [
            {
                "cluster_id": cluster["cluster_id"],
                "cluster_key": cluster["cluster_key"],
                "item_ids": cluster["item_ids"],
                "source_count": cluster["source_count"],
            }
            for cluster in clusters
        ],
        "trend_scores": trend_scores,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
