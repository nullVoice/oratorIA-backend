"""User DTOs."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    locale: str = "es"
    segment: str | None = None
    is_active: bool = True
    is_verified: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    locale: str | None = None
    segment: str | None = None
