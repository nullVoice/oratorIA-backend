"""Application startup/shutdown hooks."""

from __future__ import annotations

import logging

from oratoria.core.logger import configure_logging
from oratoria.database import async_engine

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    configure_logging()
    logger.info("OratorIA backend starting up")


async def on_shutdown() -> None:
    logger.info("OratorIA backend shutting down — disposing DB engine")
    await async_engine.dispose()
