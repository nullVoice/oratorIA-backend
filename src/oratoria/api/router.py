"""Aggregate v1 routers under /api."""

from __future__ import annotations

from fastapi import APIRouter

from oratoria.api.v1 import (
    auth,
    billing,
    practice,
    progress,
    reports,
    sessions,
    users,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/v1/users", tags=["users"])
api_router.include_router(practice.router, prefix="/v1/practice", tags=["practice"])
api_router.include_router(sessions.router, prefix="/v1/sessions", tags=["sessions"])
api_router.include_router(reports.router, prefix="/v1/reports", tags=["reports"])
api_router.include_router(progress.router, prefix="/v1/progress", tags=["progress"])
api_router.include_router(billing.router, prefix="/v1/billing", tags=["billing"])
api_router.include_router(webhooks.router, prefix="/v1/webhooks", tags=["webhooks"])
