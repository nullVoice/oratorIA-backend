"""External webhook receivers (Stripe, Culqi, Tavus, Resend, etc)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from oratoria.api.v1.avatar import _evaluate_avatar_session
from oratoria.config import settings
from oratoria.database import async_session_factory
from oratoria.models import (
    AvatarConversation,
    AvatarConversationStatus,
    Session as SessionModel,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stripe")
async def stripe_webhook() -> dict[str, str]:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED, "TODO: verify Stripe signature + dispatch"
    )


@router.post("/culqi")
async def culqi_webhook() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")


# ============================== Tavus ==============================


@router.post("/tavus")
async def tavus_webhook(
    request: Request,
    x_tavus_signature: str | None = Header(default=None, alias="x-tavus-signature"),
) -> dict[str, str]:
    """Receive Tavus events.

    Handled event types:
      * `application.transcription_ready` — final transcript is available;
        we persist it and run the EvaluatorAgent to produce the Report.
      * `conversation.ended` / `system.shutdown` — mark the conversation closed.

    Signature: if `TAVUS_WEBHOOK_SECRET` is configured we verify the HMAC-SHA256
    signature header. Otherwise we accept the payload (dev mode).
    """
    body_bytes = await request.body()
    _verify_signature(body_bytes, x_tavus_signature)

    try:
        payload: dict[str, Any] = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {exc}"
        ) from exc

    event_type = (
        payload.get("event_type") or payload.get("type") or payload.get("message_type") or ""
    )
    conversation_id = (
        payload.get("conversation_id")
        or (payload.get("data") or {}).get("conversation_id")
        or (payload.get("properties") or {}).get("conversation_id")
    )
    logger.info(
        "tavus webhook: event=%s conversation_id=%s", event_type, conversation_id
    )

    if not conversation_id:
        return {"status": "ignored", "reason": "no conversation_id"}

    async with async_session_factory() as db:
        convo = (
            await db.execute(
                select(AvatarConversation).where(
                    AvatarConversation.provider_conversation_id == conversation_id
                )
            )
        ).scalar_one_or_none()
        if convo is None:
            logger.warning(
                "tavus webhook for unknown conversation_id=%s", conversation_id
            )
            return {"status": "ignored", "reason": "unknown conversation"}

        if _is_transcript_event(event_type):
            transcript = _extract_transcript(payload)
            if transcript:
                convo.transcript = transcript
                logger.info(
                    "stored transcript for conversation %s (%d items)",
                    conversation_id,
                    len(transcript),
                )

        if _is_end_event(event_type):
            if convo.status != AvatarConversationStatus.ENDED:
                convo.status = AvatarConversationStatus.ENDED
                convo.ended_at = convo.ended_at or datetime.now(timezone.utc)
                if convo.started_at and convo.ended_at:
                    convo.duration_seconds = int(
                        (convo.ended_at - convo.started_at).total_seconds()
                    )

        # If we have both a transcript and the conversation has ended, run
        # the evaluator now to generate the Report (idempotent).
        should_evaluate = bool(convo.transcript) and (
            convo.status == AvatarConversationStatus.ENDED
        )
        if should_evaluate:
            sess = await db.get(SessionModel, convo.session_id)
            if sess:
                try:
                    await _evaluate_avatar_session(db, sess, convo)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "evaluator failed for session %s from webhook", sess.id
                    )

        await db.commit()

    return {"status": "ok"}


def _verify_signature(body: bytes, signature: str | None) -> None:
    secret = (
        settings.tavus_webhook_secret.get_secret_value()
        if settings.tavus_webhook_secret
        else ""
    )
    if not secret:
        return  # dev mode — no verification configured
    if not signature:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Missing webhook signature."
        )
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Tavus sends either the raw hex or a `sha256=hex` form.
    candidate = signature.split("=", 1)[-1].strip()
    if not hmac.compare_digest(expected, candidate):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature."
        )


def _is_transcript_event(event_type: str) -> bool:
    t = event_type.lower()
    return any(k in t for k in ("transcription_ready", "transcript"))


def _is_end_event(event_type: str) -> bool:
    t = event_type.lower()
    return any(
        k in t
        for k in (
            "conversation.ended",
            "conversation_ended",
            "system.shutdown",
            "participant_left",
            "ended",
        )
    )


def _extract_transcript(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Tavus' transcript shapes into a list[{role, content}]."""
    candidates = (
        payload.get("transcript"),
        (payload.get("data") or {}).get("transcript"),
        (payload.get("properties") or {}).get("transcript"),
    )
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return [c for c in candidate if isinstance(c, dict)]
        if isinstance(candidate, str) and candidate.strip():
            return [{"role": "user", "content": candidate.strip()}]
    return []
