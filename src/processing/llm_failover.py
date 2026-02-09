"""
LLM chat completion failover helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class LLMChatRoute:
    """One provider/model route for chat completion calls."""

    provider: str
    model: str
    client: Any


class LLMChatFailoverInvoker:
    """Invoke chat completions with optional fallback route."""

    def __init__(
        self,
        *,
        stage: str,
        primary: LLMChatRoute,
        secondary: LLMChatRoute | None = None,
    ) -> None:
        self.stage = stage
        self.primary = primary
        self.secondary = secondary

    async def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, str],
    ) -> tuple[Any, str]:
        try:
            response = await self._create_for_route(
                route=self.primary,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )
            return (response, self.primary.model)
        except Exception as exc:
            if self.secondary is None or not self.is_retryable_error(exc):
                raise

            logger.warning(
                "LLM failover activated",
                stage=self.stage,
                reason=self._error_reason(exc),
                primary_provider=self.primary.provider,
                primary_model=self.primary.model,
                secondary_provider=self.secondary.provider,
                secondary_model=self.secondary.model,
            )
            try:
                response = await self._create_for_route(
                    route=self.secondary,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                )
                return (response, self.secondary.model)
            except Exception as secondary_exc:
                logger.warning(
                    "LLM failover route failed",
                    stage=self.stage,
                    secondary_provider=self.secondary.provider,
                    secondary_model=self.secondary.model,
                    reason=self._error_reason(secondary_exc),
                )
                raise

    async def _create_for_route(
        self,
        *,
        route: LLMChatRoute,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, str],
    ) -> Any:
        return await route.client.chat.completions.create(
            model=route.model,
            temperature=temperature,
            response_format=response_format,
            messages=messages,
        )

    @staticmethod
    def is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, RateLimitError | APITimeoutError | APIConnectionError):
            return True
        if isinstance(exc, APIStatusError):
            status_code = int(getattr(exc, "status_code", 0) or 0)
            return status_code == 429 or status_code >= 500

        status_code_optional: int | None = LLMChatFailoverInvoker._extract_status_code(exc)
        if status_code_optional is not None:
            return status_code_optional == 429 or status_code_optional >= 500

        return isinstance(exc, TimeoutError | ConnectionError)

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
        status_code = LLMChatFailoverInvoker._extract_status_code(exc)
        if status_code == 429:
            return "rate_limit"
        if status_code is not None and status_code >= 500:
            return "http_5xx"
        if isinstance(exc, APITimeoutError | TimeoutError):
            return "timeout"
        if isinstance(exc, APIConnectionError | ConnectionError):
            return "connection_error"
        return type(exc).__name__
