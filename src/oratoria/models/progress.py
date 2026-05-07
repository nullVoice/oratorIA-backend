"""Daily user progress snapshot (time-series, one row per (user, date))."""

from __future__ import annotations

import uuid
from datetime import date as date_

from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from oratoria.models.base import Base


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_progress_user_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_filler_words: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_words_per_minute: Mapped[float | None] = mapped_column(Float, nullable=True)
