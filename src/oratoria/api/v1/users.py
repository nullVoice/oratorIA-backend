"""User profile routes — wires the fastapi-users users router.

Mounted at `/api/v1/users` from `api/router.py`. Resulting endpoints:

    GET    /api/v1/users/me              (current_active_user)
    PATCH  /api/v1/users/me              (current_active_user)
    GET    /api/v1/users/{id}            (current_superuser)
    PATCH  /api/v1/users/{id}            (current_superuser)
    DELETE /api/v1/users/{id}            (current_superuser)
"""

from __future__ import annotations

from fastapi import APIRouter

from oratoria.core.security import fastapi_users
from oratoria.schemas.user import UserRead, UserUpdate

router = APIRouter()
router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate))
