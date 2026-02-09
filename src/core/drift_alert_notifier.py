"""
Webhook delivery for calibration drift alerts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


class DriftAlertWebhookNotifier:
    """Deliver drift alerts to an optional webhook endpoint."""

    def __init__(
        self,
        *,
        webhook_url: str | None,
        timeout_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.transport = transport

    @classmethod
    def from_settings(cls) -> DriftAlertWebhookNotifier:
        return cls(
            webhook_url=settings.CALIBRATION_DRIFT_WEBHOOK_URL,
            timeout_seconds=settings.CALIBRATION_DRIFT_WEBHOOK_TIMEOUT_SECONDS,
            max_retries=settings.CALIBRATION_DRIFT_WEBHOOK_MAX_RETRIES,
            backoff_seconds=settings.CALIBRATION_DRIFT_WEBHOOK_BACKOFF_SECONDS,
        )

    async def notify(
        self,
        *,
        trend_scope: str,
        generated_at: datetime,
        alerts: list[dict[str, Any]],
    ) -> bool:
        if not self.webhook_url or not alerts:
            return False

        payload = {
            "event_type": "calibration_drift_alerts",
            "generated_at": generated_at.isoformat(),
            "trend_scope": trend_scope,
            "alert_count": len(alerts),
            "alerts": alerts,
        }
        max_attempts = self.max_retries + 1

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.post(self.webhook_url, json=payload)
                    response.raise_for_status()
                logger.info(
                    "Calibration drift webhook delivered",
                    webhook_url=self.webhook_url,
                    trend_scope=trend_scope,
                    alert_count=len(alerts),
                    attempts=attempt + 1,
                )
                return True
            except httpx.HTTPStatusError as exc:
                retryable = self._is_retryable_status(exc.response.status_code)
                error_message = f"http_status={exc.response.status_code}"
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                retryable = True
                error_message = str(exc)

            is_last_attempt = attempt + 1 >= max_attempts
            if not retryable or is_last_attempt:
                logger.warning(
                    "Calibration drift webhook delivery failed",
                    webhook_url=self.webhook_url,
                    trend_scope=trend_scope,
                    alert_count=len(alerts),
                    attempts=attempt + 1,
                    max_attempts=max_attempts,
                    retryable=retryable,
                    error=error_message,
                )
                return False

            delay_seconds = self._backoff_seconds(attempt)
            logger.debug(
                "Retrying calibration drift webhook delivery",
                webhook_url=self.webhook_url,
                trend_scope=trend_scope,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                next_delay_seconds=delay_seconds,
            )
            await asyncio.sleep(delay_seconds)

        return False

    def _backoff_seconds(self, attempt: int) -> float:
        if self.backoff_seconds <= 0:
            return 0.0
        return float(min(self.backoff_seconds * (2**attempt), 60.0))

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500
