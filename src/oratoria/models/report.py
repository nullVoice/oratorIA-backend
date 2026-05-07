"""Evaluation report model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_reports_score_range"),
    )

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
    paraverbal_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    next_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    pdf_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="report")
