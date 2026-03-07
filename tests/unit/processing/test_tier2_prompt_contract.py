from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROMPT_PATH = Path("ai/prompts/tier2_classify.md")


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def test_tier2_prompt_requires_specific_supported_signal_or_abstention() -> None:
    prompt = _load_prompt()

    assert "Choose the most specific supported `signal_type`" in prompt
    assert "omit that impact instead of forcing the closest keyword match" in prompt
    assert "Do not infer missing actors, dates, locations, or impacts." in prompt


def test_tier2_prompt_calibrates_ambiguous_signal_pairs() -> None:
    prompt = _load_prompt().lower()

    assert "military_movement" in prompt
    assert "military_incident" in prompt
    assert "weapons_transfer" in prompt
    assert "hostile contact" in prompt
    assert "troop repositioning" in prompt or "force posture" in prompt
