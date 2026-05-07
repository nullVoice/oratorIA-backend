"""Authentication routes — wires the fastapi-users routers.

The four sub-routers are mounted at the same prefix this router
will be included with (`/api/v1/auth`). Resulting endpoints:

    POST /api/v1/auth/register
    POST /api/v1/auth/login
    POST /api/v1/auth/logout
    POST /api/v1/auth/forgot-password
    POST /api/v1/auth/reset-password
    POST /api/v1/auth/request-verify-token
    POST /api/v1/auth/verify
"""

from __future__ import annotations

from fastapi import APIRouter

from oratoria.core.security import auth_backend, fastapi_users
from oratoria.schemas.user import UserCreate, UserRead

router = APIRouter()

# POST /register
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))

# POST /login, POST /logout
router.include_router(fastapi_users.get_auth_router(auth_backend))

# POST /forgot-password, POST /reset-password
router.include_router(fastapi_users.get_reset_password_router())

# POST /request-verify-token, POST /verify
router.include_router(fastapi_users.get_verify_router(UserRead))
