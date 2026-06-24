"""Practice flow endpoints.

- POST /api/v1/practice/transcribe        (multipart audio → Whisper text)
  Called repeatedly during a recording with the cumulative audio so far.
  The response is the full transcript Whisper produced for that audio.

- POST /api/v1/practice/finalize          (JSON metrics + transcript → LLM
                                          → persisted Session + Transcript + Report)
  Called once when the user stops recording. The endpoint:
    1. Asks Claude (or GPT-4o as fallback) for a structured evaluation
       (score, summary, one strength, one improvement).
    2. Persists a Session row (status=COMPLETED), a Transcript row,
       and a Report row owned by the current user.
    3. Returns the report JSON plus the new `id` so the frontend can
       deep-link to /sessions/:id later.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from textwrap import dedent

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from oratoria.config import settings
from oratoria.core.security import current_active_user
from oratoria.dependencies import get_db
from oratoria.models import Report, Transcript
from oratoria.models import Session as SessionModel
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import User
from oratoria.services.stt.whisper import WhisperSTT

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------------------ Deepgram token --------------------------------

_DEEPGRAM_GRANT_URL = "https://api.deepgram.com/v1/auth/grant"
_DEEPGRAM_GRANT_TTL = 30  # seconds — short enough to be single-use


class DeepgramTokenResponse(BaseModel):
    token: str
    expires_in: int


@router.post("/deepgram-token", response_model=DeepgramTokenResponse)
async def get_deepgram_token(
    user: User = Depends(current_active_user),
) -> DeepgramTokenResponse:
    """Return a Deepgram credential the browser can use to open a streaming WS.

    Token minting strategy (attempted in order):

    1. **grant-token** — ``POST /v1/auth/grant`` → short-lived ``access_token``
       (requires the key to have the ``grant-token`` scope; preferred).
    2. **Management API temp key** — ``POST /v1/projects/{id}/keys`` with a
       30-second TTL and ``usage:write`` scope (requires ``keys:write``).
    3. **Direct key fallback** — if neither is available (e.g. a usage-only
       key with no management scopes) the raw API key is returned directly.
       The endpoint still acts as an auth gate (user JWT required), so the key
       is only visible to authenticated sessions.  Replace the key with a
       ``keys:write``-capable key in production to enable ephemeral tokens.
    """
    api_key = settings.deepgram_api_key
    if not api_key or not api_key.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DEEPGRAM_API_KEY is not configured on the server.",
        )

    raw_key = api_key.get_secret_value()
    headers = {"Authorization": f"Token {raw_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        # --- Attempt 1: grant-token ---
        try:
            resp = await client.post(
                _DEEPGRAM_GRANT_URL,
                headers=headers,
                json={"ttl_seconds": _DEEPGRAM_GRANT_TTL},
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info("Deepgram token minted via grant-token")
                return DeepgramTokenResponse(
                    token=data["access_token"],
                    expires_in=data.get("expires_in", _DEEPGRAM_GRANT_TTL),
                )
            logger.debug(
                "Deepgram grant-token returned %s — trying management API",
                resp.status_code,
            )
        except httpx.HTTPError as exc:
            logger.warning("Deepgram grant-token request failed: %s", exc)

        # --- Attempt 2: Management API temp key ---
        try:
            projects_resp = await client.get(
                "https://api.deepgram.com/v1/projects", headers=headers
            )
            if projects_resp.status_code == 200:
                projects = projects_resp.json().get("projects", [])
                if projects:
                    project_id = projects[0]["project_id"]
                    key_resp = await client.post(
                        f"https://api.deepgram.com/v1/projects/{project_id}/keys",
                        headers=headers,
                        json={
                            "comment": "OratorIA ephemeral browser key",
                            "scopes": ["usage:write"],
                            "time_to_live_in_seconds": _DEEPGRAM_GRANT_TTL,
                        },
                    )
                    if key_resp.status_code in (200, 201):
                        key_data = key_resp.json()
                        logger.info("Deepgram token minted via management API temp key")
                        return DeepgramTokenResponse(
                            token=key_data["key"],
                            expires_in=_DEEPGRAM_GRANT_TTL,
                        )
                    logger.debug("Deepgram temp-key creation returned %s", key_resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Deepgram management API request failed: %s", exc)

        # No ephemeral token could be minted. We deliberately do NOT fall back to
        # returning the raw long-lived API key to the browser — that would leak a
        # production credential to every authenticated client. The Deepgram key
        # must have `grant-token` or `keys:write` scope in production.
        logger.error(
            "Deepgram ephemeral token unavailable and raw-key fallback is "
            "disabled; grant the API key 'grant-token'/'keys:write' scope."
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Live transcription is temporarily unavailable.",
        )


# --------------------------------- Transcribe ---------------------------------


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_seconds: float


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio chunk (webm/ogg/mp3)"),
    user: User = Depends(current_active_user),
) -> TranscribeResponse:
    if not settings.openai_api_key or not settings.openai_api_key.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OPENAI_API_KEY is not configured on the server.",
        )

    audio = await file.read()
    if not audio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio payload.")

    stt = WhisperSTT()
    result = await stt.transcribe(audio, language="es")
    duration = max((s.end for s in result.segments), default=0.0) if result.segments else 0.0
    return TranscribeResponse(
        text=result.text,
        language=result.language,
        duration_seconds=duration,
    )


# ---------------------------------- Finalize ----------------------------------


class FillerWordCount(BaseModel):
    word: str
    count: int


class FinalizePayload(BaseModel):
    transcript: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    filler_words_count: int = Field(ge=0)
    filler_by_word: list[FillerWordCount] = Field(default_factory=list)
    words_per_minute: float = Field(ge=0)
    presentation_type: str = "presentación general"
    audience: str = "audiencia mixta"


class FinalizeResponse(BaseModel):
    id: uuid.UUID
    score: int = Field(ge=0, le=100)
    summary: str
    strength_title: str
    strength_text: str
    improvement_title: str
    improvement_text: str


class _LlmEvaluation(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str
    strength_title: str
    strength_text: str
    improvement_title: str
    improvement_text: str


_SYSTEM_PROMPT = dedent("""
    Eres OratorIA Coach, un coach experto en oratoria. Recibirás la transcripción de
    una práctica corta de un usuario más métricas paraverbales calculadas. Tu trabajo:

    1) Asignar un score global 0-100 basado en estas tres dimensiones:
        - Verbal (40%): claridad, estructura, vocabulario.
        - Paraverbal (35%): ritmo (WPM), muletillas.
        - Estratégica (25%): adecuación al tipo y a la audiencia.
    2) Resumir en una frase clara qué tan bien lo hizo.
    3) Identificar UNA sola fortaleza concreta (con cita o evidencia textual breve).
    4) Identificar UNA sola mejora accionable (con sugerencia específica).

    Reglas:
    - En español neutro.
    - Si la transcripción es muy corta o vacía, sé honesto en el score.
    - WPM saludable está entre 110 y 160. Fuera de ese rango menciónalo en la mejora.
    - 0 muletillas es excelente; >5 cada minuto es alto.
    - Tu salida debe ser SOLO un JSON con estas claves exactas, sin texto adicional,
      sin bloques markdown:

      {
        "score": <int 0-100>,
        "summary": "<una frase>",
        "strength_title": "<título corto>",
        "strength_text": "<una frase con evidencia>",
        "improvement_title": "<título corto>",
        "improvement_text": "<una frase con sugerencia accionable>"
      }
""").strip()


def _build_evaluator_llm() -> tuple[BaseChatModel | None, str]:
    """Prefer Claude; fall back to GPT-4o; return (None, "none") otherwise."""
    if settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value():
        return (
            ChatAnthropic(
                model_name=settings.anthropic_model,
                temperature=0.3,
                max_tokens=1024,
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=45,
                stop=None,
            ),
            f"anthropic:{settings.anthropic_model}",
        )
    if settings.openai_api_key and settings.openai_api_key.get_secret_value():
        return (
            ChatOpenAI(
                model=settings.openai_model,
                temperature=0.3,
                max_tokens=1024,
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=45,
                model_kwargs={"response_format": {"type": "json_object"}},
            ),
            f"openai:{settings.openai_model}",
        )
    return None, "none"


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_practice(
    payload: FinalizePayload,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> FinalizeResponse:
    llm, provider = _build_evaluator_llm()
    if llm is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is configured on the server.",
        )

    user_msg = dedent(f"""
        ## Contexto de la sesión
        - Tipo: {payload.presentation_type}
        - Audiencia: {payload.audience}
        - Duración real: {payload.duration_seconds:.1f} segundos
        - Palabras por minuto: {payload.words_per_minute:.1f}
        - Muletillas detectadas: {payload.filler_words_count}

        ## Transcripción
        {payload.transcript}

        Genera el JSON pedido siguiendo EXACTAMENTE la estructura indicada.
    """).strip()

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_msg)]
        )
    except Exception as e:
        logger.exception("Finalize call failed via %s", provider)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"AI provider error: {type(e).__name__}",
        ) from e

    raw = response.content if isinstance(response.content, str) else str(response.content)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        evaluation = _LlmEvaluation.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        logger.exception("Failed to parse finalize response from %s: %r", provider, raw[:300])
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI returned an unparseable response. Please retry.",
        )

    # Persist the session, transcript, and report so the dashboard /sessions
    # endpoints can surface them later.
    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=max(payload.duration_seconds, 1))

    session = SessionModel(
        user_id=user.id,
        type=SessionType.LIVE,
        status=SessionStatus.COMPLETED,
        context={
            "presentation_type": payload.presentation_type,
            "audience": payload.audience,
        },
        started_at=started_at,
        ended_at=now,
        duration_seconds=int(round(payload.duration_seconds)),
    )
    db.add(session)
    await db.flush()

    db.add(
        Transcript(
            session_id=session.id,
            text=payload.transcript,
            language="es",
        )
    )

    db.add(
        Report(
            session_id=session.id,
            score=evaluation.score,
            strengths=[
                {
                    "title": evaluation.strength_title,
                    "text": evaluation.strength_text,
                }
            ],
            improvements=[
                {
                    "title": evaluation.improvement_title,
                    "text": evaluation.improvement_text,
                }
            ],
            paraverbal_metrics={
                "words_per_minute": payload.words_per_minute,
                "filler_words_count": payload.filler_words_count,
                "filler_by_word": [f.model_dump() for f in payload.filler_by_word],
                "duration_seconds": payload.duration_seconds,
            },
            summary=evaluation.summary,
            next_steps=[],
        )
    )
    await db.commit()

    return FinalizeResponse(
        id=session.id,
        score=evaluation.score,
        summary=evaluation.summary,
        strength_title=evaluation.strength_title,
        strength_text=evaluation.strength_text,
        improvement_title=evaluation.improvement_title,
        improvement_text=evaluation.improvement_text,
    )
