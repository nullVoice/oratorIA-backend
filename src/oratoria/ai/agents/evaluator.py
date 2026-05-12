"""Evaluator agent: transcript + paraverbal metrics → structured EvaluationReport."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser

from oratoria.ai.llm.claude import build_claude
from oratoria.ai.parsers.feedback_schema import EvaluationReport, ParaverbalMetrics
from oratoria.ai.prompts.evaluator_prompt_v1 import build_evaluator_prompt

_CONTEXT_DEFAULTS: dict[str, Any] = {
    "presentation_type": "presentación general",
    "audience": "audiencia mixta",
    "objective": "comunicar con claridad y persuadir",
    "formality": "profesional",
    "duration_target": 5,
}


class EvaluatorAgent:
    """Wraps Claude + structured output parsing for speech evaluation."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self._parser = PydanticOutputParser(pydantic_object=EvaluationReport)
        self._prompt = build_evaluator_prompt().partial(
            format_instructions=self._parser.get_format_instructions()
        )
        self._llm = build_claude(temperature=temperature, max_tokens=max_tokens)
        if model:
            self._llm.model_name = model  # type: ignore[attr-defined]
        self._chain = self._prompt | self._llm | self._parser

    async def evaluate(
        self,
        transcript: str,
        context: dict[str, Any],
        paraverbal_metrics: ParaverbalMetrics | dict[str, Any],
    ) -> EvaluationReport:
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
