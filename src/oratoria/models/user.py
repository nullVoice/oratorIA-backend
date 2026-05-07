"""User model — integrated with fastapi-users.

Inherits `id`, `email` (unique + indexed), `hashed_password`, `is_active`,
`is_superuser`, `is_verified` from `SQLAlchemyBaseUserTableUUID`.
Inherits `created_at` / `updated_at` from `Base`.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oratoria.models.base import Base

if TYPE_CHECKING:
    from oratoria.models.session import Session
    from oratoria.models.subscription import Subscription


class UserPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    INSTITUTIONAL = "institutional"


class UserSegment(str, enum.Enum):
    EDUCATION = "education"
    BUSINESS = "business"
    HR = "hr"


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="es", nullable=False)
    plan: Mapped[UserPlan] = mapped_column(
        Enum(UserPlan, name="user_plan"),
        default=UserPlan.FREE,
        nullable=False,
    )
    segment: Mapped[UserSegment | None] = mapped_column(
        Enum(UserSegment, name="user_segment"),
        nullable=True,
    )

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
