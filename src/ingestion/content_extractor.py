"""
Wrapper around Trafilatura extraction.
"""

from __future__ import annotations

import trafilatura


class ContentExtractor:
    """Extracts main article text from raw HTML."""

    @staticmethod
    def extract_text(html: str) -> str | None:
        """
        Extract readable article content from HTML.
        """
        extracted = trafilatura.extract(
            html,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if not extracted:
            return None
        normalized = " ".join(extracted.split())
        return normalized or None
