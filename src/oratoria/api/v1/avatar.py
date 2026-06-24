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
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from oratoria.ai.agents.evaluator import EvaluatorAgent
from oratoria.ai.parsers.feedback_schema import ParaverbalMetrics
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
    Transcript,
)
from oratoria.models import (
    Session as SessionModel,
)
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import User
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


class AvatarEndRequest(BaseModel):
    """Body for /avatar-end. The frontend ships the Daily app-message stream
    captured from the Tavus Interactions Protocol — utterances with Raven-1
    analyses, started/stopped speaking events, etc.
    """

    events: list[dict[str, Any]] = []


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
    if not (settings.tavus_api_key and settings.tavus_persona_id and settings.tavus_replica_id):
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
            session_id=str(session_id),
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        logger.warning("Tavus create_conversation failed: %s %s", code, exc.response.text[:200])
        if code == 402:
            # Tavus: "out of conversational credits"
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                "El modo Audiencia Digital se quedó sin créditos por ahora. "
                "Probá con la Práctica simple mientras tanto.",
            ) from exc
        if code == 429:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Hay demasiadas sesiones de avatar en curso. Esperá unos "
                "segundos y volvé a intentar.",
            ) from exc
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No pudimos iniciar la audiencia digital en este momento. "
            "Volvé a intentar en un ratito o usá la Práctica simple.",
        ) from exc
    except Exception as exc:
        logger.exception("Tavus create_conversation failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No pudimos iniciar la audiencia digital en este momento. "
            "Volvé a intentar en un ratito o usá la Práctica simple.",
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
    payload: AvatarEndRequest | None = None,
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
    except Exception:
        logger.warning(
            "Failed to end Tavus conversation %s; closing locally",
            convo_row.provider_conversation_id,
        )

    convo_row.status = AvatarConversationStatus.ENDED
    convo_row.ended_at = datetime.now(UTC)
    if convo_row.started_at and convo_row.ended_at:
        convo_row.duration_seconds = int(
            (convo_row.ended_at - convo_row.started_at).total_seconds()
        )

    # Persist Daily app-message stream coming from the client. We dedup
    # vs whatever the webhook may have already written.
    if payload and payload.events:
        existing_events = convo_row.events or []
        seen_seqs = {e.get("seq") for e in existing_events if isinstance(e.get("seq"), int)}
        new_events = [
            e
            for e in payload.events
            if not (isinstance(e.get("seq"), int) and e.get("seq") in seen_seqs)
        ]
        convo_row.events = existing_events + new_events
        logger.info(
            "stored %d client events for conversation %s (total %d)",
            len(new_events),
            convo_row.provider_conversation_id,
            len(convo_row.events),
        )

        # Derive a transcript from the events if the webhook hasn't fired.
        if not convo_row.transcript:
            derived = _transcript_from_events(convo_row.events)
            if derived:
                convo_row.transcript = derived

    # If the webhook hasn't delivered a transcript yet (common in local dev
    # where the backend isn't publicly reachable), poll Tavus directly for
    # a short window. Webhook + polling are belt-and-suspenders.
    if not convo_row.transcript:
        transcript = await _poll_tavus_transcript(
            convo_row.provider_conversation_id, max_attempts=8, delay=2.0
        )
        if transcript:
            convo_row.transcript = transcript

    # If we have a transcript (from webhook or polling) run the evaluator
    # so the frontend can navigate to the report immediately.
    report_ready = False
    if convo_row.transcript:
        try:
            await _evaluate_avatar_session(db, sess, convo_row)
            report_ready = True
        except Exception:
            logger.exception("EvaluatorAgent failed for session %s after avatar end", sess.id)

    # Fallback: Tavus exposes transcripts only via webhook. If we couldn't
    # reach it (no public TAVUS_CALLBACK_BASE_URL, e.g. running on
    # localhost), the polling above will time out. Produce a placeholder
    # Report so the frontend doesn't hang forever and the user sees a
    # clear message instead.
    # Only fall back to a placeholder when there is genuinely no way for the
    # webhook to reach us (no public callback URL). When a callback IS
    # configured, the Tavus transcription_ready webhook will arrive shortly and
    # produce the real report; the frontend polls GET /sessions/:id meanwhile.
    # Creating a placeholder here would otherwise force the user onto a useless
    # score-0 report before the real one lands.
    if not report_ready and _callback_url() is None:
        try:
            await _create_placeholder_avatar_report(db, sess)
            report_ready = True
        except Exception:
            logger.exception("could not create placeholder report for session %s", sess.id)

    await db.commit()

    return AvatarEndResponse(
        conversation_id=convo_row.provider_conversation_id,
        status=convo_row.status.value,
        report_ready=report_ready,
    )


def _build_perception_data(convo: AvatarConversation) -> str:
    """Compose a string the EvaluatorAgent prompt can read.

    Two sources:
      1. Per-utterance Raven-1 analyses inside `events` (user turns only —
         that's what we want to grade).
      2. The final `perception_analysis` summary from the webhook.
    """
    chunks: list[str] = []

    if convo.events:
        turn_lines: list[str] = []
        for ev in convo.events:
            if not isinstance(ev, dict):
                continue
            if ev.get("event_type") != "conversation.utterance":
                continue
            props = ev.get("properties") or {}
            role = str(props.get("role") or props.get("speaker") or "").lower()
            if role and role not in {"user", "participant", "human"}:
                continue
            visual = props.get("user_visual_analysis")
            audio = props.get("user_audio_analysis")
            if not (isinstance(visual, str) or isinstance(audio, str)):
                continue
            line_parts: list[str] = []
            if isinstance(visual, str) and visual.strip():
                line_parts.append(f"visual: {visual.strip()}")
            if isinstance(audio, str) and audio.strip():
                line_parts.append(f"audio: {audio.strip()}")
            if line_parts:
                turn_lines.append("- " + "; ".join(line_parts))
        if turn_lines:
            chunks.append("### Observaciones por turno (Raven-1)\n" + "\n".join(turn_lines))

    if convo.perception_analysis:
        try:
            chunks.append(
                "### Resumen perceptual final\n"
                + json.dumps(convo.perception_analysis, ensure_ascii=False, indent=2)
            )
        except (TypeError, ValueError):
            chunks.append("### Resumen perceptual final\n" + str(convo.perception_analysis))

    if not chunks:
        return "No hay datos perceptuales disponibles para esta sesión."

    return "\n\n".join(chunks)


def _transcript_from_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a [{role, content, visual, audio}] list from app-message events.

    Tavus emits one `conversation.utterance` per turn with the role and
    content under `properties.role` / `properties.speech`. When Raven-1 is
    active and the speaker is the user, `properties.user_visual_analysis`
    and `properties.user_audio_analysis` are also there.
    """
    out: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("event_type") != "conversation.utterance":
            continue
        props = ev.get("properties") or {}
        role = props.get("role") or props.get("speaker") or "user"
        content = props.get("speech") or props.get("content") or props.get("text") or ""
        if not isinstance(content, str) or not content.strip():
            continue
        item: dict[str, Any] = {"role": str(role), "content": content.strip()}
        for key in ("user_visual_analysis", "user_audio_analysis"):
            v = props.get(key)
            if isinstance(v, str) and v.strip():
                item[key] = v.strip()
        out.append(item)
    return out


async def _poll_tavus_transcript(
    conversation_id: str, *, max_attempts: int, delay: float
) -> list[dict[str, Any]] | None:
    """Poll Tavus' GET /conversations/{id} until a transcript appears.

    Tavus exposes the transcript on the conversation object once the call
    has fully wound down. This is the fallback for local dev where the
    webhook isn't reachable.
    """
    import asyncio

    avatar = get_avatar_service()
    for attempt in range(max_attempts):
        await asyncio.sleep(delay if attempt else 1.5)
        try:
            convo = await avatar.get_conversation(conversation_id)
        except Exception:
            logger.exception(
                "polling Tavus conversation %s failed (attempt %d)",
                conversation_id,
                attempt,
            )
            continue

        events: list[dict[str, Any]] = []
        raw_events = convo.raw.get("events") if convo.raw else None
        if isinstance(raw_events, list):
            for ev in raw_events:
                if not isinstance(ev, dict):
                    continue
                # Tavus puts the user transcript in
                # events[*].properties.transcript as text, or as a list.
                props = ev.get("properties") or {}
                t = props.get("transcript")
                if isinstance(t, list) and t:
                    events.extend(x for x in t if isinstance(x, dict))
                elif isinstance(t, str) and t.strip():
                    events.append({"role": "user", "content": t.strip()})
        if not events and convo.raw:
            # Some payloads expose `transcript` at the top level.
            top = convo.raw.get("transcript")
            if isinstance(top, list):
                events.extend(x for x in top if isinstance(x, dict))
            elif isinstance(top, str) and top.strip():
                events.append({"role": "user", "content": top.strip()})

        if events:
            logger.info(
                "polled %d transcript items for conversation %s",
                len(events),
                conversation_id,
            )
            return events

    logger.warning(
        "Tavus transcript not available after %d attempts for conversation %s",
        max_attempts,
        conversation_id,
    )
    return None


_PLACEHOLDER_SUMMARY = (
    "No pudimos obtener el transcript de tu sesión con el avatar. Tavus "
    "entrega el transcript exclusivamente por webhook, y este backend no "
    "es alcanzable desde Tavus en este momento. Para que el modo "
    "Audiencia Digital genere un reporte completo, expón el backend con "
    "un túnel HTTPS (cloudflared/ngrok) y configura su URL "
    "+ /api/v1/webhooks/tavus en el portal de Tavus."
)


async def _create_placeholder_avatar_report(db: DBSession, sess: SessionModel) -> None:
    """Generate a stub Report when Tavus' transcript never arrived.

    Idempotent: skips if a Report already exists for the session.
    """
    existing = (
        await db.execute(select(Report).where(Report.session_id == sess.id))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(
        Report(
            session_id=sess.id,
            score=0,
            summary=_PLACEHOLDER_SUMMARY,
            strengths=[],
            improvements=[
                {
                    "title": "Configurar webhook de Tavus",
                    "description": (
                        "Para obtener el transcript del modo Audiencia Digital "
                        "Tavus necesita poder alcanzar este backend con HTTPS."
                    ),
                    "dimension": "strategic",
                    "evidence": (
                        "El polling REST a /v2/conversations/<id> no expone el "
                        "transcript — verificado contra la API en runtime."
                    ),
                    "suggestion": (
                        "Ejecuta `cloudflared tunnel --url http://localhost:8000` "
                        "(o ngrok), copia la URL HTTPS, ponla en "
                        "TAVUS_CALLBACK_BASE_URL del .env y configura la misma "
                        "URL + /api/v1/webhooks/tavus en el dashboard de Tavus."
                    ),
                    "priority": "high",
                }
            ],
            paraverbal_metrics={
                "words_per_minute": 0,
                "filler_words_count": 0,
                "pause_ratio": 0,
                "tone_variance": 0,
                "notes": "Métricas no disponibles sin transcript del avatar.",
            },
            next_steps=[
                "Configura cloudflared/ngrok para exponer el backend.",
                "Mientras tanto, usa el modo de práctica simple (no avatar).",
            ],
        )
    )
    sess.status = SessionStatus.COMPLETED
    sess.ended_at = datetime.now(UTC)
    await db.flush()


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
    if existing is not None:
        # A placeholder report (created by avatar-end when no transcript was
        # available yet) must NOT shadow the real evaluation once the Tavus
        # webhook delivers the transcript. Replace the placeholder; keep any
        # genuine report (idempotency for double webhook/avatar-end calls).
        if existing.summary == _PLACEHOLDER_SUMMARY:
            await db.delete(existing)
            await db.flush()
        else:
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

    perception_data = _build_perception_data(convo)

    agent = EvaluatorAgent()
    evaluation = await agent.evaluate(
        transcript=transcript_text,
        context=sess.context or {},
        paraverbal_metrics=metrics,
        perception_data=perception_data,
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
    sess.ended_at = datetime.now(UTC)
    if convo.duration_seconds and not sess.duration_seconds:
        sess.duration_seconds = convo.duration_seconds
    await db.flush()
