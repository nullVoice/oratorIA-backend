"""Transcript model — one full document per session, with vector embedding."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session


class Transcript(Base):
    __tablename__ = "transcripts"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(default="es", nullable=False)
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="transcript")
