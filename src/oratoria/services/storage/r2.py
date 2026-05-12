"""Cloudflare R2 storage adapter (S3-compatible)."""

from __future__ import annotations

import aioboto3

from oratoria.config import settings
from oratoria.services.storage.base import BaseStorage


class R2Storage(BaseStorage):
    def __init__(self) -> None:
        if not (
            settings.r2_endpoint_url
            and settings.r2_access_key_id
            and settings.r2_secret_access_key
        ):
            raise RuntimeError(
                "R2 storage is not fully configured "
                "(missing R2_ENDPOINT_URL / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY)."
            )
        self._endpoint = settings.r2_endpoint_url
        self._access_key = settings.r2_access_key_id.get_secret_value()
        self._secret_key = settings.r2_secret_access_key.get_secret_value()
        self._bucket = settings.r2_bucket
        self._session = aioboto3.Session()

    def _client(self):  # type: ignore[no-untyped-def]
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name="auto",
        )

    async def put(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        async with self._client() as s3:
            kwargs: dict[str, object] = {
                "Bucket": self._bucket,
                "Key": key,
                "Body": data,
            }
            if content_type:
                kwargs["ContentType"] = content_type
            await s3.put_object(**kwargs)
        return await self.get_url(key, expires_in=60 * 60 * 24 * 7)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        return await self.put(key, data, content_type)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    async def download(self, key: str) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self._bucket, Key=key)
            body = obj["Body"]
            data: bytes = await body.read()
            return data

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
