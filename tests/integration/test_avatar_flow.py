"""Integration tests for avatar_start and avatar_end endpoints.

POST /api/v1/sessions/{id}/avatar-start
POST /api/v1/sessions/{id}/avatar-end

Strategy: uses FastAPI ASGI transport (no real network). DB and external services
(TavusService, EvaluatorAgent) are fully mocked so no real DB or LLM calls happen.
Follows the same mock-override pattern as test_deepgram_token.py and test_persona_llm_endpoint.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app():
    from oratoria.main import create_app

    return create_app()


def _override_auth(app, user=None):
    from oratoria.core.security import current_active_user

    fake_user = user or _fake_user()
    app.dependency_overrides[current_active_user] = lambda: fake_user


def _fake_user(user_id: uuid.UUID | None = None) -> MagicMock:
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.full_name = "Test User"
    u.segment = "business"
    return u


def _fake_session(
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    session_type: str = "live",
    status: str = "created",
) -> MagicMock:
    from oratoria.models.session import SessionStatus, SessionType

    sess = MagicMock()
    sess.id = session_id or uuid.uuid4()
    sess.user_id = user_id or uuid.uuid4()
    sess.type = SessionType.LIVE if session_type == "live" else SessionType.ASYNC
    sess.status = SessionStatus.CREATED
    sess.context = {}
    sess.started_at = None
    sess.ended_at = None
    sess.duration_seconds = None
    return sess


def _fake_avatar_convo(
    session_id: uuid.UUID,
    provider_conversation_id: str = "conv-test-123",
    status: str = "active",
    transcript: list | None = None,
) -> MagicMock:
    from oratoria.models import AvatarConversationStatus

    convo = MagicMock()
    convo.id = uuid.uuid4()
    convo.session_id = session_id
    convo.provider_conversation_id = provider_conversation_id
    convo.conversation_url = "https://daily.co/room/test"
    convo.replica_id = "replica-xyz"
    convo.persona_id = "persona-abc"
    convo.interactive = False
    convo.status = (
        AvatarConversationStatus.ACTIVE if status == "active" else AvatarConversationStatus.ENDED
    )
    convo.transcript = transcript
    convo.events = None
    convo.perception_analysis = None
    convo.started_at = datetime.now(UTC)
    convo.ended_at = None
    convo.duration_seconds = None
    return convo


def _fake_tavus_conversation(conversation_id: str = "conv-tavus-abc") -> MagicMock:
    """Mimics oratoria.services.avatar.base.AvatarConversation dataclass."""
    conv = MagicMock()
    conv.conversation_id = conversation_id
    conv.conversation_url = "https://daily.co/room/test"
    conv.status = "active"
    conv.started_at = datetime.now(UTC)
    conv.raw = {}
    return conv


def _fake_evaluation_report() -> MagicMock:
    """Mimics oratoria.ai.parsers.feedback_schema.EvaluationReport."""
    from oratoria.ai.parsers.feedback_schema import ParaverbalMetrics

    report = MagicMock()
    report.score = 75
    report.summary = "Good performance overall."
    report.strengths = []
    report.improvements = []
    report.next_steps = ["Practice more."]
    report.paraverbal_metrics = ParaverbalMetrics(
        words_per_minute=130.0,
        filler_words_count=3,
        pause_ratio=0.1,
        tone_variance=0.5,
    )

    # Make model_dump() work on MagicMock strengths/improvements items
    return report


def _mock_settings_tavus_configured(mock_settings: MagicMock) -> None:
    from pydantic import SecretStr

    mock_settings.tavus_api_key = SecretStr("fake-tavus-key")
    mock_settings.tavus_persona_id = "persona-abc"
    mock_settings.tavus_replica_id = "replica-xyz"
    mock_settings.tavus_callback_base_url = None
    mock_settings.tavus_max_call_duration_seconds = 900
    mock_settings.cors_origins = "http://localhost:3000"
    mock_settings.cors_origins_list = ["http://localhost:3000"]
    mock_settings.is_production = False
    mock_settings.sentry_dsn = None
    mock_settings.langfuse_public_key = None
    mock_settings.langfuse_secret_key = None


def _make_execute_result(value) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


def _make_db_mock(
    session_row=None,
    convo_row=None,
    report_row=None,
) -> AsyncMock:
    """Build an AsyncSession mock that returns specific rows for get() and execute().

    execute() is called multiple times in avatar_end:
      1. SELECT AvatarConversation WHERE status=ACTIVE → returns convo_row
      2. SELECT Report WHERE session_id=... → returns report_row (None = no existing report)
    We use a side_effect list so each call gets the right result.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()

    db.get = AsyncMock(return_value=session_row)

    # Build a repeating side-effect: first call → convo_row, all subsequent → report_row
    def _execute_side_effect(_query):
        call_count = db.execute.call_count
        if call_count == 1:
            return _make_execute_result(convo_row)
        return _make_execute_result(report_row)

    db.execute = AsyncMock(side_effect=_execute_side_effect)

    async def refresh(obj):
        pass

    db.refresh = AsyncMock(side_effect=refresh)

    return db


def _override_db(app, db: AsyncMock) -> None:
    from oratoria.database import get_db

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db


# ---------------------------------------------------------------------------
# Realistic Tavus utterance event fixtures
# ---------------------------------------------------------------------------


def _utterance_event(
    seq: int, role: str, speech: str, visual: str | None = None, audio: str | None = None
) -> dict:
    props: dict[str, Any] = {"role": role, "speech": speech}
    if visual:
        props["user_visual_analysis"] = visual
    if audio:
        props["user_audio_analysis"] = audio
    return {"event_type": "conversation.utterance", "seq": seq, "properties": props}


REALISTIC_EVENTS = [
    _utterance_event(1, "replica", "Hola, cuando quieras puedes empezar."),
    _utterance_event(
        2,
        "user",
        "Buenos días a todos. Hoy les voy a hablar sobre liderazgo.",
        visual="Direct eye contact, open posture",
        audio="Clear voice, moderate pace",
    ),
    _utterance_event(3, "replica", "Interesante, continúa."),
    _utterance_event(
        4,
        "user",
        "El liderazgo requiere visión, comunicación y empatía.",
        visual="Gesturing naturally",
        audio="Good projection",
    ),
    _utterance_event(
        5,
        "user",
        "Muchas gracias por su atención.",
        visual="Confident closing",
        audio="Strong finish",
    ),
]


# ---------------------------------------------------------------------------
# avatar_start tests
# ---------------------------------------------------------------------------


class TestAvatarStart:
    async def test_happy_path_returns_201_with_conversation_url(self):
        """avatar_start happy path: POST to a LIVE session → 201 with conversation_url."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id, session_type="live")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        mock_tavus_conv = _fake_tavus_conversation("conv-happy-123")
        mock_avatar_service = AsyncMock()
        mock_avatar_service.create_conversation = AsyncMock(return_value=mock_tavus_conv)

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with (
            patch("oratoria.api.v1.avatar.settings", mock_settings),
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 201
        data = resp.json()
        assert "conversation_url" in data
        assert data["conversation_url"] == "https://daily.co/room/test"

    async def test_happy_path_db_row_created_and_session_in_progress(self):
        """avatar_start: AvatarConversation row is added and session status set to IN_PROGRESS."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id, session_type="live")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        mock_tavus_conv = _fake_tavus_conversation("conv-row-check")
        mock_avatar_service = AsyncMock()
        mock_avatar_service.create_conversation = AsyncMock(return_value=mock_tavus_conv)

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with (
            patch("oratoria.api.v1.avatar.settings", mock_settings),
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        # db.add was called (with the AvatarConversation row)
        db.add.assert_called()
        # session status was updated
        from oratoria.models.session import SessionStatus

        assert sess.status == SessionStatus.IN_PROGRESS

    async def test_returns_503_when_tavus_not_configured(self):
        """avatar_start with Tavus env not configured → 503."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id, session_type="live")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        mock_settings = MagicMock()
        # Tavus NOT configured
        mock_settings.tavus_api_key = None
        mock_settings.tavus_persona_id = None
        mock_settings.tavus_replica_id = None

        with patch("oratoria.api.v1.avatar.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 503

    async def test_returns_400_for_async_session(self):
        """avatar_start on a non-LIVE (async) session → 400."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id, session_type="async")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with patch("oratoria.api.v1.avatar.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 400

    async def test_returns_404_for_another_users_session(self):
        """avatar_start on another user's session → 404."""
        app = _make_app()
        user = _fake_user()
        other_user_id = uuid.uuid4()
        # session belongs to another user
        sess = _fake_session(user_id=other_user_id, session_type="live")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with patch("oratoria.api.v1.avatar.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 404

    async def test_out_of_credits_returns_402_with_friendly_message(self):
        """When Tavus replies 402 (out of credits), avatar_start surfaces a 402
        with a clear, user-facing Spanish message — not a cryptic 503."""
        import httpx

        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id, session_type="live")
        db = _make_db_mock(session_row=sess)
        _override_auth(app, user)
        _override_db(app, db)

        req = httpx.Request("POST", "https://tavusapi.com/v2/conversations")
        tavus_402 = httpx.Response(
            402,
            json={"message": "The user is out of conversational credits."},
            request=req,
        )
        mock_avatar_service = AsyncMock()
        mock_avatar_service.create_conversation = AsyncMock(
            side_effect=httpx.HTTPStatusError("402", request=req, response=tavus_402)
        )

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with (
            patch("oratoria.api.v1.avatar.settings", mock_settings),
            patch(
                "oratoria.api.v1.avatar.get_avatar_service",
                return_value=mock_avatar_service,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert "crédito" in detail.lower()
        assert "Práctica simple" in detail

    async def test_returns_404_for_missing_session(self):
        """avatar_start on a non-existent session → 404."""
        app = _make_app()
        user = _fake_user()
        # DB returns None for get()
        db = _make_db_mock(session_row=None)
        _override_auth(app, user)
        _override_db(app, db)

        mock_settings = MagicMock()
        _mock_settings_tavus_configured(mock_settings)

        with patch("oratoria.api.v1.avatar.settings", mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{uuid.uuid4()}/avatar-start",
                    json={"interactive": False},
                )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# avatar_end tests
# ---------------------------------------------------------------------------


class TestAvatarEnd:
    async def test_returns_404_when_no_active_avatar_conversation(self):
        """avatar_end when there is no ACTIVE avatar conversation → 404."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        # execute returns None (no active avatar conversation)
        db = _make_db_mock(session_row=sess, convo_row=None)
        _override_auth(app, user)
        _override_db(app, db)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/sessions/{sess.id}/avatar-end",
                json={"events": []},
            )

        assert resp.status_code == 404

    async def test_end_with_realistic_events_runs_evaluator_and_report_ready(self):
        """avatar_end with realistic Tavus utterance events: evaluator runs, report_ready=True.

        This is the key frontend→backend transcript path. The events payload contains
        conversation.utterance events with user and replica turns. The evaluator (mocked)
        should run and report_ready should be True in the response.
        """
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)  # no transcript yet

        db = _make_db_mock(session_row=sess, convo_row=convo)
        _override_auth(app, user)
        _override_db(app, db)

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()

        fake_report = _fake_evaluation_report()
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = AsyncMock(return_value=fake_report)

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch("oratoria.api.v1.avatar.EvaluatorAgent", return_value=mock_evaluator),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": REALISTIC_EVENTS},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["report_ready"] is True

        # The evaluator was called
        mock_evaluator.evaluate.assert_awaited_once()

        # db.add was called (for Transcript and Report rows)
        assert db.add.call_count >= 2

    async def test_end_with_events_derives_transcript_from_user_turns_only(self):
        """_transcript_from_events derives transcript; _normalize_avatar_transcript
        keeps only user speech so the evaluator grades the presenter, not the replica."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)
        db = _make_db_mock(session_row=sess, convo_row=convo)
        _override_auth(app, user)
        _override_db(app, db)

        captured_transcript: list[str] = []

        async def mock_evaluate(transcript, context, paraverbal_metrics, **kwargs):
            captured_transcript.append(transcript)
            return _fake_evaluation_report()

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = AsyncMock(side_effect=mock_evaluate)

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch("oratoria.api.v1.avatar.EvaluatorAgent", return_value=mock_evaluator),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": REALISTIC_EVENTS},
                )

        assert captured_transcript, "evaluate should have been called"
        graded_text = captured_transcript[0]

        # User speech IS in the graded transcript
        assert "liderazgo" in graded_text or "Buenos días" in graded_text

        # Replica speech is NOT in the graded transcript
        assert "cuando quieras" not in graded_text
        assert "Interesante" not in graded_text

    async def test_end_no_events_no_callback_creates_placeholder_report(self):
        """avatar_end with NO events, NO callback URL, and empty Tavus poll →
        placeholder Report, report_ready=True.

        The placeholder is the LAST resort: it only fires when there is no
        public callback URL for the Tavus webhook to reach (no tunnel), so the
        transcript can never arrive any other way.

        _make_db_mock uses a side_effect sequence:
          call 1 → convo_row (AvatarConversation query)
          call 2+ → None (Report existence check → no existing report)
        """
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)
        # report_row=None so the placeholder branch fires (no existing report)
        db = _make_db_mock(session_row=sess, convo_row=convo, report_row=None)
        _override_auth(app, user)
        _override_db(app, db)

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
            # No tunnel configured → placeholder is the only way to close the session.
            patch("oratoria.api.v1.avatar._callback_url", return_value=None),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": []},
                )

        assert resp.status_code == 200
        data = resp.json()
        # Placeholder report was created → report_ready=True
        assert data["report_ready"] is True

        # db.add was called with the placeholder Report
        db.add.assert_called()
        # Check that a Report-like object was added (score=0 placeholder)
        from oratoria.models import Report

        added_objects = [call.args[0] for call in db.add.call_args_list]
        report_objs = [o for o in added_objects if isinstance(o, Report)]
        assert len(report_objs) == 1
        assert report_objs[0].score == 0

    async def test_end_no_events_with_callback_skips_placeholder(self):
        """avatar_end with NO events but a callback URL configured → NO
        placeholder is created, report_ready=False.

        Regression guard for the placeholder-shadow bug: when a tunnel is
        configured the Tavus transcription_ready webhook will deliver the real
        transcript shortly, and the frontend polls meanwhile. Creating a
        score-0 placeholder here would permanently shadow the real report.
        """
        from oratoria.models import Report

        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)
        db = _make_db_mock(session_row=sess, convo_row=convo, report_row=None)
        _override_auth(app, user)
        _override_db(app, db)

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
            patch(
                "oratoria.api.v1.avatar._callback_url",
                return_value="https://example.ngrok.dev/api/v1/webhooks/tavus",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": []},
                )

        assert resp.status_code == 200
        data = resp.json()
        # No transcript yet, but a tunnel exists → defer to the webhook.
        assert data["report_ready"] is False

        # Crucially, NO placeholder Report was added.
        added_objects = [call.args[0] for call in db.add.call_args_list]
        report_objs = [o for o in added_objects if isinstance(o, Report)]
        assert report_objs == []

    async def test_end_conversation_status_becomes_ended(self):
        """After avatar_end, the AvatarConversation status is set to ENDED."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)
        db = _make_db_mock(session_row=sess, convo_row=convo)
        _override_auth(app, user)
        _override_db(app, db)

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": []},
                )

        from oratoria.models import AvatarConversationStatus

        assert convo.status == AvatarConversationStatus.ENDED

    async def test_end_with_events_stores_events_on_convo_row(self):
        """Events from the frontend are stored on the AvatarConversation.events field."""
        app = _make_app()
        user = _fake_user()
        sess = _fake_session(user_id=user.id)
        convo = _fake_avatar_convo(sess.id, transcript=None)
        convo.events = None  # start with no events
        db = _make_db_mock(session_row=sess, convo_row=convo)
        _override_auth(app, user)
        _override_db(app, db)

        mock_avatar_service = AsyncMock()
        mock_avatar_service.end_conversation = AsyncMock()

        with (
            patch("oratoria.api.v1.avatar.get_avatar_service", return_value=mock_avatar_service),
            patch(
                "oratoria.api.v1.avatar.EvaluatorAgent",
                return_value=MagicMock(evaluate=AsyncMock(return_value=_fake_evaluation_report())),
            ),
            patch("oratoria.api.v1.avatar._poll_tavus_transcript", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    f"/api/v1/sessions/{sess.id}/avatar-end",
                    json={"events": REALISTIC_EVENTS},
                )

        # Events were stored on the convo row
        assert convo.events is not None
        assert len(convo.events) == len(REALISTIC_EVENTS)

    async def test_end_session_missing_returns_404(self):
        """avatar_end on a non-existent session → 404."""
        app = _make_app()
        user = _fake_user()
        db = _make_db_mock(session_row=None)
        _override_auth(app, user)
        _override_db(app, db)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/sessions/{uuid.uuid4()}/avatar-end",
                json={"events": []},
            )

        assert resp.status_code == 404


class TestPlaceholderReplacement:
    """_evaluate_avatar_session must REPLACE a placeholder report once a real
    transcript arrives (e.g. via the Tavus webhook), but must NOT touch a
    genuine report. This is the core fix for the placeholder-shadow bug where
    avatar-end's score-0 placeholder permanently blocked the real evaluation.
    """

    def _db_with_existing_report(self, existing) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(existing))
        return db

    async def test_placeholder_report_is_replaced_by_real_evaluation(self):
        from oratoria.api.v1.avatar import _PLACEHOLDER_SUMMARY, _evaluate_avatar_session
        from oratoria.models import Report

        # Existing placeholder report (score 0, the canonical placeholder text).
        placeholder = MagicMock()
        placeholder.score = 0
        placeholder.summary = _PLACEHOLDER_SUMMARY

        sess = _fake_session()
        convo = _fake_avatar_convo(
            sess.id,
            status="ended",
            transcript=[{"role": "user", "content": "Buenas tardes, presento mi tesis."}],
        )
        convo.duration_seconds = 120
        db = self._db_with_existing_report(placeholder)

        agent_instance = MagicMock()
        agent_instance.evaluate = AsyncMock(return_value=_fake_evaluation_report())

        with patch("oratoria.api.v1.avatar.EvaluatorAgent", return_value=agent_instance):
            await _evaluate_avatar_session(db, sess, convo)

        # The placeholder was deleted...
        db.delete.assert_awaited_once_with(placeholder)
        # ...and a real Report (score 75 from the fake evaluation) was added.
        added = [c.args[0] for c in db.add.call_args_list]
        reports = [o for o in added if isinstance(o, Report)]
        assert len(reports) == 1
        assert reports[0].score == 75

    async def test_genuine_report_is_not_replaced(self):
        from oratoria.api.v1.avatar import _evaluate_avatar_session
        from oratoria.models import Report

        # A real, previously-generated report — must be left untouched.
        real = MagicMock()
        real.score = 82
        real.summary = "Una evaluación real previa."

        sess = _fake_session()
        convo = _fake_avatar_convo(
            sess.id,
            status="ended",
            transcript=[{"role": "user", "content": "Contenido real."}],
        )
        db = self._db_with_existing_report(real)

        agent_instance = MagicMock()
        agent_instance.evaluate = AsyncMock(return_value=_fake_evaluation_report())

        with patch("oratoria.api.v1.avatar.EvaluatorAgent", return_value=agent_instance):
            await _evaluate_avatar_session(db, sess, convo)

        # Idempotent: no delete, no new report, evaluator never called.
        db.delete.assert_not_called()
        added = [c.args[0] for c in db.add.call_args_list]
        assert [o for o in added if isinstance(o, Report)] == []
        agent_instance.evaluate.assert_not_called()
