"""Evaluator agent: transcript + paraverbal metrics → structured EvaluationReport."""

from __future__ import annotations

import json
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser

from oratoria.ai.parsers.feedback_schema import EvaluationReport, ParaverbalMetrics
from oratoria.ai.prompts.evaluator_prompt_v1 import build_evaluator_prompt
from oratoria.config import settings


class EvaluatorAgent:
    """Wraps Claude + structured output parsing for speech evaluation."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured — cannot instantiate EvaluatorAgent."
            )
        self._parser = PydanticOutputParser(pydantic_object=EvaluationReport)
        self._prompt = build_evaluator_prompt().partial(
            format_instructions=self._parser.get_format_instructions()
        )
        self._llm = ChatAnthropic(
            model_name=model or settings.anthropic_model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=60,
            stop=None,
        )
        self._chain = self._prompt | self._llm | self._parser

    async def evaluate(
        self,
        transcript: str,
        paraverbal_metrics: ParaverbalMetrics | dict[str, Any],
        *,
        presentation_type: str = "presentación general",
        audience: str = "audiencia mixta",
        goal: str = "comunicar con claridad y persuadir",
        formality: str = "profesional",
        language: str = "es",
    ) -> EvaluationReport:
        metrics_payload = (
            paraverbal_metrics.model_dump_json(indent=2)
            if isinstance(paraverbal_metrics, ParaverbalMetrics)
            else json.dumps(paraverbal_metrics, ensure_ascii=False, indent=2)
        )
        return await self._chain.ainvoke(
            {
                "transcript": transcript,
                "paraverbal_metrics": metrics_payload,
                "presentation_type": presentation_type,
                "audience": audience,
                "goal": goal,
                "formality": formality,
                "language": language,
            }
        )
