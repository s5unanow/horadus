"""Deterministic mapping from extracted event facts to trend impacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.trend_config import normalize_definition_payload, trend_runtime_id_for_record
from src.processing.event_claims import (
    EventClaimSpec,
    build_event_claim_specs,
    normalize_claim_text,
)
from src.storage.models import Event, TaxonomyGapReason, Trend

TREND_IMPACT_MAPPING_KEY = "_trend_impact_mapping"
_MAPPING_VERSION = 1
_UNMAPPED_TREND_ID = "__unmapped__"
_UNMAPPED_SIGNAL_TYPE = "__no_matching_indicator__"
_AMBIGUOUS_VALUE = "__ambiguous__"
_DESCRIPTION_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
}


@dataclass(frozen=True)
class TrendImpactMappingResult:
    """Deterministic mapping output for one event."""

    impacts: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class _IndicatorContext:
    trend_id: str
    trend_name: str
    signal_type: str
    direction: str
    description: str
    keywords: tuple[str, ...]
    description_terms: tuple[str, ...]
    actor_phrases: tuple[str, ...]
    region_phrases: tuple[str, ...]


@dataclass(frozen=True)
class _Candidate:
    indicator: _IndicatorContext
    claim: EventClaimSpec
    score: int
    matched_keywords: tuple[str, ...]
    description_overlap: tuple[str, ...]
    actor_matches: tuple[str, ...]
    region_matches: tuple[str, ...]


def map_event_trend_impacts(*, event: Event, trends: list[Trend]) -> TrendImpactMappingResult:
    """Map extracted claims onto eligible trend indicators."""

    claim_specs = _claim_specs_for_mapping(event)
    event_context = _event_context_text(event)
    indicators = _indicator_contexts(trends)

    mapped_impacts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for claim in claim_specs:
        candidates = _rank_candidates(
            claim=claim,
            event_context=event_context,
            indicators=indicators,
        )
        if not candidates:
            unresolved.append(_no_match_diagnostic(claim=claim, event=event))
            continue
        best = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        if runner_up is not None and runner_up.score >= best.score - 5:
            unresolved.append(
                _ambiguous_diagnostic(
                    claim=claim,
                    event=event,
                    candidates=candidates[:3],
                )
            )
            continue
        mapped_impacts.append(_build_impact(best=best, runner_up=runner_up))

    diagnostics = {
        "version": _MAPPING_VERSION,
        "strategy": "keyword-and-metadata",
        "unresolved": unresolved,
    }
    return TrendImpactMappingResult(impacts=mapped_impacts, diagnostics=diagnostics)


def iter_unresolved_mapping_gaps(event: Event) -> list[dict[str, Any]]:
    """Return unresolved deterministic-mapping diagnostics persisted on an event."""

    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    payload = claims.get(TREND_IMPACT_MAPPING_KEY)
    if not isinstance(payload, dict):
        return []
    unresolved = payload.get("unresolved")
    if not isinstance(unresolved, list):
        return []
    return [entry for entry in unresolved if isinstance(entry, dict)]


def taxonomy_gap_reason_for_mapping(reason: str) -> TaxonomyGapReason:
    """Map deterministic-mapping diagnostics to taxonomy-gap reasons."""

    if reason == TaxonomyGapReason.AMBIGUOUS_MAPPING.value:
        return TaxonomyGapReason.AMBIGUOUS_MAPPING
    return TaxonomyGapReason.NO_MATCHING_INDICATOR


def _claim_specs_for_mapping(event: Event) -> list[EventClaimSpec]:
    specs = build_event_claim_specs(event)
    statement_specs = [spec for spec in specs if spec.claim_type == "statement"]
    if statement_specs:
        return statement_specs
    return specs[:1]


def _event_context_text(event: Event) -> str:
    parts: list[str] = []
    if isinstance(event.extracted_who, list):
        parts.extend(value for value in event.extracted_who if isinstance(value, str))
    extracted_when = getattr(event, "extracted_when", None)
    for raw_value in (
        event.extracted_where,
        event.extracted_what,
        event.canonical_summary,
        extracted_when.isoformat() if extracted_when is not None else None,
    ):
        if isinstance(raw_value, str) and raw_value.strip():
            parts.append(raw_value)
    return normalize_claim_text(" ".join(parts))


def _indicator_contexts(trends: list[Trend]) -> list[_IndicatorContext]:
    contexts: list[_IndicatorContext] = []
    for trend in trends:
        trend_id = trend_runtime_id_for_record(trend)
        definition = normalize_definition_payload(
            trend.definition if isinstance(trend.definition, dict) else None
        )
        actor_phrases = _normalized_phrases(definition.get("actors"))
        region_phrases = _normalized_phrases(definition.get("regions"))
        indicators = trend.indicators if isinstance(trend.indicators, dict) else {}
        for signal_type, raw_config in indicators.items():
            if not isinstance(raw_config, dict):
                continue
            direction = str(raw_config.get("direction", "")).strip()
            if direction not in {"escalatory", "de_escalatory"}:
                continue
            description = _indicator_description(signal_type=signal_type, config=raw_config)
            contexts.append(
                _IndicatorContext(
                    trend_id=trend_id,
                    trend_name=str(getattr(trend, "name", "") or trend_id),
                    signal_type=signal_type,
                    direction=direction,
                    description=description,
                    keywords=_normalized_phrases(raw_config.get("keywords")),
                    description_terms=_description_terms(
                        signal_type=signal_type, description=description
                    ),
                    actor_phrases=actor_phrases,
                    region_phrases=region_phrases,
                )
            )
    return contexts


def _indicator_description(*, signal_type: str, config: dict[str, Any]) -> str:
    raw_description = config.get("description")
    if isinstance(raw_description, str) and raw_description.strip():
        return raw_description.strip()
    humanized = signal_type.replace("_", " ").strip()
    if humanized:
        return humanized
    return "signal relevant to this trend"


def _description_terms(*, signal_type: str, description: str) -> tuple[str, ...]:
    values = normalize_claim_text(f"{signal_type.replace('_', ' ')} {description}").split()
    return tuple(value for value in values if value not in _DESCRIPTION_STOP_WORDS)


def _normalized_phrases(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    phrases: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = normalize_claim_text(value)
        if normalized and normalized not in phrases:
            phrases.append(normalized)
    return tuple(phrases)


def _rank_candidates(
    *,
    claim: EventClaimSpec,
    event_context: str,
    indicators: list[_IndicatorContext],
) -> list[_Candidate]:
    claim_text = normalize_claim_text(claim.claim_text)
    claim_terms = set(claim_text.split())
    event_terms = set(event_context.split())
    candidates: list[_Candidate] = []
    for indicator in indicators:
        matched_keywords = tuple(
            keyword for keyword in indicator.keywords if keyword and keyword in claim_text
        )
        description_overlap = tuple(
            sorted(term for term in claim_terms if term in indicator.description_terms)
        )
        if not matched_keywords and len(description_overlap) < 2:
            continue
        actor_matches = tuple(
            phrase for phrase in indicator.actor_phrases if phrase and phrase in event_context
        )
        region_matches = tuple(
            phrase for phrase in indicator.region_phrases if phrase and phrase in event_context
        )
        score = (
            len(matched_keywords) * 100
            + len(description_overlap) * 10
            + len(actor_matches) * 4
            + len(region_matches) * 3
            + len(event_terms.intersection(set(indicator.description_terms[:3])))
        )
        candidates.append(
            _Candidate(
                indicator=indicator,
                claim=claim,
                score=score,
                matched_keywords=matched_keywords,
                description_overlap=description_overlap,
                actor_matches=actor_matches,
                region_matches=region_matches,
            )
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            candidate.indicator.trend_id,
            candidate.indicator.signal_type,
        )
    )
    return candidates


def _build_impact(*, best: _Candidate, runner_up: _Candidate | None) -> dict[str, Any]:
    severity = 0.55
    if best.matched_keywords:
        severity = 0.7
    if len(best.matched_keywords) > 1:
        severity = 0.8

    confidence = 0.7
    if best.matched_keywords:
        confidence += 0.1
    if best.actor_matches or best.region_matches:
        confidence += 0.05
    if runner_up is None or (best.score - runner_up.score) >= 10:
        confidence += 0.1
    if not best.matched_keywords and len(best.description_overlap) >= 3:
        confidence += 0.05

    rationale_parts: list[str] = []
    if best.matched_keywords:
        keywords = ", ".join(best.matched_keywords)
        rationale_parts.append(f"Matched indicator keywords: {keywords}.")
    else:
        overlap = ", ".join(best.description_overlap)
        rationale_parts.append(f"Matched indicator terms: {overlap}.")
    if best.actor_matches:
        rationale_parts.append(f"Actor context: {', '.join(best.actor_matches)}.")
    if best.region_matches:
        rationale_parts.append(f"Region context: {', '.join(best.region_matches)}.")

    return {
        "trend_id": best.indicator.trend_id,
        "signal_type": best.indicator.signal_type,
        "direction": best.indicator.direction,
        "severity": round(min(1.0, severity), 4),
        "confidence": round(min(0.95, confidence), 4),
        "rationale": " ".join(rationale_parts),
        "event_claim_key": best.claim.claim_key,
        "event_claim_text": best.claim.claim_text,
    }


def _no_match_diagnostic(*, claim: EventClaimSpec, event: Event) -> dict[str, Any]:
    extracted_when = getattr(event, "extracted_when", None)
    return {
        "reason": TaxonomyGapReason.NO_MATCHING_INDICATOR.value,
        "trend_id": _UNMAPPED_TREND_ID,
        "signal_type": _UNMAPPED_SIGNAL_TYPE,
        "event_claim_key": claim.claim_key,
        "event_claim_text": claim.claim_text,
        "details": {
            "claim_type": claim.claim_type,
            "claim_order": claim.claim_order,
            "event_where": event.extracted_where,
            "event_when": extracted_when.isoformat() if extracted_when is not None else None,
        },
    }


def _ambiguous_diagnostic(
    *,
    claim: EventClaimSpec,
    event: Event,
    candidates: list[_Candidate],
) -> dict[str, Any]:
    extracted_when = getattr(event, "extracted_when", None)
    trend_values = {candidate.indicator.trend_id for candidate in candidates}
    signal_values = {candidate.indicator.signal_type for candidate in candidates}
    return {
        "reason": TaxonomyGapReason.AMBIGUOUS_MAPPING.value,
        "trend_id": next(iter(trend_values)) if len(trend_values) == 1 else _AMBIGUOUS_VALUE,
        "signal_type": (next(iter(signal_values)) if len(signal_values) == 1 else _AMBIGUOUS_VALUE),
        "event_claim_key": claim.claim_key,
        "event_claim_text": claim.claim_text,
        "details": {
            "claim_type": claim.claim_type,
            "claim_order": claim.claim_order,
            "event_where": event.extracted_where,
            "event_when": extracted_when.isoformat() if extracted_when is not None else None,
            "candidates": [
                {
                    "trend_id": candidate.indicator.trend_id,
                    "signal_type": candidate.indicator.signal_type,
                    "direction": candidate.indicator.direction,
                    "score": candidate.score,
                    "matched_keywords": list(candidate.matched_keywords),
                    "description_overlap": list(candidate.description_overlap),
                    "actor_matches": list(candidate.actor_matches),
                    "region_matches": list(candidate.region_matches),
                }
                for candidate in candidates
            ],
        },
    }
