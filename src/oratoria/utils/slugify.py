"""Lightweight slugify (no external dep)."""

from __future__ import annotations

import re
import unicodedata


def slugify(value: str, *, max_len: int = 80) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:max_len].strip("-")
