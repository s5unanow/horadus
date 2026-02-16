"""
Deterministic narrative grounding checks against structured evidence payloads.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_NUMERIC_TOKEN_PATTERN = re.compile(r"(?<!\w)-?\d[\d,]*(?:\.\d+)?%?(?!\w)")


@dataclass(frozen=True, slots=True)
class NarrativeGroundingEvaluation:
    is_grounded: bool
    violation_count: int
    unsupported_claims: tuple[str, ...]


def _parse_numeric_token(token: str) -> tuple[float, bool] | None:
    normalized = token.strip()
    is_percent = normalized.endswith("%")
    if is_percent:
        normalized = normalized[:-1]
    normalized = normalized.replace(",", "")
    try:
        value = float(normalized)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return (value, is_percent)


def _collect_payload_numbers(value: Any, into: list[float]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int | float):
        numeric = float(value)
        if math.isfinite(numeric):
            into.append(numeric)
        return
    if isinstance(value, str):
        for match in _NUMERIC_TOKEN_PATTERN.finditer(value):
            parsed = _parse_numeric_token(match.group(0))
            if parsed is None:
                continue
            numeric_value, is_percent = parsed
            into.append(numeric_value / 100.0 if is_percent else numeric_value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_payload_numbers(nested, into)
        return
    if isinstance(value, list | tuple):
        for nested in value:
            _collect_payload_numbers(nested, into)


def _expand_payload_values(payload_values: list[float]) -> list[float]:
    expanded: list[float] = []
    for value in payload_values:
        expanded.append(value)
        if 0.0 <= value <= 1.0:
            expanded.append(value * 100.0)
    return expanded


def evaluate_narrative_grounding(
    *,
    narrative: str,
    evidence_payload: dict[str, Any],
    violation_threshold: int = 0,
    numeric_tolerance: float = 0.05,
) -> NarrativeGroundingEvaluation:
    payload_numbers: list[float] = []
    _collect_payload_numbers(evidence_payload, payload_numbers)
    allowed_values = _expand_payload_values(payload_numbers)

    unsupported_claims: list[str] = []
    for match in _NUMERIC_TOKEN_PATTERN.finditer(narrative):
        token = match.group(0)
        parsed = _parse_numeric_token(token)
        if parsed is None:
            continue
        numeric_value, is_percent = parsed
        candidate_values = [numeric_value]
        if is_percent:
            candidate_values.append(numeric_value / 100.0)

        matched = False
        for candidate in candidate_values:
            if any(abs(candidate - allowed) <= numeric_tolerance for allowed in allowed_values):
                matched = True
                break
        if matched:
            continue
        if token not in unsupported_claims:
            unsupported_claims.append(token)

    violations = len(unsupported_claims)
    return NarrativeGroundingEvaluation(
        is_grounded=violations <= max(0, violation_threshold),
        violation_count=violations,
        unsupported_claims=tuple(unsupported_claims),
    )


def build_grounding_references(
    evaluation: NarrativeGroundingEvaluation,
) -> dict[str, Any] | None:
    if not evaluation.unsupported_claims:
        return None
    return {"unsupported_claims": list(evaluation.unsupported_claims)}
