"""Base TTS contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class BaseTTS(ABC):
    @abstractmethod
    async def synthesize(self, text: str, *, voice_id: str | None = None) -> bytes: ...

    @abstractmethod
    def stream(self, text: str, *, voice_id: str | None = None) -> AsyncIterator[bytes]: ...
