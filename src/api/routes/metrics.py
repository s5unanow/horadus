"""
Prometheus metrics endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.core.observability import (
    CALIBRATION_DRIFT_ALERTS_TOTAL,
    INGESTION_ITEMS_TOTAL,
    LLM_API_CALLS_TOTAL,
    LLM_ESTIMATED_COST_USD_TOTAL,
    WORKER_ERRORS_TOTAL,
)

router = APIRouter()

_REGISTERED_METRICS = (
    INGESTION_ITEMS_TOTAL,
    LLM_API_CALLS_TOTAL,
    LLM_ESTIMATED_COST_USD_TOTAL,
    WORKER_ERRORS_TOTAL,
    CALIBRATION_DRIFT_ALERTS_TOTAL,
)


@router.get("/metrics", include_in_schema=False)
async def get_metrics() -> Response:
    """Expose Prometheus metrics in text format."""
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
