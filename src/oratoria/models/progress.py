"""User progress snapshots over time."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from oratoria.models.base import Base


class Progress(Base):
    __tablename__ = "progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period: Mapped[str] = mapped_column(nullable=False)  # e.g. "2026-W18", "2026-05"
    sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
