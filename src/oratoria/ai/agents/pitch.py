"""Pitch-rewriter agent: transcript + how they spoke → structured, better-told pitch."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser

from oratoria.ai.llm.factory import get_evaluator_llm
from oratoria.ai.parsers.feedback_schema import ParaverbalMetrics, StructuredPitch
from oratoria.ai.prompts.pitch_prompt import build_pitch_prompt

_CONTEXT_DEFAULTS: dict[str, Any] = {
    "presentation_type": "presentación general",
    "audience": "audiencia mixta",
    "objective": "comunicar con claridad y persuadir",
    "formality": "profesional",
    "duration_target": 5,
}


class PitchRewriterAgent:
    """Rewrites the user's speech into a structured pitch with a stronger arc."""

    def __init__(self, temperature: float = 0.5, max_tokens: int = 2048) -> None:
        self._parser = PydanticOutputParser(pydantic_object=StructuredPitch)
        self._prompt = build_pitch_prompt().partial(
            format_instructions=self._parser.get_format_instructions()
        )
        # Same provider strategy as the evaluator (Claude first, GPT-4o fallback).
        self._llm = get_evaluator_llm(temperature=temperature, max_tokens=max_tokens)
        self._chain = self._prompt | self._llm | self._parser

    async def rewrite(
        self,
        transcript: str,
        context: dict[str, Any],
        paraverbal_metrics: ParaverbalMetrics | dict[str, Any],
    ) -> StructuredPitch:
        metrics_payload = (
            paraverbal_metrics.model_dump_json(indent=2)
            if isinstance(paraverbal_metrics, ParaverbalMetrics)
            else json.dumps(paraverbal_metrics, ensure_ascii=False, indent=2)
        )
        ctx = {**_CONTEXT_DEFAULTS, **context}
        return await self._chain.ainvoke(
            {
                "transcript": transcript,
                "paraverbal_metrics": metrics_payload,
                "presentation_type": ctx["presentation_type"],
                "audience": ctx["audience"],
                "objective": ctx["objective"],
                "formality": ctx["formality"],
                "duration_target": ctx["duration_target"],
            }
        )


async def try_generate_pitch(
    transcript: str,
    context: dict[str, Any],
    paraverbal_metrics: ParaverbalMetrics | dict[str, Any],
) -> dict[str, Any] | None:
    """Best-effort pitch generation.

    Returns the pitch as a plain dict (ready to store on Report.structured_pitch),
    or None if anything goes wrong. NEVER raises: the pitch is an enhancement, so
    a failure here must not break the evaluation/report pipeline.
    """
    import logging

    logger = logging.getLogger(__name__)
    if not transcript or not transcript.strip():
        return None
    try:
        pitch = await PitchRewriterAgent().rewrite(transcript, context, paraverbal_metrics)
        return pitch.model_dump()
    except Exception:
        logger.exception("PitchRewriterAgent failed; continuing without structured pitch")
        return None
