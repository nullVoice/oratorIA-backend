"""Paraverbal analyzer: words-per-minute, fillers, pause ratio, tone variance.

Wraps `librosa` (and optionally `pyannote.audio`) for acoustic features.
The heavy ML models are lazy-imported to keep cold starts fast and to allow
the rest of the service to boot without the full audio stack installed.
"""

from __future__ import annotations

import io
import math
from typing import TYPE_CHECKING

from oratoria.ai.parsers.feedback_schema import ParaverbalMetrics
from oratoria.services.paraverbal.filler_words import (
    count_fillers,
    words_per_minute,
)
from oratoria.services.paraverbal.pauses import pause_ratio

if TYPE_CHECKING:
    import numpy as np


class ParaverbalAnalyzer:
    """Compute paraverbal metrics from raw audio bytes + transcript."""

    def __init__(self, target_sr: int = 16000) -> None:
        self._target_sr = target_sr

    async def analyze(
        self,
        audio_bytes: bytes,
        *,
        transcript: str = "",
        duration_hint: float = 0.0,
    ) -> ParaverbalMetrics:
        # Lexical metrics (transcript-only) work even if the audio can't be
        # decoded acoustically.
        fillers = count_fillers(transcript) if transcript else 0

        try:
            import librosa  # type: ignore[import-not-found]
            import numpy as np

            y, sr = librosa.load(
                io.BytesIO(audio_bytes), sr=self._target_sr, mono=True
            )
            duration = float(librosa.get_duration(y=y, sr=sr))

            # Silence detection — librosa default top_db=60 is too aggressive.
            intervals = librosa.effects.split(y, top_db=30)
            voiced_seconds = (
                float(sum(end - start for start, end in intervals)) / sr
            )
            silent_seconds = max(0.0, duration - voiced_seconds)
            ratio = pause_ratio(silent_seconds, duration)

            # Tone variance via pYIN F0.
            f0, _, _ = librosa.pyin(
                y,
                fmin=float(librosa.note_to_hz("C2")),
                fmax=float(librosa.note_to_hz("C6")),
                sr=sr,
            )
            f0_voiced: np.ndarray = (
                f0[~np.isnan(f0)] if f0 is not None else np.array([])
            )
            tone_variance = float(np.var(f0_voiced)) if f0_voiced.size > 0 else 0.0
            if math.isnan(tone_variance) or math.isinf(tone_variance):
                tone_variance = 0.0

            wpm = words_per_minute(transcript, duration) if transcript else 0.0

            return ParaverbalMetrics(
                words_per_minute=round(wpm, 2),
                filler_words_count=fillers,
                pause_ratio=round(ratio, 3),
                tone_variance=round(tone_variance, 3),
                notes=None,
            )
        except Exception as exc:  # noqa: BLE001
            # Audio undecodable (e.g. webm/opus unsupported by libsndfile) or
            # the acoustic stack (Épica 6: torch/pyannote) not installed.
            # Degrade gracefully to transcript-only metrics instead of 500.
            wpm = (
                words_per_minute(transcript, duration_hint)
                if transcript and duration_hint > 0
                else 0.0
            )
            return ParaverbalMetrics(
                words_per_minute=round(wpm, 2),
                filler_words_count=fillers,
                pause_ratio=0.0,
                tone_variance=0.0,
                notes=f"Análisis acústico no disponible ({type(exc).__name__}).",
            )
