"""Tests for PersonaAgent."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPersonaAgentAstreamReply:
    async def test_yields_token_strings(self, mocker):
        """Agent yields non-empty content strings from astream."""
        # Create fake chunks
        chunk1 = MagicMock()
        chunk1.content = "Hola"
        chunk2 = MagicMock()
        chunk2.content = " mundo"

        async def fake_astream(messages):
            for c in [chunk1, chunk2]:
                yield c

        with patch("oratoria.ai.agents.persona.get_evaluator_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.astream = fake_astream
            mock_get_llm.return_value = mock_llm

            from oratoria.ai.agents.persona import PersonaAgent
            agent = PersonaAgent()

            tokens = []
            async for token in agent.astream_reply(
                system_prompt="Eres una audiencia.",
                messages=[{"role": "user", "content": "Hola audiencia"}],
            ):
                tokens.append(token)

        assert tokens == ["Hola", " mundo"]

    async def test_empty_content_chunks_are_skipped(self, mocker):
        """Chunks with empty content are not yielded."""
        chunk_empty = MagicMock(); chunk_empty.content = ""
        chunk_none = MagicMock(); chunk_none.content = None
        chunk_valid = MagicMock(); chunk_valid.content = "token"

        async def fake_astream(messages):
            for c in [chunk_empty, chunk_none, chunk_valid]:
                yield c

        with patch("oratoria.ai.agents.persona.get_evaluator_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.astream = fake_astream
            mock_get_llm.return_value = mock_llm

            from oratoria.ai.agents.persona import PersonaAgent
            agent = PersonaAgent()

            tokens = []
            async for token in agent.astream_reply(
                system_prompt="Sys",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                tokens.append(token)

        assert tokens == ["token"]

    async def test_system_role_messages_not_forwarded(self, mocker):
        """System-role messages in the input list are dropped; we own the system prompt."""
        captured_messages = []

        async def fake_astream(messages):
            captured_messages.extend(messages)
            return
            yield  # make it an async generator

        with patch("oratoria.ai.agents.persona.get_evaluator_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.astream = fake_astream
            mock_get_llm.return_value = mock_llm

            from oratoria.ai.agents.persona import PersonaAgent
            agent = PersonaAgent()

            async for _ in agent.astream_reply(
                system_prompt="Our system prompt",
                messages=[
                    {"role": "system", "content": "Ignore this"},
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi"},
                ],
            ):
                pass

        # Only SystemMessage (our prompt) + HumanMessage + AIMessage
        # No extra SystemMessage from the input
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        types = [type(m) for m in captured_messages]
        assert types.count(SystemMessage) == 1  # only our system_prompt
        assert HumanMessage in types
        assert AIMessage in types

    async def test_assistant_messages_become_ai_messages(self, mocker):
        """role=assistant → AIMessage."""
        captured_messages = []

        async def fake_astream(messages):
            captured_messages.extend(messages)
            return
            yield

        with patch("oratoria.ai.agents.persona.get_evaluator_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.astream = fake_astream
            mock_get_llm.return_value = mock_llm

            from oratoria.ai.agents.persona import PersonaAgent
            agent = PersonaAgent()

            async for _ in agent.astream_reply(
                system_prompt="Sys",
                messages=[{"role": "assistant", "content": "I said this"}],
            ):
                pass

        from langchain_core.messages import AIMessage
        ai_msgs = [m for m in captured_messages if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1
        assert ai_msgs[0].content == "I said this"
