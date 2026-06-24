"""Tests that TavusService.create_conversation sends the correct POST body.

The `layers` field was deliberately removed (see src/oratoria/services/avatar/tavus.py
lines 91-98). Per tavus_docs.md the BYO/custom LLM config lives on the Persona, NOT
on the conversation. These tests verify the correct current contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestTavusConversationContract:
    """TavusService.create_conversation POST body matches the Tavus API contract."""

    def _make_mock_client(self, captured_body: dict) -> MagicMock:
        """Return a mock httpx.AsyncClient context manager that captures the POST body."""

        async def mock_post(path, json=None, **kwargs):
            if json is not None:
                captured_body.update(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "conversation_id": "conv-123",
                "conversation_url": "https://daily.co/room/123",
                "status": "active",
            }
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = mock_post
        return mock_client

    def _base_mock_settings(self) -> MagicMock:
        s = MagicMock()
        s.tavus_api_key.get_secret_value.return_value = "test-key"
        s.tavus_api_base_url = "https://tavusapi.com/v2"
        s.tavus_callback_base_url = "https://api.oratoria.app"
        s.persona_llm_secret = None
        return s

    async def test_no_layers_field_sent(self):
        """The POST body to /conversations must NOT contain a `layers` key.

        The BYO/custom LLM config lives on the Tavus Persona, not on the
        conversation request. Injecting `layers` here would override the
        Persona's LLM config unnecessarily.
        """
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
                session_id="session-abc-123",
            )

        assert "layers" not in captured, (
            "layers MUST NOT be sent — LLM config belongs on the Tavus Persona"
        )

    async def test_conversational_context_carries_brief(self):
        """The per-session brief is delivered via `conversational_context`, not layers.llm.

        This is the correct way to pass session-specific context to the Tavus-hosted LLM
        on the Persona.
        """
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        ctx_text = "This is a pitch session for a business audience"
        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="persona-abc",
                replica_id="replica-xyz",
                conversational_context=ctx_text,
                session_id="session-abc-123",
            )

        assert captured.get("conversational_context") == ctx_text
        assert captured.get("persona_id") == "persona-abc"
        assert captured.get("replica_id") == "replica-xyz"
        assert "layers" not in captured

    async def test_required_fields_always_present(self):
        """persona_id, replica_id, conversational_context, and properties are always sent."""
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
            )

        assert "persona_id" in captured
        assert "replica_id" in captured
        assert "conversational_context" in captured
        props = captured.get("properties", {})
        assert "language" in props
        assert "max_call_duration" in props

    async def test_callback_url_included_only_when_passed(self):
        """callback_url appears in the body only when explicitly provided."""
        from oratoria.services.avatar.tavus import TavusService

        captured_with: dict = {}
        captured_without: dict = {}
        mock_settings = self._base_mock_settings()

        # With callback_url
        client_with = self._make_mock_client(captured_with)
        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=client_with),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
                callback_url="https://api.example.com/webhooks/tavus",
            )

        assert captured_with.get("callback_url") == "https://api.example.com/webhooks/tavus"

        # Without callback_url
        client_without = self._make_mock_client(captured_without)
        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=client_without),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
                # no callback_url
            )

        assert "callback_url" not in captured_without

    async def test_custom_greeting_and_name_included_only_when_passed(self):
        """custom_greeting and conversation_name appear only when provided."""
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
                custom_greeting="Hola, bienvenido.",
                conversation_name="oratoria-session-999",
            )

        assert captured.get("custom_greeting") == "Hola, bienvenido."
        assert captured.get("conversation_name") == "oratoria-session-999"

    async def test_optional_fields_absent_when_not_passed(self):
        """conversation_name and custom_greeting are absent when not provided."""
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
            )

        assert "conversation_name" not in captured
        assert "custom_greeting" not in captured
        assert "layers" not in captured

    async def test_properties_language_and_max_call_duration(self):
        """properties.language and properties.max_call_duration are forwarded correctly."""
        from oratoria.services.avatar.tavus import TavusService

        captured: dict = {}
        mock_settings = self._base_mock_settings()
        mock_client = self._make_mock_client(captured)

        with (
            patch("oratoria.services.avatar.tavus.settings", mock_settings),
            patch("oratoria.services.avatar.tavus.httpx.AsyncClient", return_value=mock_client),
        ):
            service = TavusService(api_key="test-key")
            await service.create_conversation(
                persona_id="p-1",
                replica_id="r-1",
                conversational_context="ctx",
                language="english",
                max_call_duration_seconds=600,
            )

        props = captured.get("properties", {})
        assert props.get("language") == "english"
        assert props.get("max_call_duration") == 600
