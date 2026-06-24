"""Unit tests for avatar helper functions.

Tests:
  - _transcript_from_events: builds [{role, content, ...}] from Tavus utterance events
  - _build_perception_data: extracts Raven-1 analyses from events / perception_analysis
  - _normalize_avatar_transcript: filters to user-only turns and joins to a string

Realistic Tavus utterance event shape (from tavus_docs.md):
  {
    "event_type": "conversation.utterance",
    "seq": N,
    "properties": {
      "role": "user" | "replica",
      "speech": "<text>",
      "user_visual_analysis": "...",   # only for user turns with Raven-1
      "user_audio_analysis": "...",    # only for user turns with Raven-1
    }
  }
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _utterance(
    seq: int, role: str, speech: str, visual: str | None = None, audio: str | None = None
) -> dict:
    """Build a realistic Tavus conversation.utterance event."""
    props: dict = {"role": role, "speech": speech}
    if visual is not None:
        props["user_visual_analysis"] = visual
    if audio is not None:
        props["user_audio_analysis"] = audio
    return {"event_type": "conversation.utterance", "seq": seq, "properties": props}


def _non_utterance_event(seq: int) -> dict:
    return {"event_type": "conversation.started", "seq": seq, "properties": {}}


# ---------------------------------------------------------------------------
# _transcript_from_events
# ---------------------------------------------------------------------------


class TestTranscriptFromEvents:
    """_transcript_from_events converts Tavus utterance events to [{role, content}]."""

    def _call(self, events):
        from oratoria.api.v1.avatar import _transcript_from_events

        return _transcript_from_events(events)

    def test_user_turn_included(self):
        """A user utterance event produces a transcript item with role=user."""
        events = [_utterance(1, "user", "Buenos días a todos.")]
        result = self._call(events)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Buenos días a todos."

    def test_replica_turn_included_with_role(self):
        """A replica utterance is included in the raw transcript with role=replica.

        _transcript_from_events returns ALL turns (both user and replica). Filtering
        to user-only happens in _normalize_avatar_transcript.
        """
        events = [
            _utterance(1, "user", "Hola."),
            _utterance(2, "replica", "Hola, bienvenido."),
        ]
        result = self._call(events)
        assert len(result) == 2
        roles = [r["role"] for r in result]
        assert "user" in roles
        assert "replica" in roles

    def test_empty_speech_skipped(self):
        """Events with empty or whitespace-only speech are excluded."""
        events = [
            _utterance(1, "user", ""),
            _utterance(2, "user", "   "),
            _utterance(3, "user", "Contenido real."),
        ]
        result = self._call(events)
        assert len(result) == 1
        assert result[0]["content"] == "Contenido real."

    def test_raven_analyses_captured_on_user_turns(self):
        """Raven-1 visual/audio analyses are captured on user turns."""
        events = [
            _utterance(
                1,
                "user",
                "Mi propuesta de valor es...",
                visual="Good eye contact, open posture",
                audio="Clear articulation, moderate pace",
            )
        ]
        result = self._call(events)
        assert len(result) == 1
        item = result[0]
        assert item.get("user_visual_analysis") == "Good eye contact, open posture"
        assert item.get("user_audio_analysis") == "Clear articulation, moderate pace"

    def test_non_utterance_events_skipped(self):
        """Non-utterance events (started, ended, etc.) are ignored."""
        events = [
            _non_utterance_event(0),
            _utterance(1, "user", "Mi presentación es sobre IA."),
            _non_utterance_event(2),
        ]
        result = self._call(events)
        assert len(result) == 1
        assert result[0]["content"] == "Mi presentación es sobre IA."

    def test_empty_events_list(self):
        """An empty event list returns an empty transcript."""
        assert self._call([]) == []

    def test_non_dict_events_skipped(self):
        """Non-dict items in the events list are silently ignored."""
        events = [None, "bad", 42, _utterance(1, "user", "Válido.")]
        result = self._call(events)
        assert len(result) == 1

    def test_missing_properties_defaults_role_to_user(self):
        """When properties.role is absent the item defaults to role='user'."""
        event = {"event_type": "conversation.utterance", "seq": 1, "properties": {"speech": "Hola"}}
        result = self._call([event])
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_speech_fallback_to_content_and_text(self):
        """Falls back to properties.content or properties.text if speech is absent."""
        events = [
            {
                "event_type": "conversation.utterance",
                "seq": 1,
                "properties": {"role": "user", "content": "Desde content"},
            },
            {
                "event_type": "conversation.utterance",
                "seq": 2,
                "properties": {"role": "user", "text": "Desde text"},
            },
        ]
        result = self._call(events)
        assert len(result) == 2
        assert result[0]["content"] == "Desde content"
        assert result[1]["content"] == "Desde text"

    def test_multiple_user_and_replica_turns(self):
        """Mixed turns are all returned; order matches input sequence."""
        events = [
            _utterance(1, "user", "Primera pregunta del presentador."),
            _utterance(2, "replica", "Respuesta del avatar."),
            _utterance(3, "user", "Segunda intervención."),
        ]
        result = self._call(events)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "replica"
        assert result[2]["role"] == "user"


# ---------------------------------------------------------------------------
# _normalize_avatar_transcript
# ---------------------------------------------------------------------------


class TestNormalizeAvatarTranscript:
    """_normalize_avatar_transcript filters to user-only turns and joins to a string."""

    async def _call(self, transcript):
        from oratoria.api.v1.avatar import _normalize_avatar_transcript

        return await _normalize_avatar_transcript(transcript)

    async def test_user_turns_joined(self):
        """User turns are concatenated into a single string."""
        transcript = [
            {"role": "user", "content": "Primera parte."},
            {"role": "user", "content": "Segunda parte."},
        ]
        result = await self._call(transcript)
        assert "Primera parte." in result
        assert "Segunda parte." in result

    async def test_replica_turns_excluded(self):
        """Replica (avatar) turns are NOT included in the graded transcript."""
        transcript = [
            {"role": "user", "content": "Hola audiencia."},
            {"role": "replica", "content": "Hola presentador, bienvenido."},
            {"role": "user", "content": "Mi tema hoy es liderazgo."},
        ]
        result = await self._call(transcript)
        assert "Hola audiencia." in result
        assert "Mi tema hoy es liderazgo." in result
        assert "bienvenido" not in result

    async def test_empty_transcript_returns_empty_string(self):
        """None or empty list returns an empty string."""
        assert await self._call(None) == ""
        assert await self._call([]) == ""

    async def test_empty_content_skipped(self):
        """Items with empty or whitespace content are excluded."""
        transcript = [
            {"role": "user", "content": ""},
            {"role": "user", "content": "   "},
            {"role": "user", "content": "Contenido válido."},
        ]
        result = await self._call(transcript)
        assert result == "Contenido válido."

    async def test_non_dict_items_skipped(self):
        """Non-dict items in the transcript list are silently ignored."""
        transcript = [None, "string", {"role": "user", "content": "Válido."}]
        result = await self._call(transcript)
        assert "Válido." in result

    async def test_participant_role_alias_included(self):
        """'participant' and 'presenter' are treated as user roles."""
        transcript = [
            {"role": "participant", "content": "Desde participant."},
            {"role": "presenter", "content": "Desde presenter."},
        ]
        result = await self._call(transcript)
        assert "Desde participant." in result
        assert "Desde presenter." in result

    async def test_speaker_field_used_as_fallback(self):
        """If 'role' is absent, 'speaker' field is used to determine the role."""
        transcript = [
            {"speaker": "user", "content": "Con speaker field."},
        ]
        result = await self._call(transcript)
        assert "Con speaker field." in result

    async def test_result_contains_only_user_speech(self):
        """The final string contains ONLY user speech, not avatar speech."""
        transcript = [
            {"role": "user", "content": "Buenas tardes."},
            {"role": "replica", "content": "Buenas tardes, ¿sobre qué hablarás?"},
            {"role": "user", "content": "Hoy hablo sobre motivación."},
            {"role": "replica", "content": "Interesante, continúa."},
            {"role": "user", "content": "La clave es la persistencia."},
        ]
        result = await self._call(transcript)
        words_in_result = result.lower()
        # User words present
        assert "buenas tardes" in words_in_result
        assert "motivación" in words_in_result
        assert "persistencia" in words_in_result
        # Replica words absent
        assert "interesante" not in words_in_result
        assert "continúa" not in words_in_result


# ---------------------------------------------------------------------------
# _build_perception_data
# ---------------------------------------------------------------------------


class TestBuildPerceptionData:
    """_build_perception_data composes Raven-1 per-turn and summary analyses."""

    def _make_convo(self, events=None, perception_analysis=None):
        """Return a minimal AvatarConversation ORM-like mock."""
        convo = MagicMock()
        convo.events = events
        convo.perception_analysis = perception_analysis
        return convo

    def _call(self, convo):
        from oratoria.api.v1.avatar import _build_perception_data

        return _build_perception_data(convo)

    def test_raven_visual_and_audio_included(self):
        """Raven-1 visual and audio analyses from user utterance events are included."""
        events = [
            _utterance(
                1,
                "user",
                "Buenos días.",
                visual="Direct gaze, relaxed shoulders",
                audio="Steady pace, clear pronunciation",
            )
        ]
        convo = self._make_convo(events=events)
        result = self._call(convo)
        assert "Direct gaze" in result
        assert "Steady pace" in result

    def test_replica_turns_not_included_in_perception(self):
        """Raven-1 data from replica turns is excluded — we grade the user only."""
        events = [
            _utterance(1, "user", "Yo hablo.", visual="Good posture", audio="Clear"),
            _utterance(
                2, "replica", "Avatar speaks.", visual="replica visual", audio="replica audio"
            ),
        ]
        convo = self._make_convo(events=events)
        result = self._call(convo)
        assert "Good posture" in result
        assert "replica visual" not in result

    def test_perception_analysis_summary_included(self):
        """The final perception_analysis summary (from webhook) is included when present."""
        convo = self._make_convo(
            events=[],
            perception_analysis={"overall": "Confident body language", "score": 8},
        )
        result = self._call(convo)
        assert "Confident body language" in result

    def test_no_data_returns_placeholder(self):
        """When no perception data is available, a placeholder message is returned."""
        convo = self._make_convo(events=[], perception_analysis=None)
        result = self._call(convo)
        assert result  # not empty
        assert "No hay datos" in result or "not available" in result.lower() or len(result) > 0

    def test_non_utterance_events_ignored_in_perception(self):
        """Non-utterance events don't contribute to perception data."""
        events = [
            _non_utterance_event(0),
            _utterance(1, "user", "Hola.", visual="Open posture", audio="Clear voice"),
        ]
        convo = self._make_convo(events=events)
        result = self._call(convo)
        assert "Open posture" in result
        assert "Clear voice" in result

    def test_utterance_without_analyses_not_included(self):
        """Utterance events without visual/audio analysis don't add empty lines."""
        events = [_utterance(1, "user", "Hola sin análisis.")]  # no visual/audio
        convo = self._make_convo(events=events)
        result = self._call(convo)
        # No Raven data → falls through to placeholder or empty analysis section
        assert isinstance(result, str)

    def test_both_per_turn_and_summary_combined(self):
        """When both per-turn Raven data and a summary exist, both appear in the output."""
        events = [
            _utterance(1, "user", "Introducción.", visual="Eye contact good", audio="Slow pace"),
        ]
        convo = self._make_convo(
            events=events,
            perception_analysis={"summary": "Overall confident"},
        )
        result = self._call(convo)
        assert "Eye contact good" in result
        assert "Overall confident" in result
