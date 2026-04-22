"""Helpers for Decimal-backed ORM boundaries."""

from __future__ import annotations

from decimal import Decimal

__all__ = ["Decimal", "to_decimal"]


def to_decimal(value: Decimal | float | int | str) -> Decimal:
    """Normalize common numeric inputs to Decimal without losing scale."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
