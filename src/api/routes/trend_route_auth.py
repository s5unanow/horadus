"""Shared privileged-route authorization helpers for trend endpoints."""

from __future__ import annotations

from fastapi import Depends

from src.api.middleware.auth import require_privileged_access

AUTHORIZE_TREND_CREATE = Depends(require_privileged_access("trends.create"))
AUTHORIZE_TREND_DELETE = Depends(require_privileged_access("trends.delete"))
AUTHORIZE_TREND_OUTCOME = Depends(require_privileged_access("trends.record_outcome"))
AUTHORIZE_TREND_SYNC = Depends(require_privileged_access("trends.sync_config"))
AUTHORIZE_TREND_UPDATE = Depends(require_privileged_access("trends.update"))
