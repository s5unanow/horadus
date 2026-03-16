"""Shared privileged-route authorization helpers for trend endpoints."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from src.api.middleware.auth import (
    audit_privileged_action,
    require_privileged_access,
    verify_privileged_access,
)

AUTHORIZE_TREND_CREATE = Depends(require_privileged_access("trends.create"))
AUTHORIZE_TREND_DELETE = Depends(require_privileged_access("trends.delete"))
AUTHORIZE_TREND_OUTCOME = Depends(require_privileged_access("trends.record_outcome"))
AUTHORIZE_TREND_SYNC = Depends(require_privileged_access("trends.sync_config"))
AUTHORIZE_TREND_UPDATE = Depends(require_privileged_access("trends.update"))


def authorize_sync_from_config_request(request: Request) -> None:
    """Require privileged access for the mutating list wrapper path."""
    try:
        verify_privileged_access(request)
    except HTTPException as exc:
        audit_privileged_action(
            request=request,
            action="trends.sync_config",
            outcome="denied",
            detail=str(exc.detail),
        )
        raise
    audit_privileged_action(
        request=request,
        action="trends.sync_config",
        outcome="authorized",
        detail="sync_from_config query flag",
    )
