"""LLM factory — pick a provider per environment / feature flag."""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from oratoria.ai.llm.claude import build_claude
from oratoria.ai.llm.openai import build_openai

ProviderName = Literal["claude", "anthropic", "openai"]


def _has_secret(s: object) -> bool:
    if s is None:
        return False
    if hasattr(s, "get_secret_value"):
        return bool(s.get_secret_value())  # type: ignore[no-any-return]
    return bool(s)


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


def get_evaluator_llm(*, temperature: float = 0.3, max_tokens: int = 4096) -> BaseChatModel:
    """LLM for the evaluator / persona / pitch agents — OpenAI (GPT-4o) first.

    OpenAI is the primary (and currently only) configured provider, so we use
    it by default. Claude is only used as a fallback if an Anthropic key is
    present. This keeps the system working with a single provider key.
    """
    from oratoria.config import settings

    if _has_secret(settings.openai_api_key):
        return build_openai(temperature=temperature, max_tokens=max_tokens)
    if _has_secret(settings.anthropic_api_key):
        return build_claude(temperature=temperature, max_tokens=max_tokens)
    raise RuntimeError("No LLM provider configured: set OPENAI_API_KEY or ANTHROPIC_API_KEY.")


def get_chat_model(provider: ProviderName = "claude", **kwargs: object) -> BaseChatModel:
    return get_llm(provider, **kwargs)  # type: ignore[arg-type]
