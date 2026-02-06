from __future__ import annotations

import pytest

from src.ingestion.content_extractor import ContentExtractor

pytestmark = pytest.mark.unit


def test_extract_text_normalizes_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ingestion.content_extractor.trafilatura.extract",
        lambda *_args, **_kwargs: "  line 1 \n  line 2  ",
    )

    assert ContentExtractor.extract_text("<html></html>") == "line 1 line 2"


def test_extract_text_returns_none_when_not_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ingestion.content_extractor.trafilatura.extract",
        lambda *_args, **_kwargs: None,
    )

    assert ContentExtractor.extract_text("<html></html>") is None
