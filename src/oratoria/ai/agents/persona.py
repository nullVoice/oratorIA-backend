"""Persona Agent — streaming conversational LLM for Audiencia Digital."""
from __future__ import annotations

from typing import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from oratoria.ai.llm.factory import get_evaluator_llm


class PersonaAgent:
    def __init__(self, temperature: float = 0.7, max_tokens: int = 512) -> None:
        # Fallback-aware: Claude si hay ANTHROPIC_API_KEY, si no GPT-4o.
        self._llm = get_evaluator_llm(temperature=temperature, max_tokens=max_tokens)

    async def astream_reply(
        self, *, system_prompt: str, messages: list[dict]
    ) -> AsyncIterator[str]:
        lc_messages = [SystemMessage(content=system_prompt)]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            # DROP system-role messages — we own the system prompt

        async for chunk in self._llm.astream(lc_messages):
            if chunk.content:  # skip empty/None
                yield chunk.content
