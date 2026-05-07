"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from oratoria.api.router import api_router
from oratoria.api.ws import ws_router
from oratoria.config import settings
from oratoria.core.events import on_shutdown, on_startup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    await on_startup()
    try:
        yield
    finally:
        await on_shutdown()


def _init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=0.1 if settings.is_production else 1.0,
        )
    except Exception:
        logger.exception("Failed to initialize Sentry")


def _init_langfuse() -> None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]

        Langfuse(
            public_key=settings.langfuse_public_key.get_secret_value(),
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            host=settings.langfuse_host,
        )
    except Exception:
        logger.exception("Failed to initialize Langfuse")


def create_app() -> FastAPI:
    _init_sentry()
    _init_langfuse()

    app = FastAPI(
        title="OratorIA Backend",
        description="AI-powered public speaking coaching platform.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, Any]:
        return {
            "name": "OratorIA Backend",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
