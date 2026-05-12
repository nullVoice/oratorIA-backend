"""Avatar (conversational video) providers."""

from __future__ import annotations

from oratoria.services.avatar.base import (
    AvatarConversation,
    AvatarConversationStatus,
    AvatarService,
)
from oratoria.services.avatar.tavus import TavusService

__all__ = [
    "AvatarConversation",
    "AvatarConversationStatus",
    "AvatarService",
    "TavusService",
    "get_avatar_service",
]


def get_avatar_service() -> AvatarService:
    """Return the configured avatar provider. Tavus only for now."""
    return TavusService()
