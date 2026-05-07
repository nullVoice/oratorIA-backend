"""LLM factory — pick a provider per environment / feature flag."""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

ProviderName = Literal["anthropic", "openai"]


def get_chat_model(provider: ProviderName = "anthropic", **kwargs: object) -> BaseChatModel:
    """TODO: instantiate based on provider, return a LangChain BaseChatModel."""
    raise NotImplementedError
