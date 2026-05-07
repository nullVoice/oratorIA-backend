"""Audit log of significant actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from oratoria.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Stored as String to allow non-UUID identifiers (e.g. external Stripe IDs
    # like `cus_abc123`). When the resource is internal, it's a UUID rendered
    # as text.
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The Python attribute is `metadata_` to avoid clashing with SQLAlchemy's
    # `Base.metadata`. The actual Postgres column is named `metadata`.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
