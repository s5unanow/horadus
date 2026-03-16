from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

import src.workers.tasks as tasks_module
from src.processing.pipeline_retry import RetryablePipelineError

pytestmark = pytest.mark.unit


def _session_maker(session: object):
    @asynccontextmanager
    async def _manager():
        yield session

    return _manager


@pytest.mark.asyncio
async def test_process_pending_async_propagates_retryable_failure_without_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = AsyncMock()

    class FakeTier2Classifier:
        def __init__(self, *, session, model) -> None:
            self.session = session
            self.model = model

    class FakePipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            self.session = session
            self.tier2_classifier = tier2_classifier
            self.degraded_llm_tracker = degraded_llm_tracker

        async def process_pending_items(self, *, limit: int):
            raise RetryablePipelineError(
                item_id=None,
                stage="post_tier1",
                reason="TimeoutError",
                exc=TimeoutError(f"retry limit={limit}"),
            )

    monkeypatch.setattr(tasks_module, "async_session_maker", _session_maker(mock_session))
    monkeypatch.setattr(tasks_module.settings, "LLM_DEGRADED_MODE_ENABLED", False)
    monkeypatch.setattr(tasks_module, "Tier2Classifier", FakeTier2Classifier)
    monkeypatch.setattr(tasks_module, "ProcessingPipeline", FakePipeline)

    with pytest.raises(RetryablePipelineError, match="post_tier1"):
        await tasks_module._process_pending_async(limit=4)

    assert mock_session.commit.await_count == 0


def test_retryable_pipeline_error_is_a_connection_error() -> None:
    assert issubclass(RetryablePipelineError, ConnectionError)
