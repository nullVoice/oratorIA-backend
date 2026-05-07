"""ElevenLabs TTS adapter — Multilingual v2."""

from __future__ import annotations

from collections.abc import AsyncIterator

from elevenlabs.client import AsyncElevenLabs

from oratoria.config import settings
from oratoria.services.tts.base import BaseTTS


class ElevenLabsTTS(BaseTTS):
    def __init__(
        self,
        voice_id: str | None = None,
        model: str | None = None,
    ) -> None:
        if not settings.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured.")
        self._client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key.get_secret_value())
        self._voice_id = voice_id or settings.elevenlabs_voice_id
        self._model = model or settings.elevenlabs_model

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> bytes:
        chunks: list[bytes] = []
        async for chunk in self.stream(text, voice_id=voice_id):
            chunks.append(chunk)
        return b"".join(chunks)

    async def stream(
        self, text: str, *, voice_id: str | None = None
    ) -> AsyncIterator[bytes]:
        vid = voice_id or self._voice_id
        if not vid:
            raise RuntimeError("ELEVENLABS_VOICE_ID is required for synthesis.")
        async for chunk in self._client.text_to_speech.convert(
            voice_id=vid,
            text=text,
            model_id=self._model,
            output_format="mp3_44100_128",
        ):
            if chunk:
                yield chunk
