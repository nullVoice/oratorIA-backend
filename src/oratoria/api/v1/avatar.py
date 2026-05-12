"""Avatar (Tavus) conversation endpoints.

Two endpoints under /api/v1/sessions/{session_id}/avatar-*:
  * POST avatar-start — provisions a Tavus conversation and returns the URL.
  * POST avatar-end   — ends the Tavus conversation; if a transcript is already
                        available, the EvaluatorAgent is invoked synchronously
                        to produce a Report (same pipeline as /evaluate).

Tavus pushes a final transcript via the webhook in api/v1/webhooks.py; this
endpoint also serves as a manual fallback when the webhook hasn't arrived yet.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from oratoria.ai.agents.evaluator import EvaluatorAgent
from oratoria.ai.prompts.audience_prompt import (
    build_audience_context,
    build_custom_greeting,
)
from oratoria.config import settings
from oratoria.core.security import current_active_user
from oratoria.dependencies import get_db
from oratoria.models import (
    AvatarConversation,
    AvatarConversationStatus,
    Report,
    Session as SessionModel,
    Transcript,
)
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import User
from oratoria.ai.parsers.feedback_schema import ParaverbalMetrics
from oratoria.services.avatar import get_avatar_service
from oratoria.services.paraverbal.filler_words import (
    count_fillers,
    words_per_minute,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================== Schemas ==============================


class AvatarStartRequest(BaseModel):
    interactive: bool = False


class AvatarStartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: str
    conversation_url: str
    interactive: bool
    persona_id: str
    replica_id: str
    started_at: datetime


class AvatarEndResponse(BaseModel):
    conversation_id: str
    status: str
    report_ready: bool


# ============================== Helpers ==============================


def _require_tavus_configured() -> tuple[str, str]:
    if not (
        settings.tavus_api_key
        and settings.tavus_persona_id
        and settings.tavus_replica_id
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El modo Audiencia Digital no está disponible (Tavus no configurado).",
        )
    return settings.tavus_persona_id, settings.tavus_replica_id


def _callback_url() -> str | None:
    base = settings.tavus_callback_base_url
    if not base:
        return None
    return f"{base.rstrip('/')}/api/v1/webhooks/tavus"


async def _normalize_avatar_transcript(
    transcript: list[dict[str, Any]] | None,
) -> str:
    """Convert Tavus transcript events into a single Spanish utterance string.

    Tavus typically returns a list of `{role, content, ...}` items. We keep
    only what the user said (role == 'user' / 'participant') so the evaluator
    grades the presenter, not the avatar's questions.
    """
    if not transcript:
        return ""
    pieces: list[str] = []
    for item in transcript:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("speaker") or "").lower()
        content = item.get("content") or item.get("text") or ""
        if not isinstance(content, str) or not content.strip():
            continue
        if role in {"user", "participant", "human", "presenter"} or role == "":
            pieces.append(content.strip())
    return " ".join(pieces).strip()


# ============================== Endpoints ==============================


@router.post(
    "/{session_id}/avatar-start",
    response_model=AvatarStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def avatar_start(
    session_id: uuid.UUID,
    payload: AvatarStartRequest,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> AvatarStartResponse:
    persona_id, replica_id = _require_tavus_configured()

    sess = await db.get(SessionModel, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.type != SessionType.LIVE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El modo Audiencia Digital sólo aplica a sesiones en vivo.",
        )

    ctx = sess.context or {}
    conversational_context = build_audience_context(
        segment=getattr(user, "segment", None),
        presentation_type=ctx.get("presentation_type"),
        audience=ctx.get("audience"),
        objective=ctx.get("objective"),
        formality=ctx.get("formality"),
        duration_target=ctx.get("duration_target"),
        interactive=payload.interactive,
        user_full_name=user.full_name,
    )
    greeting = build_custom_greeting(
        user_full_name=user.full_name, segment=getattr(user, "segment", None)
    )

    avatar = get_avatar_service()
    try:
        conversation = await avatar.create_conversation(
            persona_id=persona_id,
            replica_id=replica_id,
            conversational_context=conversational_context,
            custom_greeting=greeting,
            conversation_name=f"oratoria-{session_id}",
            callback_url=_callback_url(),
            max_call_duration_seconds=settings.tavus_max_call_duration_seconds,
            language="spanish",
        )
    except Exception as exc:  # noqa: BLE001 — bubble a clear 503 to the client
        logger.exception("Tavus create_conversation failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"No pudimos iniciar la conversación con el avatar: {type(exc).__name__}",
        ) from exc

    row = AvatarConversation(
        session_id=sess.id,
        provider="tavus",
        provider_conversation_id=conversation.conversation_id,
        conversation_url=conversation.conversation_url,
        replica_id=replica_id,
        persona_id=persona_id,
        interactive=payload.interactive,
        status=AvatarConversationStatus.ACTIVE,
        started_at=conversation.started_at,
    )
    db.add(row)
    sess.status = SessionStatus.IN_PROGRESS
    sess.context = {
        **(sess.context or {}),
        "avatar_provider": "tavus",
        "avatar_interactive": payload.interactive,
    }
    await db.commit()
    await db.refresh(row)

    return AvatarStartResponse(
        conversation_id=row.provider_conversation_id,
        conversation_url=row.conversation_url,
        interactive=row.interactive,
        persona_id=row.persona_id,
        replica_id=row.replica_id,
        started_at=row.started_at,
    )


@router.post("/{session_id}/avatar-end", response_model=AvatarEndResponse)
async def avatar_end(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> AvatarEndResponse:
    sess = await db.get(SessionModel, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")

    convo_row = (
        await db.execute(
            select(AvatarConversation)
            .where(
                AvatarConversation.session_id == sess.id,
                AvatarConversation.status == AvatarConversationStatus.ACTIVE,
            )
            .order_by(AvatarConversation.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if convo_row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No hay conversación de avatar activa para esta sesión.",
        )

    avatar = get_avatar_service()
    try:
        await avatar.end_conversation(convo_row.provider_conversation_id)
    except Exception:  # noqa: BLE001 — already-ended is fine; we still close locally
        logger.warning(
            "Failed to end Tavus conversation %s; closing locally",
            convo_row.provider_conversation_id,
        )

    convo_row.status = AvatarConversationStatus.ENDED
    convo_row.ended_at = datetime.now(timezone.utc)
    if convo_row.started_at and convo_row.ended_at:
        convo_row.duration_seconds = int(
            (convo_row.ended_at - convo_row.started_at).total_seconds()
        )

    # If the webhook already populated the transcript, run the evaluator now
    # so the user can navigate to the report immediately.
    report_ready = False
    if convo_row.transcript:
        try:
            await _evaluate_avatar_session(db, sess, convo_row)
            report_ready = True
        except Exception:  # noqa: BLE001 — don't block the end-call response
            logger.exception(
                "EvaluatorAgent failed for session %s after avatar end", sess.id
            )

    await db.commit()

    return AvatarEndResponse(
        conversation_id=convo_row.provider_conversation_id,
        status=convo_row.status.value,
        report_ready=report_ready,
    )


async def _evaluate_avatar_session(
    db: DBSession,
    sess: SessionModel,
    convo: AvatarConversation,
) -> None:
    """Run the EvaluatorAgent over the avatar transcript and persist a Report.

    Idempotent: if a report already exists for the session, we don't create a
    second one — this can be called both from /avatar-end and from the webhook.
    """
    existing = (
        await db.execute(select(Report).where(Report.session_id == sess.id))
    ).scalar_one_or_none()
    if existing:
        return

    transcript_text = await _normalize_avatar_transcript(convo.transcript)
    if not transcript_text:
        return

    duration = float(convo.duration_seconds or 0)
    metrics = ParaverbalMetrics(
        words_per_minute=round(words_per_minute(transcript_text, duration), 2)
        if duration > 0
        else 0.0,
        filler_words_count=count_fillers(transcript_text),
        pause_ratio=0.0,
        tone_variance=0.0,
        notes=(
            "Métricas paraverbales parciales: en el modo Audiencia Digital no "
            "se graba audio del usuario, por lo que el ratio de pausas y la "
            "variación tonal no están disponibles."
        ),
    )
    agent = EvaluatorAgent()
    evaluation = await agent.evaluate(
        transcript=transcript_text,
        context=sess.context or {},
        paraverbal_metrics=metrics,
    )

    db.add(
        Transcript(
            session_id=sess.id,
            text=transcript_text,
            language="es",
            segments=convo.transcript or [],
        )
    )
    db.add(
        Report(
            session_id=sess.id,
            score=evaluation.score,
            summary=evaluation.summary,
            strengths=[s.model_dump() for s in evaluation.strengths],
            improvements=[i.model_dump() for i in evaluation.improvements],
            paraverbal_metrics=evaluation.paraverbal_metrics.model_dump(),
            next_steps=evaluation.next_steps,
        )
    )
    sess.status = SessionStatus.COMPLETED
    sess.ended_at = datetime.now(timezone.utc)
    if convo.duration_seconds and not sess.duration_seconds:
        sess.duration_seconds = convo.duration_seconds
    await db.flush()
