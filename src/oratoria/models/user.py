"""User model — integrated with fastapi-users."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session
    from oratoria.models.subscription import Subscription


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="es", nullable=False)
    segment: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # educational | corporate | hr | individual

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
