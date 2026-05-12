"""LLM factory — pick a provider per environment / feature flag."""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from oratoria.ai.llm.claude import build_claude
from oratoria.ai.llm.openai import build_openai

ProviderName = Literal["claude", "anthropic", "openai"]


def get_llm(
    provider: ProviderName = "claude",
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> BaseChatModel:
    if provider in ("claude", "anthropic"):
        return build_claude(temperature=temperature, max_tokens=max_tokens)
    if provider == "openai":
        return build_openai(temperature=temperature, max_tokens=max_tokens)
    raise ValueError(f"Unknown LLM provider: {provider!r}")


def get_chat_model(
    provider: ProviderName = "claude", **kwargs: object
) -> BaseChatModel:
    return get_llm(provider, **kwargs)  # type: ignore[arg-type]
