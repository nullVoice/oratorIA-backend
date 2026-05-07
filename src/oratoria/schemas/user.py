"""User Pydantic schemas — extend fastapi-users base schemas with our extras."""

from __future__ import annotations

import uuid

from fastapi_users import schemas as fu_schemas
from pydantic import Field

from oratoria.models.user import UserPlan, UserSegment


class UserRead(fu_schemas.BaseUser[uuid.UUID]):
    """User as returned by the API. Inherits id/email/is_active/is_superuser/is_verified."""

    full_name: str | None = None
    locale: str = "es"
    plan: UserPlan = UserPlan.FREE
    segment: UserSegment | None = None


class UserCreate(fu_schemas.BaseUserCreate):
    """Payload for `POST /auth/register`."""

    full_name: str | None = Field(default=None, max_length=255)
    locale: str = Field(default="es", max_length=10)
    segment: UserSegment | None = None


class UserUpdate(fu_schemas.BaseUserUpdate):
    """Payload for `PATCH /users/me` and admin user edits."""

    full_name: str | None = Field(default=None, max_length=255)
    locale: str | None = Field(default=None, max_length=10)
    segment: UserSegment | None = None
