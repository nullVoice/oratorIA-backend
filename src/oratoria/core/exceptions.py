"""Domain-level exceptions."""

from __future__ import annotations


class OratoriaError(Exception):
    """Base exception for all OratorIA domain errors."""


class NotFoundError(OratoriaError):
    """Raised when a requested resource does not exist."""


class PermissionDeniedError(OratoriaError):
    """Raised when the current user is not allowed to access a resource."""


class BillingError(OratoriaError):
    """Raised on subscription / payment-related issues."""


class AIProviderError(OratoriaError):
    """Raised when an upstream LLM / STT / TTS provider fails."""
