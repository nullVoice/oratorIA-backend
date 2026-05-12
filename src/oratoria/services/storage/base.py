"""Storage contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str: ...

    @abstractmethod
    async def get_url(self, key: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    async def download(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...
