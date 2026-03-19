"""Shared language and polarity heuristics for extracted claims."""

from __future__ import annotations

_SUPPORTED_CLAIM_HEURISTIC_LANGUAGES = {"en", "uk", "ru"}
_CLAIM_NEGATIVE_MARKERS: dict[str, tuple[str, ...]] = {
    "en": (
        " not ",
        " no ",
        " never ",
        " deny",
        " denied",
        " denies",
        " refute",
        " refuted",
        " refutes",
        " false",
        "did not",
        "didn't",
    ),
    "uk": (
        " не ",
        " ніколи ",
        " запереч",
        " спрост",
        " хибн",
        " без ",
    ),
    "ru": (
        " не ",
        " никогда ",
        " отрица",
        " опроверг",
        " ложн",
        " без ",
    ),
}


def supported_claim_heuristic_languages() -> set[str]:
    """Return languages covered by local claim heuristics."""

    return set(_SUPPORTED_CLAIM_HEURISTIC_LANGUAGES)


def claim_polarity(value: str, *, language: str) -> str:
    """Return coarse claim polarity for supported languages."""

    lowered = value.lower()
    negative_markers = _CLAIM_NEGATIVE_MARKERS.get(language, ())
    for marker in negative_markers:
        if marker in f" {lowered} ":
            return "negative"
    return "positive"


def claim_language(value: str) -> str:
    """Infer the dominant language family from claim text."""

    lowered = value.lower()
    has_cyrillic = any("\u0430" <= ch <= "\u044f" or ch == "\u0451" for ch in lowered)
    if has_cyrillic:
        ukrainian_specific = {"\u0456", "\u0457", "\u0454", "\u0491"}
        russian_specific = {"\u044b", "\u044d", "\u044a", "\u0451"}
        if any(ch in ukrainian_specific for ch in lowered):
            return "uk"
        if any(ch in russian_specific for ch in lowered):
            return "ru"
        return "ru"

    has_ascii_letters = any("a" <= ch <= "z" for ch in lowered)
    has_non_ascii_letters = any(ch.isalpha() and not ch.isascii() for ch in lowered)
    if has_ascii_letters and not has_non_ascii_letters:
        return "en"
    return "unknown"
