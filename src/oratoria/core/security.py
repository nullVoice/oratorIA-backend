"""Security primitives: password hashing, JWT helpers, fastapi-users wiring."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.schemas import BaseUserCreate
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from oratoria.config import settings
from oratoria.database import get_db
from oratoria.models.user import User

logger = logging.getLogger(__name__)


# ----------------------------- Password hashing -----------------------------

# bcrypt rejects passwords longer than 72 bytes — truncate explicitly
# so we never raise on a long password from a user.
_BCRYPT_MAX_BYTES = 72


def _truncate(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_truncate(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


# --------------------------------- JWT helpers ------------------------------


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expires_minutes)
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


# --------------------------- fastapi-users wiring ---------------------------


async def get_user_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """Yields the SQLAlchemy user-DB adapter fastapi-users expects."""
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """fastapi-users `UserManager` wired to our settings.

    Hooks (`on_after_register`, `on_after_login`, …) can be overridden as
    auth flows mature; for now they only emit structured log lines.
    """

    reset_password_token_secret = settings.jwt_secret.get_secret_value()
    verification_token_secret = settings.jwt_secret.get_secret_value()

    async def validate_password(
        self,
        password: str,
        user: User | BaseUserCreate,
    ) -> None:
        """No password policy: accept anything.

        Registration only fails if the account already exists (fastapi-users
        returns 400 REGISTER_USER_ALREADY_EXISTS for that). Any non-empty
        password is accepted here.
        """
        return None

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        logger.info("user.registered id=%s email=%s", user.id, user.email)

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: Any | None = None,
    ) -> None:
        logger.info("user.login id=%s email=%s", user.id, user.email)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# Bearer + JWT auth backend.
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.jwt_secret.get_secret_value(),
        lifetime_seconds=settings.jwt_access_token_expires_minutes * 60,
        algorithm=settings.jwt_algorithm,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Convenience dependencies for routes downstream.
current_active_user = fastapi_users.current_user(active=True)
current_active_verified_user = fastapi_users.current_user(active=True, verified=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
