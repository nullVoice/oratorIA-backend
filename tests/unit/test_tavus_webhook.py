"""Unit tests for POST /api/v1/webhooks/tavus.

Tests:
  - application.transcription_ready stores transcript; if conversation ENDED, evaluator runs
  - Signature verification: wrong signature → 401; correct HMAC → 200; no secret → 200
  - Unknown conversation_id → 200 with status "ignored"
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# App / infrastructure helpers
# ---------------------------------------------------------------------------


def _make_app():
    from oratoria.database import get_db
    from oratoria.main import create_app

    app = create_app()

    async def override_get_db():
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app


def _sign(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest — matches _verify_signature in webhooks.py."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _tavus_payload(event_type: str, conversation_id: str, extra: dict | None = None) -> dict:
    payload = {"event_type": event_type, "conversation_id": conversation_id}
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Helpers to build DB mocks that simulate existing AvatarConversation rows
# ---------------------------------------------------------------------------


def _make_convo_row(
    *,
    provider_conversation_id: str,
    status: str = "active",
    transcript: list | None = None,
) -> MagicMock:
    from oratoria.models import AvatarConversationStatus

    row = MagicMock()
    row.provider_conversation_id = provider_conversation_id
    row.status = (
        AvatarConversationStatus.ACTIVE if status == "active" else AvatarConversationStatus.ENDED
    )
    row.transcript = transcript
    row.session_id = uuid.uuid4()
    row.started_at = None
    row.ended_at = None
    row.duration_seconds = None
    row.perception_analysis = None
    return row


def _make_session_row() -> MagicMock:
    from oratoria.models.session import SessionStatus

    sess = MagicMock()
    sess.id = uuid.uuid4()
    sess.status = SessionStatus.IN_PROGRESS
    sess.context = {}
    sess.ended_at = None
    sess.duration_seconds = None
    return sess


def _make_db_that_returns(convo_row, session_row=None):
    """Return an async_session_factory mock that yields a DB yielding the given rows."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=session_row)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    # scalar_one_or_none() returns the convo row
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=convo_row)
    mock_db.execute = AsyncMock(return_value=execute_result)

    # Make it work as async context manager
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)
    return mock_db


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------


class TestTavusWebhookSignatureVerification:
    """Webhook signature verification with TAVUS_WEBHOOK_SECRET."""

    async def test_no_secret_configured_accepts_any_request(self):
        """Dev mode: no TAVUS_WEBHOOK_SECRET → 200 regardless of signature header."""
        app = _make_app()
        convo = _make_convo_row(provider_conversation_id="conv-sig-1")
        mock_db = _make_db_that_returns(convo)

        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        payload = _tavus_payload("some.event", "conv-sig-1")
        body = json.dumps(payload).encode()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                    # No x-tavus-signature header
                )

        assert resp.status_code == 200

    async def test_wrong_signature_returns_401(self):
        """When TAVUS_WEBHOOK_SECRET is set and signature is wrong → 401."""
        from pydantic import SecretStr

        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = SecretStr("my-webhook-secret")

        payload = _tavus_payload("some.event", "conv-bad-sig")
        body = json.dumps(payload).encode()

        with patch("oratoria.api.v1.webhooks.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "x-tavus-signature": "totally-wrong-signature",
                    },
                )

        assert resp.status_code == 401

    async def test_correct_hmac_signature_returns_200(self):
        """When TAVUS_WEBHOOK_SECRET is set and correct HMAC is provided → 200."""
        from pydantic import SecretStr

        app = _make_app()
        secret = "my-webhook-secret"
        convo = _make_convo_row(provider_conversation_id="conv-correct-sig")
        mock_db = _make_db_that_returns(convo)

        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = SecretStr(secret)

        payload = _tavus_payload("some.event", "conv-correct-sig")
        body = json.dumps(payload).encode()
        signature = _sign(body, secret)

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "x-tavus-signature": signature,
                    },
                )

        assert resp.status_code == 200

    async def test_missing_signature_header_returns_401_when_secret_set(self):
        """When secret is configured but no signature header is sent → 401."""
        from pydantic import SecretStr

        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = SecretStr("my-webhook-secret")

        payload = _tavus_payload("some.event", "conv-no-header")
        body = json.dumps(payload).encode()

        with patch("oratoria.api.v1.webhooks.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                    # No x-tavus-signature header
                )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unknown conversation_id
# ---------------------------------------------------------------------------


class TestTavusWebhookUnknownConversation:
    async def test_unknown_conversation_id_returns_200_ignored(self):
        """An event for an unknown conversation_id → 200 with status='ignored'."""
        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        # DB returns None for the conversation lookup
        mock_db = _make_db_that_returns(convo_row=None)

        payload = _tavus_payload("application.transcription_ready", "conv-unknown-999")
        body = json.dumps(payload).encode()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ignored"


# ---------------------------------------------------------------------------
# application.transcription_ready — transcript stored and evaluator triggered
# ---------------------------------------------------------------------------


class TestTavusWebhookTranscriptionReady:
    async def test_transcript_stored_when_conversation_still_active(self):
        """transcription_ready stores transcript on the AvatarConversation row."""
        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        convo = _make_convo_row(
            provider_conversation_id="conv-transcript-1",
            status="active",  # not yet ended → evaluator should NOT run
        )
        mock_db = _make_db_that_returns(convo)

        transcript_payload = [
            {"role": "user", "content": "Hola audiencia."},
            {"role": "replica", "content": "Hola, bienvenido."},
        ]
        payload = _tavus_payload(
            "application.transcription_ready",
            "conv-transcript-1",
            extra={"transcript": transcript_payload},
        )
        body = json.dumps(payload).encode()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        # transcript was written to the convo row
        assert convo.transcript == transcript_payload

    async def test_evaluator_runs_when_transcript_ready_and_conversation_ended(self):
        """transcription_ready + conversation already ENDED → evaluator runs immediately."""
        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        convo = _make_convo_row(
            provider_conversation_id="conv-eval-trigger",
            status="ended",
        )
        session_row = _make_session_row()
        mock_db = _make_db_that_returns(convo, session_row=session_row)

        transcript_payload = [{"role": "user", "content": "Mi pitch."}]
        payload = _tavus_payload(
            "application.transcription_ready",
            "conv-eval-trigger",
            extra={"transcript": transcript_payload},
        )
        body = json.dumps(payload).encode()

        mock_evaluate = AsyncMock()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
            patch("oratoria.api.v1.webhooks._evaluate_avatar_session", mock_evaluate),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        mock_evaluate.assert_awaited_once()

    async def test_evaluator_does_not_run_when_conversation_still_active(self):
        """If the conversation is still ACTIVE when the transcript arrives, don't evaluate yet."""
        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        convo = _make_convo_row(
            provider_conversation_id="conv-no-eval",
            status="active",
        )
        mock_db = _make_db_that_returns(convo)

        transcript_payload = [{"role": "user", "content": "Presentación aún en curso."}]
        payload = _tavus_payload(
            "application.transcription_ready",
            "conv-no-eval",
            extra={"transcript": transcript_payload},
        )
        body = json.dumps(payload).encode()

        mock_evaluate = AsyncMock()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
            patch("oratoria.api.v1.webhooks._evaluate_avatar_session", mock_evaluate),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        mock_evaluate.assert_not_awaited()

    async def test_transcript_in_data_envelope_also_extracted(self):
        """Transcript nested under payload.data is correctly extracted."""
        app = _make_app()
        mock_settings = MagicMock()
        mock_settings.tavus_webhook_secret = None

        convo = _make_convo_row(
            provider_conversation_id="conv-data-envelope",
            status="active",
        )
        mock_db = _make_db_that_returns(convo)

        transcript_payload = [{"role": "user", "content": "Via data envelope."}]
        payload = {
            "event_type": "application.transcription_ready",
            "conversation_id": "conv-data-envelope",
            "data": {"transcript": transcript_payload},
        }
        body = json.dumps(payload).encode()

        with (
            patch("oratoria.api.v1.webhooks.settings", mock_settings),
            patch("oratoria.api.v1.webhooks.async_session_factory", return_value=mock_db),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks/tavus",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        assert convo.transcript == transcript_payload
