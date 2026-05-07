"""Session DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    type: str = Field(pattern="^(live|async)$")
    title: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    status: str
    title: str | None
    context: dict[str, Any]
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
