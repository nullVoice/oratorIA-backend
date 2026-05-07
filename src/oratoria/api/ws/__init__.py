"""WebSocket endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from oratoria.api.ws import live_session

ws_router = APIRouter()
ws_router.include_router(live_session.router)
