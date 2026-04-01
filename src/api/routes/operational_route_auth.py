"""Shared privileged-route helpers for operational endpoints."""

from __future__ import annotations

from fastapi import Depends

from src.api.middleware.auth import require_production_privileged_access

AUTHORIZE_HEALTH_STATUS = Depends(require_production_privileged_access("ops.read_health"))
AUTHORIZE_HEALTH_READINESS = Depends(require_production_privileged_access("ops.read_readiness"))
AUTHORIZE_METRICS = Depends(require_production_privileged_access("ops.read_metrics"))
