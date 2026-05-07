"""Cloudflare R2 storage adapter (S3-compatible) — stub."""

from __future__ import annotations

from oratoria.services.storage.base import BaseStorage


class R2Storage(BaseStorage):
    """TODO: implement using aioboto3 against the R2 endpoint."""

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:  # noqa: ARG002
        raise NotImplementedError

    async def get_url(self, key: str, expires_in: int = 3600) -> str:  # noqa: ARG002
        raise NotImplementedError

    async def delete(self, key: str) -> None:  # noqa: ARG002
        raise NotImplementedError
