"""Progress DTOs."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    period: str
    sessions_count: int
    average_score: int | None
    metrics: dict[str, Any]
