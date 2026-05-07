"""Structured logging configuration."""

from __future__ import annotations

import logging

import structlog

from oratoria.config import settings


def configure_logging() -> None:
    level = logging.DEBUG if settings.debug else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (
                structlog.dev.ConsoleRenderer()
                if not settings.is_production
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
