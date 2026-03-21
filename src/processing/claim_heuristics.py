"""Language-specific claim-heuristic constants and helpers."""

# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any

from src.processing.claim_text_analysis import (
    claim_language as detect_claim_language,
)
from src.processing.claim_text_analysis import (
    claim_polarity as detect_claim_polarity,
)
from src.processing.claim_text_analysis import (
    supported_claim_heuristic_languages,
)
from src.processing.event_claims import normalize_claim_text

CLAIM_STOP_WORDS: dict[str, set[str]] = {
    "en": {
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
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "with",
    },
    "uk": {
        "а",
        "або",
        "але",
        "в",
        "від",
        "до",
        "для",
        "з",
        "за",
        "і",
        "й",
        "на",
        "по",
        "про",
        "та",
        "у",
        "це",
        "що",
        "як",
    },
    "ru": {
        "а",
        "без",
        "в",
        "для",
        "до",
        "за",
        "и",
        "или",
        "на",
        "не",
        "о",
        "по",
        "с",
        "также",
        "то",
        "что",
        "это",
    },
}

SUPPORTED_CLAIM_HEURISTIC_LANGUAGES: set[str] = supported_claim_heuristic_languages()


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def build_claim_graph(claims: list[str]) -> dict[str, Any]:
    nodes = [
        {
            "claim_id": f"claim_{index + 1}",
            "text": claim,
            "normalized_text": normalize_claim_text(claim),
        }
        for index, claim in enumerate(claims)
    ]

    links: list[dict[str, str]] = []
    for index, source_node in enumerate(nodes):
        source_text = str(source_node["text"])
        for target_node in nodes[index + 1 :]:
            target_text = str(target_node["text"])
            relation = claim_relation(source_text, target_text)
            if relation is None:
                continue
            links.append(
                {
                    "source_claim_id": str(source_node["claim_id"]),
                    "target_claim_id": str(target_node["claim_id"]),
                    "relation": relation,
                }
            )

    return {"nodes": nodes, "links": links}


def claim_relation(first: str, second: str) -> str | None:
    first_language = claim_language(first)
    second_language = claim_language(second)
    if (
        first_language not in SUPPORTED_CLAIM_HEURISTIC_LANGUAGES
        or second_language not in SUPPORTED_CLAIM_HEURISTIC_LANGUAGES
        or first_language != second_language
    ):
        return None

    first_tokens = claim_tokens(first, language=first_language)
    second_tokens = claim_tokens(second, language=second_language)
    if len(first_tokens.intersection(second_tokens)) < 2:
        return None

    if claim_polarity(first, language=first_language) != claim_polarity(
        second,
        language=second_language,
    ):
        return "contradict"
    return "support"


def claim_tokens(value: str, *, language: str) -> set[str]:
    stop_words = CLAIM_STOP_WORDS.get(language, set())
    normalized = normalize_claim_text(value)
    return {
        token
        for token in normalized.split()
        if token and len(token) > 2 and token not in stop_words
    }


def claim_polarity(value: str, *, language: str) -> str:
    return detect_claim_polarity(value, language=language)


def claim_language(value: str) -> str:
    return detect_claim_language(value)
