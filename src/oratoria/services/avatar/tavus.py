"""Tavus CVI provider — wraps the REST API at https://tavusapi.com/v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, cast

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from oratoria.config import settings
from oratoria.services.avatar.base import (
    AvatarConversation,
    AvatarConversationStatus,
)

logger = logging.getLogger(__name__)


class TavusService:
    """Tavus REST client. Auth via x-api-key header."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        key = api_key or (
            settings.tavus_api_key.get_secret_value()
            if settings.tavus_api_key
            else ""
        )
        if not key:
            raise RuntimeError(
                "TAVUS_API_KEY is not configured — cannot instantiate TavusService."
            )
        self._api_key = key
        self._base_url = (base_url or settings.tavus_api_base_url).rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
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
    ) -> AvatarConversation:
        body: dict[str, Any] = {
            "persona_id": persona_id,
            "replica_id": replica_id,
            "conversational_context": conversational_context,
            "properties": {
                "language": language,
                "max_call_duration": max_call_duration_seconds,
                "participant_left_timeout": 30,
                "enable_recording": False,
            },
        }
        if conversation_name:
            body["conversation_name"] = conversation_name
        if custom_greeting:
            body["custom_greeting"] = custom_greeting
        if callback_url:
            body["callback_url"] = callback_url

        async with self._client() as client:
            response = await client.post("/conversations", json=body)
            if response.status_code >= 400:
                logger.error(
                    "Tavus create_conversation failed: %s %s",
                    response.status_code,
                    response.text[:500],
                )
                response.raise_for_status()
            data = response.json()

        return AvatarConversation(
            conversation_id=cast(str, data["conversation_id"]),
            conversation_url=cast(str, data["conversation_url"]),
            status=cast(AvatarConversationStatus, data.get("status", "active")),
            started_at=datetime.now(timezone.utc),
            raw=data,
        )

    async def end_conversation(self, conversation_id: str) -> None:
        async with self._client() as client:
            response = await client.post(f"/conversations/{conversation_id}/end")
            # Tavus returns 200 even if already ended — treat 404 as already-ended too.
            if response.status_code not in (200, 204, 404):
                logger.error(
                    "Tavus end_conversation failed: %s %s",
                    response.status_code,
                    response.text[:500],
                )
                response.raise_for_status()

    async def get_conversation(self, conversation_id: str) -> AvatarConversation:
        async with self._client() as client:
            response = await client.get(f"/conversations/{conversation_id}")
            response.raise_for_status()
            data = response.json()
        return AvatarConversation(
            conversation_id=cast(str, data["conversation_id"]),
            conversation_url=cast(str, data.get("conversation_url", "")),
            status=cast(AvatarConversationStatus, data.get("status", "ended")),
            started_at=_parse_dt(data.get("created_at")) or datetime.now(timezone.utc),
            ended_at=_parse_dt(data.get("ended_at")),
            raw=data,
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
