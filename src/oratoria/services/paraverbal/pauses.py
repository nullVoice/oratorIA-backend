"""Pause / silence ratio computation — placeholder."""

from __future__ import annotations


def pause_ratio(silent_seconds: float, total_seconds: float) -> float:
    if total_seconds <= 0:
        return 0.0
    return max(0.0, min(1.0, silent_seconds / total_seconds))
