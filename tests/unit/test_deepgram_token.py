"""Unit tests for POST /api/v1/practice/deepgram-token (F2-B-01..04).

Strategy: patch ``oratoria.api.v1.practice.httpx.AsyncClient`` so only the
Deepgram HTTP calls are mocked, leaving the ASGI test transport untouched.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport, Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    """Create a FastAPI test app with DB dependency overridden."""
    from oratoria.main import create_app
    from oratoria.database import get_db

    app = create_app()

    async def override_get_db():
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app


def _override_auth(app, user=None):
    """Inject a fake current_active_user into the app."""
    from oratoria.core.security import current_active_user

    fake = user or MagicMock(id="test-user-id")

    async def _fake_user():
        return fake

    app.dependency_overrides[current_active_user] = _fake_user


def _mock_dg_client(post_side_effect=None, get_side_effect=None):
    """Return a mock that behaves like ``httpx.AsyncClient`` used as async ctx manager."""
    instance = MagicMock()
    instance.post = AsyncMock(side_effect=post_side_effect)
    instance.get = AsyncMock(side_effect=get_side_effect)

    # Make it usable as ``async with httpx.AsyncClient(...) as client:``
    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield instance

    return _ctx, instance


# ---------------------------------------------------------------------------
# F2-B-01: grant-token path succeeds
# ---------------------------------------------------------------------------

class TestDeepgramTokenGrantPath:
    async def test_returns_token_shape_on_grant_success(self):
        """F2-B-01: grant-token 200 → endpoint returns {token, expires_in}."""
        from pydantic import SecretStr

        app = _make_app()
        _override_auth(app)

        mock_settings = MagicMock()
        mock_settings.deepgram_api_key = SecretStr("fake-dg-key")

        grant_response = Response(
            200,
            json={"access_token": "short-lived-token-abc", "expires_in": 30},
        )

        ctx, _inst = _mock_dg_client(post_side_effect=AsyncMock(return_value=grant_response))

        with (
            patch("oratoria.api.v1.practice.settings", mock_settings),
            patch("oratoria.api.v1.practice.httpx.AsyncClient", new=ctx),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/v1/practice/deepgram-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == "short-lived-token-abc"
        assert data["expires_in"] == 30


# ---------------------------------------------------------------------------
# F2-B-02: fallback to management-API temp-key when grant returns 404
# ---------------------------------------------------------------------------

class TestDeepgramTokenTempKeyFallback:
    async def test_falls_back_to_temp_key_when_grant_returns_403(self):
        """F2-B-02: grant 403 → management API temp-key path used."""
        from pydantic import SecretStr

        app = _make_app()
        _override_auth(app)

        mock_settings = MagicMock()
        mock_settings.deepgram_api_key = SecretStr("fake-dg-key")

        grant_403 = Response(403, json={"err_code": "FORBIDDEN"})
        key_created = Response(201, json={"key": "temp-api-key-xyz", "key_id": "kid-1"})
        projects_ok = Response(
            200, json={"projects": [{"project_id": "proj-123", "name": "OratorIA"}]}
        )

        async def mock_post(url, **kwargs):
            if "auth/grant" in url:
                return grant_403
            if "keys" in url:
                return key_created
            return Response(500)

        async def mock_get(url, **kwargs):
            if "projects" in url:
                return projects_ok
            return Response(404)

        ctx, _inst = _mock_dg_client(
            post_side_effect=mock_post,
            get_side_effect=mock_get,
        )

        with (
            patch("oratoria.api.v1.practice.settings", mock_settings),
            patch("oratoria.api.v1.practice.httpx.AsyncClient", new=ctx),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/v1/practice/deepgram-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == "temp-api-key-xyz"
        assert data["expires_in"] == 30

    async def test_direct_key_fallback_when_no_management_scopes(self):
        """F2-B-02b: grant 403 + keys:write 403 → direct key returned."""
        from pydantic import SecretStr

        app = _make_app()
        _override_auth(app)

        mock_settings = MagicMock()
        mock_settings.deepgram_api_key = SecretStr("real-api-key-usage-only")

        grant_403 = Response(403, json={"err_code": "FORBIDDEN"})
        keys_403 = Response(403, json={"category": "INSUFFICIENT_PERMISSIONS"})
        projects_ok = Response(
            200, json={"projects": [{"project_id": "proj-123", "name": "OratorIA"}]}
        )

        async def mock_post(url, **kwargs):
            if "auth/grant" in url:
                return grant_403
            if "keys" in url:
                return keys_403
            return Response(500)

        async def mock_get(url, **kwargs):
            if "projects" in url:
                return projects_ok
            return Response(404)

        ctx, _inst = _mock_dg_client(
            post_side_effect=mock_post,
            get_side_effect=mock_get,
        )

        with (
            patch("oratoria.api.v1.practice.settings", mock_settings),
            patch("oratoria.api.v1.practice.httpx.AsyncClient", new=ctx),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/v1/practice/deepgram-token")

        assert resp.status_code == 200
        data = resp.json()
        # Direct key fallback: the raw key is returned
        assert data["token"] == "real-api-key-usage-only"


# ---------------------------------------------------------------------------
# F2-B-03: auth protection — unauthenticated → 401
# ---------------------------------------------------------------------------

class TestDeepgramTokenAuthProtection:
    async def test_unauthenticated_returns_401(self):
        """F2-B-03: endpoint requires a valid JWT; no auth → 401."""
        # Intentionally do NOT override auth dependency.
        app = _make_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/practice/deepgram-token")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# F2-B-04: missing API key → 503
# ---------------------------------------------------------------------------

class TestDeepgramTokenMissingKey:
    async def test_503_when_deepgram_key_not_configured(self):
        """F2-B-04: DEEPGRAM_API_KEY not set → 503 SERVICE_UNAVAILABLE."""
        app = _make_app()
        _override_auth(app)

        mock_settings = MagicMock()
        mock_settings.deepgram_api_key = None

        with patch("oratoria.api.v1.practice.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/v1/practice/deepgram-token")

        assert resp.status_code == 503
