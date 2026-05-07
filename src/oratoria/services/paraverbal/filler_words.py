"""Filler-word detection from transcripts (es-ES / es-LA)."""

from __future__ import annotations

import re

SPANISH_FILLERS: tuple[str, ...] = (
    "este", "eh", "ehh", "em", "mmm", "ah", "pues", "o sea",
    "este,", "como que", "tipo", "bueno", "vale", "okey", "okay",
    "y entonces", "digamos",
)

_TOKEN_RE = re.compile(r"\b[\wáéíóúñü]+\b", re.IGNORECASE)


def count_fillers(transcript: str, fillers: tuple[str, ...] = SPANISH_FILLERS) -> int:
    text = transcript.lower()
    total = 0
    for filler in fillers:
        if " " in filler:
            total += len(re.findall(rf"\b{re.escape(filler)}\b", text))
        else:
            total += len(re.findall(rf"\b{re.escape(filler)}\b", text))
    return total


def words_per_minute(transcript: str, duration_seconds: float) -> float:
    if duration_seconds <= 0:
        return 0.0
    tokens = _TOKEN_RE.findall(transcript)
    return len(tokens) / (duration_seconds / 60.0)
