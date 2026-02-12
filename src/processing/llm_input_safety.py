"""
Helpers for guarding LLM inputs against injection payloads and context overruns.
"""

from __future__ import annotations

from math import ceil

DEFAULT_CHARS_PER_TOKEN = 4
DEFAULT_TRUNCATION_MARKER = "[TRUNCATED]"


def estimate_tokens(*, text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Approximate token count using a conservative chars-per-token heuristic."""
    safe_chars_per_token = max(1, int(chars_per_token))
    if not text:
        return 0
    return max(1, ceil(len(text) / safe_chars_per_token))


def truncate_to_token_limit(
    *,
    text: str,
    max_tokens: int,
    marker: str = DEFAULT_TRUNCATION_MARKER,
    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN,
) -> str:
    """Truncate text to an approximate token budget with an explicit marker."""
    normalized = text.strip()
    if max_tokens <= 0:
        return marker
    if not normalized:
        return normalized
    if estimate_tokens(text=normalized, chars_per_token=chars_per_token) <= max_tokens:
        return normalized

    max_chars = max_tokens * max(1, int(chars_per_token))
    if max_chars <= len(marker):
        return marker
    keep_chars = max(1, max_chars - len(marker) - 1)
    truncated = normalized[:keep_chars].rstrip()
    return f"{truncated} {marker}".strip()


def wrap_untrusted_text(*, text: str, tag: str) -> str:
    """Delimit untrusted text so prompts can treat it as data only."""
    safe_tag = tag.strip().upper().replace("-", "_")
    normalized = text.strip()
    return f"<{safe_tag}>\n{normalized}\n</{safe_tag}>"
