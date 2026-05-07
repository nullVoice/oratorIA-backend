"""Report DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    score: int
    summary: str | None
    strengths: list[dict[str, Any]]
    improvements: list[dict[str, Any]]
    paraverbal_metrics: dict[str, Any]
    recommended_next_steps: list[str]
    pdf_url: str | None
    created_at: datetime
