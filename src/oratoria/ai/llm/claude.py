"""Claude (Anthropic) client helpers."""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from oratoria.config import settings


def build_claude(temperature: float = 0.3, max_tokens: int = 4096) -> ChatAnthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
    return ChatAnthropic(
        model_name=settings.anthropic_model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=60,
        stop=None,
    )


def get_claude_llm(temperature: float = 0.3, max_tokens: int = 4096) -> ChatAnthropic:
    return build_claude(temperature=temperature, max_tokens=max_tokens)
