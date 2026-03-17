"""Shared SQLAlchemy declarative base for storage models."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
        UUID: PGUUID(as_uuid=True),
    }
