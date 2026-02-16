"""
LLM chat completion failover helpers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from src.processing.llm_invocation_adapter import create_route_completion

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class LLMChatRoute:
    """One provider/model route for chat completion calls."""

    provider: str
    model: str
    client: Any
    api_mode: str = "chat_completions"
    request_overrides: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class LLMChatRetryPolicy:
    """Retry controls for one LLM route before failover."""

    max_attempts: int = 2
    backoff_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            msg = "LLM retry policy requires max_attempts >= 1"
            raise ValueError(msg)
        if self.backoff_seconds < 0:
            msg = "LLM retry policy requires backoff_seconds >= 0"
            raise ValueError(msg)


class LLMInvocationErrorCode(StrEnum):
    RATE_LIMIT = "rate_limit"
    PROVIDER_HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    CONNECTION = "connection_error"
    NON_RETRYABLE = "non_retryable"


@dataclass(slots=True, frozen=True)
class LLMInvocationError:
    code: LLMInvocationErrorCode
    retryable: bool
    status_code: int | None = None


class LLMChatFailoverInvoker:
    """Invoke chat completions with optional fallback route."""

    def __init__(
        self,
        *,
        stage: str,
        primary: LLMChatRoute,
        secondary: LLMChatRoute | None = None,
        retry_policy: LLMChatRetryPolicy | None = None,
    ) -> None:
        self.stage = stage
        self.primary = primary
        self.secondary = secondary
        self.retry_policy = retry_policy or LLMChatRetryPolicy()

    async def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> tuple[Any, str]:
        response, primary_attempts, primary_error = await self._create_with_route_retries(
            route=self.primary,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )
        if primary_error is None:
            return (response, self.primary.model)
        if self.secondary is None or not self.is_retryable_error(primary_error):
            raise primary_error

        logger.warning(
            "LLM failover activated",
            stage=self.stage,
            reason=self._error_reason(primary_error),
            primary_provider=self.primary.provider,
            primary_model=self.primary.model,
            secondary_provider=self.secondary.provider,
            secondary_model=self.secondary.model,
            primary_attempts=primary_attempts,
            primary_max_attempts=self.retry_policy.max_attempts,
        )
        (
            secondary_response,
            secondary_attempts,
            secondary_error,
        ) = await self._create_with_route_retries(
            route=self.secondary,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )
        if secondary_error is None:
            return (secondary_response, self.secondary.model)

        logger.warning(
            "LLM failover route failed",
            stage=self.stage,
            secondary_provider=self.secondary.provider,
            secondary_model=self.secondary.model,
            reason=self._error_reason(secondary_error),
            secondary_attempts=secondary_attempts,
            secondary_max_attempts=self.retry_policy.max_attempts,
        )
        raise secondary_error

    async def _create_with_route_retries(
        self,
        *,
        route: LLMChatRoute,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> tuple[Any | None, int, Exception | None]:
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                response = await self._create_for_route(
                    route=route,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                )
                return (response, attempt, None)
            except Exception as exc:
                should_retry = self.is_retryable_error(exc)
                if not should_retry or attempt >= self.retry_policy.max_attempts:
                    return (None, attempt, exc)

                backoff_seconds = round(self.retry_policy.backoff_seconds * attempt, 4)
                logger.warning(
                    "LLM route retry scheduled",
                    stage=self.stage,
                    provider=route.provider,
                    model=route.model,
                    reason=self._error_reason(exc),
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=self.retry_policy.max_attempts,
                    backoff_seconds=backoff_seconds,
                )
                if backoff_seconds > 0:
                    await asyncio.sleep(backoff_seconds)
        return (
            None,
            self.retry_policy.max_attempts,
            RuntimeError("LLM route retry loop exhausted"),
        )

    async def _create_for_route(
        self,
        *,
        route: LLMChatRoute,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> Any:
        return await create_route_completion(
            route=route,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )

    @staticmethod
    def is_retryable_error(exc: Exception) -> bool:
        return LLMChatFailoverInvoker.classify_error(exc).retryable

    @staticmethod
    def classify_error(exc: Exception) -> LLMInvocationError:
        if isinstance(exc, RateLimitError):
            return LLMInvocationError(
                code=LLMInvocationErrorCode.RATE_LIMIT,
                retryable=True,
                status_code=429,
            )
        if isinstance(exc, APITimeoutError | TimeoutError):
            return LLMInvocationError(code=LLMInvocationErrorCode.TIMEOUT, retryable=True)
        if isinstance(exc, APIConnectionError | ConnectionError):
            return LLMInvocationError(code=LLMInvocationErrorCode.CONNECTION, retryable=True)
        if isinstance(exc, APIStatusError):
            status_code = int(getattr(exc, "status_code", 0) or 0)
            if status_code == 429:
                return LLMInvocationError(
                    code=LLMInvocationErrorCode.RATE_LIMIT,
                    retryable=True,
                    status_code=status_code,
                )
            if status_code >= 500:
                return LLMInvocationError(
                    code=LLMInvocationErrorCode.PROVIDER_HTTP_5XX,
                    retryable=True,
                    status_code=status_code,
                )
            return LLMInvocationError(
                code=LLMInvocationErrorCode.NON_RETRYABLE,
                retryable=False,
                status_code=status_code,
            )

        status_code_optional: int | None = LLMChatFailoverInvoker._extract_status_code(exc)
        if status_code_optional == 429:
            return LLMInvocationError(
                code=LLMInvocationErrorCode.RATE_LIMIT,
                retryable=True,
                status_code=status_code_optional,
            )
        if status_code_optional is not None and status_code_optional >= 500:
            return LLMInvocationError(
                code=LLMInvocationErrorCode.PROVIDER_HTTP_5XX,
                retryable=True,
                status_code=status_code_optional,
            )
        if isinstance(exc, TimeoutError):
            return LLMInvocationError(code=LLMInvocationErrorCode.TIMEOUT, retryable=True)
        if isinstance(exc, ConnectionError):
            return LLMInvocationError(code=LLMInvocationErrorCode.CONNECTION, retryable=True)
        return LLMInvocationError(code=LLMInvocationErrorCode.NON_RETRYABLE, retryable=False)

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        raw_status = getattr(exc, "status_code", None)
        if isinstance(raw_status, int):
            return raw_status
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    @staticmethod
    def _error_reason(exc: Exception) -> str:
        return str(LLMChatFailoverInvoker.classify_error(exc).code)
