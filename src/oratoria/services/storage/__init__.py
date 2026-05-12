"""Object storage adapters."""

from __future__ import annotations

from functools import lru_cache

from oratoria.config import settings
from oratoria.services.storage.base import BaseStorage
from oratoria.services.storage.local import LocalStorage
from oratoria.services.storage.r2 import R2Storage


@lru_cache(maxsize=1)
def get_storage() -> BaseStorage:
    if (
        settings.r2_endpoint_url
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    ):
        return R2Storage()
    return LocalStorage()


__all__ = ["BaseStorage", "LocalStorage", "R2Storage", "get_storage"]
