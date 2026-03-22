"""Deterministic mapping from extracted event facts to trend impacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.trend_config import normalize_definition_payload, trend_runtime_id_for_record
from src.processing.claim_text_analysis import claim_language, claim_polarity
from src.processing.event_claims import (
    EventClaimSpec,
    build_event_claim_specs,
    normalize_claim_text,
)
from src.storage.event_summary import resolved_event_summary
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


@dataclass(frozen=True)
class _IndicatorMatchSignals:
    claim_keyword_matches: tuple[str, ...]
    canonical_keyword_matches: tuple[str, ...]
    claim_overlap: tuple[str, ...]
    canonical_overlap: tuple[str, ...]

    @property
    def matched_keywords(self) -> tuple[str, ...]:
        return self.claim_keyword_matches + self.canonical_keyword_matches

    @property
    def description_overlap(self) -> tuple[str, ...]:
        return self.claim_overlap + self.canonical_overlap

    def is_match(self) -> bool:
        if self.claim_keyword_matches or len(self.claim_overlap) >= 2:
            return True
        return bool(self.canonical_keyword_matches or len(self.canonical_overlap) >= 2)


@dataclass(frozen=True)
class _SelectedImpact:
    impact: dict[str, Any]
    score: int
    claim_order: int
    claim_type: str


def map_event_trend_impacts(*, event: Event, trends: list[Trend]) -> TrendImpactMappingResult:
    """Map extracted claims onto eligible trend indicators."""

    claim_specs = _claim_specs_for_mapping(event)
    event_context = _event_context_text(event)
    indicators = _indicator_contexts(trends)

    selected_impacts: dict[tuple[str, str], _SelectedImpact] = {}
    unresolved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    deduplicated: list[dict[str, Any]] = []
    for claim in claim_specs:
        if _is_negative_claim(claim):
            skipped.append(_negative_claim_diagnostic(claim=claim, event=event))
            continue
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
        selected = _SelectedImpact(
            impact=_build_impact(best=best, runner_up=runner_up),
            score=best.score,
            claim_order=best.claim.claim_order,
            claim_type=best.claim.claim_type,
        )
        impact_key = _impact_key(best)
        existing = selected_impacts.get(impact_key)
        if existing is None:
            selected_impacts[impact_key] = selected
            continue
        if _prefer_selected_impact(candidate=selected, current=existing):
            deduplicated.append(
                _deduplicated_impact_diagnostic(
                    kept=selected,
                    suppressed=existing,
                    trend_id=impact_key[0],
                    signal_type=impact_key[1],
                )
            )
            selected_impacts[impact_key] = selected
            continue
        deduplicated.append(
            _deduplicated_impact_diagnostic(
                kept=existing,
                suppressed=selected,
                trend_id=impact_key[0],
                signal_type=impact_key[1],
            )
        )

    mapped_impacts = [
        selection.impact
        for selection in sorted(
            selected_impacts.values(),
            key=lambda selection: (
                selection.claim_order,
                str(selection.impact["trend_id"]),
                str(selection.impact["signal_type"]),
            ),
        )
    ]
    if mapped_impacts:
        unresolved = []
    diagnostics = {
        "version": _MAPPING_VERSION,
        "strategy": "keyword-metadata-canonical-context",
        "unresolved": unresolved,
    }
    if skipped:
        diagnostics["skipped"] = skipped
    if deduplicated:
        diagnostics["deduplicated"] = deduplicated
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
    fallback_specs = specs[:1]
    if not statement_specs:
        return fallback_specs
    return statement_specs + fallback_specs


def _event_context_text(event: Event) -> str:
    parts: list[str] = []
    if isinstance(event.extracted_who, list):
        parts.extend(value for value in event.extracted_who if isinstance(value, str))
    extracted_when = getattr(event, "extracted_when", None)
    for raw_value in (
        event.extracted_where,
        event.extracted_what,
        resolved_event_summary(event),
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
    canonical_context = ""
    if claim.claim_type != "statement" or claim_language(claim.claim_text) != "en":
        canonical_context = event_context
    canonical_terms = set(canonical_context.split())
    event_terms = set(event_context.split())
    candidates: list[_Candidate] = []
    for indicator in indicators:
        match_signals = _match_indicator(
            indicator=indicator,
            claim_text=claim_text,
            claim_terms=claim_terms,
            canonical_context=canonical_context,
            canonical_terms=canonical_terms,
        )
        if not match_signals.is_match():
            continue
        actor_matches = tuple(
            phrase for phrase in indicator.actor_phrases if phrase and phrase in event_context
        )
        region_matches = tuple(
            phrase for phrase in indicator.region_phrases if phrase and phrase in event_context
        )
        score = _candidate_score(
            indicator=indicator,
            match_signals=match_signals,
            actor_matches=actor_matches,
            region_matches=region_matches,
            event_terms=event_terms,
        )
        candidates.append(
            _Candidate(
                indicator=indicator,
                claim=claim,
                score=score,
                matched_keywords=match_signals.matched_keywords,
                description_overlap=match_signals.description_overlap,
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


def _match_indicator(
    *,
    indicator: _IndicatorContext,
    claim_text: str,
    claim_terms: set[str],
    canonical_context: str,
    canonical_terms: set[str],
) -> _IndicatorMatchSignals:
    claim_keyword_matches = tuple(
        keyword for keyword in indicator.keywords if keyword and keyword in claim_text
    )
    canonical_keyword_matches = tuple(
        keyword
        for keyword in indicator.keywords
        if (
            keyword
            and keyword not in claim_keyword_matches
            and canonical_context
            and keyword in canonical_context
        )
    )
    claim_overlap = tuple(
        sorted(term for term in claim_terms if term in indicator.description_terms)
    )
    canonical_overlap = tuple(
        sorted(
            term
            for term in canonical_terms
            if term in indicator.description_terms and term not in claim_overlap
        )
    )
    return _IndicatorMatchSignals(
        claim_keyword_matches=claim_keyword_matches,
        canonical_keyword_matches=canonical_keyword_matches,
        claim_overlap=claim_overlap,
        canonical_overlap=canonical_overlap,
    )


def _candidate_score(
    *,
    indicator: _IndicatorContext,
    match_signals: _IndicatorMatchSignals,
    actor_matches: tuple[str, ...],
    region_matches: tuple[str, ...],
    event_terms: set[str],
) -> int:
    return (
        len(match_signals.claim_keyword_matches) * 100
        + len(match_signals.canonical_keyword_matches) * 60
        + len(match_signals.claim_overlap) * 10
        + len(match_signals.canonical_overlap) * 4
        + len(actor_matches) * 4
        + len(region_matches) * 3
        + len(event_terms.intersection(set(indicator.description_terms[:3])))
    )


def _impact_key(candidate: _Candidate) -> tuple[str, str]:
    return candidate.indicator.trend_id, candidate.indicator.signal_type


def _prefer_selected_impact(*, candidate: _SelectedImpact, current: _SelectedImpact) -> bool:
    return (
        candidate.score,
        1 if candidate.claim_type == "statement" else 0,
        -candidate.claim_order,
        str(candidate.impact["event_claim_key"]),
    ) > (
        current.score,
        1 if current.claim_type == "statement" else 0,
        -current.claim_order,
        str(current.impact["event_claim_key"]),
    )


def _is_negative_claim(claim: EventClaimSpec) -> bool:
    language = claim_language(claim.claim_text)
    if language not in {"en", "uk", "ru"}:
        return False
    return claim_polarity(claim.claim_text, language=language) == "negative"


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


def _negative_claim_diagnostic(*, claim: EventClaimSpec, event: Event) -> dict[str, Any]:
    extracted_when = getattr(event, "extracted_when", None)
    return {
        "reason": "negative_claim",
        "event_claim_key": claim.claim_key,
        "event_claim_text": claim.claim_text,
        "details": {
            "claim_type": claim.claim_type,
            "claim_order": claim.claim_order,
            "event_where": event.extracted_where,
            "event_when": extracted_when.isoformat() if extracted_when is not None else None,
        },
    }


def _deduplicated_impact_diagnostic(
    *,
    kept: _SelectedImpact,
    suppressed: _SelectedImpact,
    trend_id: str,
    signal_type: str,
) -> dict[str, Any]:
    return {
        "reason": "duplicate_event_indicator",
        "trend_id": trend_id,
        "signal_type": signal_type,
        "event_claim_key": suppressed.impact["event_claim_key"],
        "event_claim_text": suppressed.impact["event_claim_text"],
        "details": {
            "kept_event_claim_key": kept.impact["event_claim_key"],
            "kept_event_claim_text": kept.impact["event_claim_text"],
            "kept_score": kept.score,
            "suppressed_score": suppressed.score,
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
