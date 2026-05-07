"""Base STT contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    language: str = "es"
    segments: list[TranscriptionSegment] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class BaseSTT(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "es",
        prompt: str | None = None,
    ) -> TranscriptionResult: ...
