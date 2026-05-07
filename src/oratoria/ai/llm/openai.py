"""OpenAI client helpers (fallback LLM)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from oratoria.config import settings


def build_openai(temperature: float = 0.2, max_tokens: int = 4096) -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=60,
    )
