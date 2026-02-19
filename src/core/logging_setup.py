"""
Structured logging configuration.
"""

from __future__ import annotations

import logging

import structlog

from src.core.config import settings


def configure_logging() -> None:
    """Configure stdlib and structlog processors."""
    level_name = settings.effective_log_level.upper()
    level_value = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level_value,
        format="%(message)s",
    )

    renderer: structlog.types.Processor
    if settings.LOG_FORMAT == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            level_value,
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
