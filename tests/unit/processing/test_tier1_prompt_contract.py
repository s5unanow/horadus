from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROMPT_PATH = Path("ai/prompts/tier1_filter.md")


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def test_tier1_prompt_defines_score_bands_around_threshold() -> None:
    prompt = _load_prompt()

    assert "The routing threshold is `5`." in prompt
    for band in ("`0-2`", "`3-4`", "`5-6`", "`7-8`", "`9-10`"):
        assert band in prompt
    assert "current real-world operational relevance" in prompt


def test_tier1_prompt_includes_targeted_false_positive_examples() -> None:
    prompt = _load_prompt().lower()

    assert "documentary" in prompt
    assert "historical" in prompt
    assert "video game" in prompt
    assert "fictional" in prompt
    assert "commentary" in prompt
    assert "cold war" in prompt or "2015 military crisis" in prompt


def test_tier1_prompt_includes_positive_current_event_examples() -> None:
    prompt = _load_prompt().lower()

    assert "troops" in prompt
    assert "missiles" in prompt
    assert "sanctions" in prompt
    assert "export controls" in prompt
