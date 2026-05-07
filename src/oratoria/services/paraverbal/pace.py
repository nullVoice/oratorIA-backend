"""Pace metrics (words-per-minute and rhythm variance) — placeholder."""

from __future__ import annotations


def classify_pace(wpm: float) -> str:
    """Bucket WPM into a qualitative label (Spanish-tuned)."""
    if wpm < 90:
        return "lento"
    if wpm < 130:
        return "moderado"
    if wpm < 170:
        return "ágil"
    return "demasiado rápido"
