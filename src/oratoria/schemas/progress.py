"""Progress DTOs."""

from __future__ import annotations

import uuid
from datetime import date as date_

from pydantic import BaseModel, ConfigDict


class ProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    date: date_
    sessions_count: int
    avg_score: float | None
    total_filler_words: int
    avg_words_per_minute: float | None
