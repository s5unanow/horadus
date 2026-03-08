from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "src/processing/llm_input_safety.py"
sys.modules.setdefault("src.processing", types.ModuleType("src.processing"))
_SPEC = importlib.util.spec_from_file_location("src.processing.llm_input_safety", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

estimate_tokens = _MODULE.estimate_tokens
truncate_to_token_limit = _MODULE.truncate_to_token_limit
wrap_untrusted_text = _MODULE.wrap_untrusted_text

pytestmark = pytest.mark.unit


def test_estimate_tokens_handles_empty_text_and_low_chars_per_token() -> None:
    assert estimate_tokens(text="") == 0
    assert estimate_tokens(text="abcd", chars_per_token=0) == 4


def test_truncate_to_token_limit_handles_edge_cases() -> None:
    assert truncate_to_token_limit(text="  keep me  ", max_tokens=10) == "keep me"
    assert truncate_to_token_limit(text="anything", max_tokens=0) == "[TRUNCATED]"
    assert truncate_to_token_limit(text="   ", max_tokens=5) == ""
    assert truncate_to_token_limit(text="abcdef", max_tokens=1, chars_per_token=2) == "[TRUNCATED]"
    assert (
        truncate_to_token_limit(
            text="abcdefghijklmnopqrstuvwxyz",
            max_tokens=5,
            chars_per_token=4,
        )
        == "abcdefgh [TRUNCATED]"
    )


def test_wrap_untrusted_text_normalizes_tag_and_body() -> None:
    assert wrap_untrusted_text(text="  body  ", tag="raw-text") == "<RAW_TEXT>\nbody\n</RAW_TEXT>"
