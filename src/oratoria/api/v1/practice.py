"""Quick-eval practice endpoints — demo flow without session persistence.

Two endpoints:

- POST /api/v1/practice/transcribe        (multipart audio → Whisper text)
  Called repeatedly during a recording with the cumulative audio so far.
  The response is the full transcript Whisper produced for that audio.

- POST /api/v1/practice/finalize          (JSON metrics + transcript → LLM)
  Called once when the user stops recording. Returns a small structured
  evaluation: score 0-100 + summary + 1 strength + 1 improvement.
  Uses Claude if `ANTHROPIC_API_KEY` is set, otherwise falls back to
  GPT-4o via the OpenAI key. This keeps the demo working when the team
  only has one provider configured.

These endpoints are intentionally stateless. The persisted Session / Report
flow lives behind /sessions and is wired in Épica 4 proper.
"""

from __future__ import annotations

import json
import logging
from textwrap import dedent

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from oratoria.config import settings
from oratoria.core.security import current_active_user
from oratoria.models.user import User
from oratoria.services.stt.whisper import WhisperSTT

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------- Transcribe ---------------------------------


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_seconds: float


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio chunk (webm/ogg/mp3)"),
    user: User = Depends(current_active_user),  # noqa: ARG001 — enforces auth
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
    duration = (
        max((s.end for s in result.segments), default=0.0)
        if result.segments
        else 0.0
    )
    return TranscribeResponse(
        text=result.text,
        language=result.language,
        duration_seconds=duration,
    )


# ---------------------------------- Finalize ----------------------------------


class FinalizePayload(BaseModel):
    transcript: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    filler_words_count: int = Field(ge=0)
    words_per_minute: float = Field(ge=0)
    presentation_type: str = "presentación general"
    audience: str = "audiencia mixta"


class FinalizeResponse(BaseModel):
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


def _build_evaluator_llm() -> tuple[BaseChatModel, str]:
    """Pick whichever LLM we have credentials for.

    Prefers Claude (matches the production-target stack); falls back to
    GPT-4o so the demo still works when only the OpenAI key is set.
    Returns the chat model + a human-readable provider label for logs.
    """
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
                # GPT-4o native JSON mode — saves us a fence-stripping pass
                # and makes parsing much more reliable.
                model_kwargs={"response_format": {"type": "json_object"}},
            ),
            f"openai:{settings.openai_model}",
        )
    return None, "none"  # type: ignore[return-value]


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_practice(
    payload: FinalizePayload,
    user: User = Depends(current_active_user),  # noqa: ARG001 — enforces auth
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
    # Strip a fenced ```json ... ``` block if the model added one despite the instructions.
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        data = json.loads(raw)
        return FinalizeResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        logger.exception(
            "Failed to parse finalize response from %s: %r", provider, raw[:300]
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI returned an unparseable response. Please retry.",
        )
