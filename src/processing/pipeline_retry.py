"""Retryability classification for processing pipeline failures."""

from __future__ import annotations

from uuid import UUID

import httpx

from src.processing.llm_failover import LLMChatFailoverInvoker


class RetryablePipelineError(ConnectionError):
    """Wrap a retryable item-stage failure so task autoretry can handle it."""

    def __init__(
        self,
        *,
        item_id: UUID | None,
        stage: str,
        reason: str,
        exc: Exception,
    ) -> None:
        self.item_id = item_id
        self.stage = stage
        self.reason = reason
        self.original_exception = exc
        item_label = str(item_id) if item_id is not None else "batch"
        super().__init__(
            f"Retryable pipeline failure during {stage} for {item_label} ({reason}): {exc}"
        )


def build_retryable_pipeline_error(
    *,
    item_id: UUID | None,
    stage: str,
    exc: Exception,
) -> RetryablePipelineError | None:
    if isinstance(exc, RetryablePipelineError):
        return exc
    reason = _retryable_reason(exc)
    if reason is None:
        return None
    return RetryablePipelineError(item_id=item_id, stage=stage, reason=reason, exc=exc)


def _retryable_reason(exc: Exception) -> str | None:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = int(exc.response.status_code)
        if status_code == 429 or status_code >= 500:
            return f"http_status_{status_code}"
        return None
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError):
        return type(exc).__name__
    if isinstance(exc, TimeoutError | ConnectionError):
        return type(exc).__name__
    classification = LLMChatFailoverInvoker.classify_error(exc)
    if classification.retryable:
        return str(classification.code.value)
    return None
