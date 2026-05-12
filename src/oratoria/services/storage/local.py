"""Local filesystem storage — dev/test fallback when R2 is not configured."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import aiofiles
import aiofiles.os

from oratoria.services.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class LocalStorage(BaseStorage):
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(tempfile.gettempdir()) / "oratoria-storage"
        self._root.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "Using LocalStorage fallback (R2 not configured). Files at %s",
            self._root,
        )

    def _path(self, key: str) -> Path:
        return self._root / key

    async def put(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return path.resolve().as_uri()

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        return await self.put(key, data, content_type)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        return self._path(key).resolve().as_uri()

    async def delete(self, key: str) -> None:
        try:
            await aiofiles.os.remove(self._path(key))
        except FileNotFoundError:
            pass
