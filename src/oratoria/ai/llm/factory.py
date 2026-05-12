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


def get_evaluator_llm(
    *, temperature: float = 0.3, max_tokens: int = 4096
) -> BaseChatModel:
    """LLM for the evaluator agent — Claude first, GPT-4o fallback.

    Mirrors the strategy used by /api/v1/practice/finalize so the system
    keeps working when only one provider key is configured.
    """
    from oratoria.config import settings

    if _has_secret(settings.anthropic_api_key):
        return build_claude(temperature=temperature, max_tokens=max_tokens)
    if _has_secret(settings.openai_api_key):
        return build_openai(temperature=temperature, max_tokens=max_tokens)
    raise RuntimeError(
        "No LLM provider configured: set ANTHROPIC_API_KEY or OPENAI_API_KEY."
    )


def get_chat_model(
    provider: ProviderName = "claude", **kwargs: object
) -> BaseChatModel:
    return get_llm(provider, **kwargs)  # type: ignore[arg-type]
