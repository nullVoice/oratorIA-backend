"""Unit tests for POST /api/v1/chat/completions (persona LLM endpoint)."""
from __future__ import annotations

import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock


# ---- Helpers ----

async def collect_sse(response) -> list[dict]:
    """Parse SSE stream from an httpx Response into a list of parsed JSON objects.
    Skips `data: [DONE]` lines.
    """
    chunks = []
    content = response.text
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("data: ") and not line.endswith("[DONE]"):
            try:
                chunks.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return chunks


def make_app_with_overrides(mock_db=None):
    """Create a test app with DB dependency overridden."""
    # Import here to avoid module-level side effects
    from oratoria.main import create_app
    from oratoria.database import get_db

    app = create_app()

    # Always override get_db — there's no real DB in unit tests
    if mock_db is None:
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    return app


# ---- Fixtures ----

@pytest.fixture
def mock_agent_tokens():
    """Returns an async generator that yields 3 tokens."""
    async def _gen(*args, **kwargs):
        for token in ["Hello", " world", "!"]:
            yield token
    return _gen


# ---- Tests ----

class TestPersonaLLMEndpointSSE:
    async def test_sse_shape_and_done_marker(self, mock_agent_tokens):
        """F1-U-01: SSE response has correct OpenAI chunk shape + [DONE]."""
        app = make_app_with_overrides()

        with patch("oratoria.api.v1.persona_llm.PersonaAgent") as MockAgent:
            instance = MagicMock()
            instance.astream_reply = mock_agent_tokens
            MockAgent.return_value = instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
                )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "data: [DONE]" in response.text

        chunks = await collect_sse(response)
        assert len(chunks) >= 1
        # Check first content chunk shape
        for c in chunks:
            assert "choices" in c
            assert "delta" in c["choices"][0]

    async def test_multiple_tokens_appear_as_chunks(self, mock_agent_tokens):
        """F1-U-02: Each yielded token becomes its own SSE chunk."""
        app = make_app_with_overrides()

        with patch("oratoria.api.v1.persona_llm.PersonaAgent") as MockAgent:
            instance = MagicMock()
            instance.astream_reply = mock_agent_tokens
            MockAgent.return_value = instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}]},
                )

        chunks = await collect_sse(response)
        # 3 content chunks + 1 final stop chunk = 4 total (but final has empty delta so content may not be in it)
        content_chunks = [c for c in chunks if c["choices"][0]["delta"].get("content")]
        assert len(content_chunks) == 3
        contents = [c["choices"][0]["delta"]["content"] for c in content_chunks]
        assert contents == ["Hello", " world", "!"]

    async def test_stream_false_returns_single_json(self, mock_agent_tokens):
        """F1-U-03: stream=false returns a single OpenAI chat.completion object."""
        app = make_app_with_overrides()

        with patch("oratoria.api.v1.persona_llm.PersonaAgent") as MockAgent:
            instance = MagicMock()
            instance.astream_reply = mock_agent_tokens
            MockAgent.return_value = instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}], "stream": False},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert "choices" in data
        assert data["choices"][0]["message"]["content"] == "Hello world!"
        assert data["choices"][0]["finish_reason"] == "stop"

    async def test_malformed_body_returns_4xx(self):
        """F1-U-04: Missing required 'messages' field returns 422."""
        app = make_app_with_overrides()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/completions",
                json={"model": "oratoria-persona"},  # missing messages
            )

        assert response.status_code == 422

    async def test_auth_header_missing_returns_401_when_secret_set(self, mocker):
        """When persona_llm_secret is set and header is missing → 401."""
        app = make_app_with_overrides()

        mocker.patch("oratoria.api.v1.persona_llm.settings")
        # We need to simulate settings.persona_llm_secret being set
        from unittest.mock import MagicMock
        from pydantic import SecretStr

        mock_settings = MagicMock()
        mock_settings.persona_llm_secret = SecretStr("mysecret")

        with patch("oratoria.api.v1.persona_llm.settings", mock_settings):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}]},
                    # No X-Oratoria-Persona-Token header
                )

        assert response.status_code == 401

    async def test_auth_header_wrong_returns_401_when_secret_set(self, mocker):
        """When persona_llm_secret is set and header value is wrong → 401."""
        app = make_app_with_overrides()

        from pydantic import SecretStr
        mock_settings = MagicMock()
        mock_settings.persona_llm_secret = SecretStr("mysecret")

        with patch("oratoria.api.v1.persona_llm.settings", mock_settings):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"X-Oratoria-Persona-Token": "wrongsecret"},
                )

        assert response.status_code == 401

    async def test_no_secret_configured_allows_any_request(self, mock_agent_tokens):
        """When persona_llm_secret is None → any request is allowed (dev mode)."""
        app = make_app_with_overrides()

        mock_settings = MagicMock()
        mock_settings.persona_llm_secret = None

        with patch("oratoria.api.v1.persona_llm.PersonaAgent") as MockAgent, \
             patch("oratoria.api.v1.persona_llm.settings", mock_settings):
            instance = MagicMock()
            instance.astream_reply = mock_agent_tokens
            MockAgent.return_value = instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/chat/completions",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}]},
                    # No auth header, no secret set
                )

        assert response.status_code == 200

    async def test_session_id_loads_session_context(self, mock_agent_tokens):
        """When session_id is provided, the endpoint loads the session from DB."""
        import uuid
        session_id = uuid.uuid4()

        # Mock session object
        mock_sess = MagicMock()
        mock_sess.context = {
            "presentation_type": "pitch",
            "audience": "inversores",
            "objective": "captar fondos",
            "formality": "alta",
            "duration_target": 5,
            "segment": "business",
        }
        mock_sess.user_full_name = "Test User"

        # Mock DB
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_sess)

        app = make_app_with_overrides(mock_db=mock_db)

        with patch("oratoria.api.v1.persona_llm.PersonaAgent") as MockAgent, \
             patch("oratoria.api.v1.persona_llm.build_persona_system_prompt") as mock_build:
            mock_build.return_value = "mocked system prompt"
            instance = MagicMock()
            instance.astream_reply = mock_agent_tokens
            MockAgent.return_value = instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/chat/completions?session_id={session_id}",
                    json={"model": "oratoria-persona", "messages": [{"role": "user", "content": "Hi"}]},
                )

        assert response.status_code == 200
        mock_build.assert_called_once()
