"""UserManager.validate_password policy (registration / reset)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi_users.exceptions import InvalidPasswordException

from oratoria.core.security import UserManager


def _manager() -> UserManager:
    return UserManager(MagicMock())


def _user(email: str = "alguien@correo.com") -> MagicMock:
    u = MagicMock()
    u.email = email
    return u


async def test_rejects_too_short_password():
    with pytest.raises(InvalidPasswordException):
        await _manager().validate_password("123", _user())


async def test_rejects_password_over_128_chars():
    with pytest.raises(InvalidPasswordException):
        await _manager().validate_password("a" * 129, _user())


async def test_rejects_password_containing_email_local_part():
    with pytest.raises(InvalidPasswordException):
        await _manager().validate_password("juanperez2026", _user("juanperez@x.com"))


async def test_accepts_valid_password():
    # Should not raise.
    await _manager().validate_password("ClaveSegura2026", _user())
