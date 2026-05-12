"""Avatar conversation contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

AvatarConversationStatus = Literal["active", "ended", "error"]


@dataclass(slots=True)
class AvatarConversation:
    """Provider-agnostic representation of a video conversation."""

    conversation_id: str
    conversation_url: str
    status: AvatarConversationStatus
    started_at: datetime
    ended_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class AvatarService(Protocol):
    """Protocol for conversational video providers (Tavus, others)."""

    async def create_conversation(
        self,
        *,
        persona_id: str,
        replica_id: str,
        conversational_context: str,
        custom_greeting: str | None = None,
        conversation_name: str | None = None,
        callback_url: str | None = None,
        max_call_duration_seconds: int = 900,
        language: str = "spanish",
    ) -> AvatarConversation: ...

    async def end_conversation(self, conversation_id: str) -> None: ...

    async def get_conversation(self, conversation_id: str) -> AvatarConversation: ...
