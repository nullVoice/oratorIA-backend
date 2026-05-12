"""Avatar (Tavus) conversation model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session


class AvatarConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    ERROR = "error"


class AvatarConversation(Base):
    __tablename__ = "avatar_conversations"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), default="tavus", nullable=False)
    provider_conversation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    conversation_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    replica_id: Mapped[str] = mapped_column(String(64), nullable=False)
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False)
    interactive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[AvatarConversationStatus] = mapped_column(
        Enum(
            AvatarConversationStatus,
            name="avatar_conversation_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=AvatarConversationStatus.ACTIVE,
        index=True,
    )
    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped["Session"] = relationship(back_populates="avatar_conversations")
