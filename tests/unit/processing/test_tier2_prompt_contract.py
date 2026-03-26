from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROMPT_PATH = Path("ai/prompts/tier2_classify.md")


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def test_tier2_prompt_requires_extraction_only_contract() -> None:
    prompt = _load_prompt()

    assert "Make each claim specific enough that deterministic code can later map it" in prompt
    assert '"entities"' in prompt
    assert "canonical-mention list for durable registry linking" in prompt
    assert "Keep `summary`, `extracted_who`, `extracted_what`, and `extracted_where`" in prompt
    assert "Do not infer missing actors, dates, locations, or causal implications." in prompt
    assert '"trend_impacts"' not in prompt


def test_tier2_prompt_excludes_taxonomy_payload_shape() -> None:
    prompt = _load_prompt().lower()

    assert "context_chunks" in prompt
    assert "claims" in prompt
    assert "categories" in prompt
    assert "trends[]" not in prompt
