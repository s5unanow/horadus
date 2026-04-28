"""Tier 1 payload and result conversion helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.processing.tier1_contract import (
    canonical_trend_id,
    optional_text,
    trend_list_field,
    unique_strings,
)
from src.processing.tier1_taxonomy_floor import non_operational_score_cap, taxonomy_keyword_floors
from src.processing.tier1_types import (
    Tier1ItemResult,
    Tier1Output,
    TrendRelevanceScore,
    TrendScoreOutput,
)

if TYPE_CHECKING:
    from src.storage.models import RawItem, Trend


def trend_payload(trend: Trend, *, trend_identifier: Callable[[Trend], str]) -> dict[str, Any]:
    indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
    all_keywords: list[str] = []
    for indicator in indicators.values():
        if not isinstance(indicator, dict):
            continue
        for keyword in unique_strings(indicator.get("keywords", [])):
            if keyword not in all_keywords:
                all_keywords.append(keyword)

    payload: dict[str, Any] = {
        "trend_id": trend_identifier(trend),
        "name": trend.name,
        "description": optional_text(getattr(trend, "description", None)),
        "keywords": all_keywords,
        "regions": trend_list_field(trend, "regions"),
        "actors": trend_list_field(trend, "actors"),
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def validate_output_alignment(output: Tier1Output, *, items: list[RawItem]) -> None:
    expected_item_ids = {str(item.id) for item in items}
    actual_item_ids: set[str] = set()
    for row in output.items:
        if row.item_id in actual_item_ids:
            msg = f"Tier 1 response has duplicate item id {row.item_id}"
            raise ValueError(msg)
        actual_item_ids.add(row.item_id)
    if expected_item_ids != actual_item_ids:
        msg = "Tier 1 response item ids do not match input batch"
        raise ValueError(msg)


def to_item_results(
    output: Tier1Output,
    *,
    items: list[RawItem],
    trends: list[Trend],
    trend_identifier: Callable[[Trend], str],
    threshold: int,
) -> list[Tier1ItemResult]:
    expected_trend_ids = [trend_identifier(trend) for trend in trends]
    expected_trend_id_set = set(expected_trend_ids)
    item_by_id = {str(item.id): item for item in items}
    results: list[Tier1ItemResult] = []
    for row in output.items:
        item = item_by_id[row.item_id]
        trend_scores = _trend_scores_for_row(
            row_trend_scores=row.trend_scores,
            item=item,
            trends=trends,
            expected_trend_ids=expected_trend_ids,
            expected_trend_id_set=expected_trend_id_set,
            trend_identifier=trend_identifier,
            threshold=threshold,
        )
        max_relevance = max(score.relevance_score for score in trend_scores)
        results.append(
            Tier1ItemResult(
                item_id=UUID(row.item_id),
                max_relevance=max_relevance,
                should_queue_tier2=max_relevance >= threshold,
                trend_scores=trend_scores,
            )
        )
    return results


def _trend_scores_for_row(
    *,
    row_trend_scores: list[TrendScoreOutput],
    item: RawItem,
    trends: list[Trend],
    expected_trend_ids: list[str],
    expected_trend_id_set: set[str],
    trend_identifier: Callable[[Trend], str],
    threshold: int,
) -> list[TrendRelevanceScore]:
    score_by_trend_id = _dedupe_known_scores(
        row_trend_scores=row_trend_scores,
        trends=trends,
        expected_trend_id_set=expected_trend_id_set,
        trend_identifier=trend_identifier,
    )
    floor_by_trend_id = taxonomy_keyword_floors(
        title=item.title,
        content=item.raw_content,
        trends=trends,
        trend_identifier=trend_identifier,
        threshold=threshold,
    )
    trend_scores = [
        _score_for_trend(
            trend_id=trend_id,
            score_output=score_by_trend_id.get(trend_id),
            floor=floor_by_trend_id.get(trend_id),
        )
        for trend_id in expected_trend_ids
    ]
    score_cap = non_operational_score_cap(title=item.title, content=item.raw_content)
    if score_cap is None:
        return trend_scores
    return [
        TrendRelevanceScore(
            trend_id=score.trend_id,
            relevance_score=min(score.relevance_score, score_cap),
            rationale=score.rationale,
        )
        for score in trend_scores
    ]


def _dedupe_known_scores(
    *,
    row_trend_scores: list[TrendScoreOutput],
    trends: list[Trend],
    expected_trend_id_set: set[str],
    trend_identifier: Callable[[Trend], str],
) -> dict[str, TrendScoreOutput]:
    score_by_trend_id: dict[str, TrendScoreOutput] = {}
    for score in row_trend_scores:
        trend_id = canonical_trend_id(
            score.trend_id,
            trends=trends,
            trend_identifier=trend_identifier,
        )
        if trend_id not in expected_trend_id_set:
            continue
        existing = score_by_trend_id.get(trend_id)
        if existing is None or score.relevance_score > existing.relevance_score:
            score_by_trend_id[trend_id] = score
    return score_by_trend_id


def _score_for_trend(
    *,
    trend_id: str,
    score_output: TrendScoreOutput | None,
    floor: tuple[int, str] | None,
) -> TrendRelevanceScore:
    if score_output is None:
        if floor is None:
            return TrendRelevanceScore(
                trend_id=trend_id,
                relevance_score=0,
                rationale="No Tier 1 score returned; deterministically filled as unrelated.",
            )
        return TrendRelevanceScore(
            trend_id=trend_id,
            relevance_score=floor[0],
            rationale=floor[1],
        )
    if floor is not None and score_output.relevance_score < floor[0]:
        return TrendRelevanceScore(
            trend_id=trend_id,
            relevance_score=floor[0],
            rationale=floor[1],
        )
    return TrendRelevanceScore(
        trend_id=trend_id,
        relevance_score=score_output.relevance_score,
        rationale=score_output.rationale,
    )
