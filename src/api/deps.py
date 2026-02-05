"""
Shared FastAPI dependencies.

Centralizes dependency aliases to keep route signatures concise.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

# Reusable dependency alias for async DB sessions in API routes.
DBSession = Annotated[AsyncSession, Depends(get_session)]
