"""OpenAI Whisper STT adapter."""

from __future__ import annotations

import io

from openai import AsyncOpenAI

from oratoria.config import settings
from oratoria.services.stt.base import (
    BaseSTT,
    TranscriptionResult,
    TranscriptionSegment,
)


class WhisperSTT(BaseSTT):
    def __init__(self, model: str | None = None) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._model = model or settings.whisper_model

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "es",
        prompt: str | None = None,
    ) -> TranscriptionResult:
        buf = io.BytesIO(audio)
        buf.name = "audio.webm"

        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=buf,
            language=language,
            prompt=prompt,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

        raw = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        segments = [
            TranscriptionSegment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=str(s.get("text", "")).strip(),
            )
            for s in raw.get("segments", []) or []
        ]
        return TranscriptionResult(
            text=raw.get("text", "").strip(),
            language=raw.get("language", language),
            duration_seconds=float(raw.get("duration", 0.0) or 0.0),
            segments=segments,
            raw=raw,
        )
