"""Evaluation report model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session


class Report(Base):
    __tablename__ = "reports"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    strengths: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    improvements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    paraverbal_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recommended_next_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(nullable=True)

    # Paraverbal headline metrics (denormalized for sorting/filtering)
    words_per_minute: Mapped[float | None] = mapped_column(Float, nullable=True)
    filler_words_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pause_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    tone_variance: Mapped[float | None] = mapped_column(Float, nullable=True)

    pdf_url: Mapped[str | None] = mapped_column(nullable=True)

    session: Mapped["Session"] = relationship(back_populates="report")
