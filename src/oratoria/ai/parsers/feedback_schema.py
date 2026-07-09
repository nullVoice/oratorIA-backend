"""Structured-output schema for the evaluator agent."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _fold(value: str) -> str:
    """Lowercase and strip accents so 'Estratégica' == 'estrategica'."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().lower()


# The evaluator prompt is written in Spanish, so the model frequently emits the
# dimension/priority labels in Spanish ("estratégica", "alta") even though the
# schema expects the canonical English literals. Rather than depend on the model
# getting the enum exactly right (a non-deterministic parse failure that leaves
# the session with no report), we normalize known variants before validation.
_DIMENSION_MAP: dict[str, str] = {
    "verbal": "verbal",
    "paraverbal": "paraverbal",
    "para-verbal": "paraverbal",
    "para verbal": "paraverbal",
    "strategic": "strategic",
    "strategy": "strategic",
    "estrategica": "strategic",
    "estrategico": "strategic",
    "estrategia": "strategic",
}

_PRIORITY_MAP: dict[str, str] = {
    "high": "high",
    "alta": "high",
    "alto": "high",
    "medium": "medium",
    "media": "medium",
    "medio": "medium",
    "low": "low",
    "baja": "low",
    "bajo": "low",
}


def _normalize_dimension(value: object) -> object:
    if isinstance(value, str):
        return _DIMENSION_MAP.get(_fold(value), value)
    return value


def _normalize_priority(value: object) -> object:
    if isinstance(value, str):
        return _PRIORITY_MAP.get(_fold(value), value)
    return value


Dimension = Annotated[
    Literal["verbal", "paraverbal", "strategic"],
    BeforeValidator(_normalize_dimension),
]
Priority = Annotated[
    Literal["high", "medium", "low"],
    BeforeValidator(_normalize_priority),
]


class Strength(BaseModel):
    title: str = Field(description="Short label for the strength.")
    description: str = Field(description="One- or two-sentence explanation of the strength.")
    dimension: Dimension = Field(description="Dimension this strength applies to.")
    evidence: str = Field(description="Concrete excerpt or moment that supports this strength.")
    impact: str = Field(description="Why this matters for the audience or goal.")


class Improvement(BaseModel):
    title: str = Field(description="Short label for the area to improve.")
    description: str = Field(description="One- or two-sentence explanation of the issue.")
    dimension: Dimension = Field(description="Dimension this improvement applies to.")
    evidence: str = Field(description="Concrete excerpt or moment that exposes the issue.")
    suggestion: str = Field(description="Actionable, specific recommendation.")
    priority: Priority = Field(default="medium")


class ParaverbalMetrics(BaseModel):
    words_per_minute: float = Field(ge=0, description="Average words per minute.")
    filler_words_count: int = Field(ge=0, description="Total filler words detected.")
    pause_ratio: float = Field(ge=0, le=1, description="Silent time / total time (0–1).")
    tone_variance: float = Field(
        ge=0, description="Pitch variance — proxy for vocal expressiveness."
    )
    notes: str | None = Field(
        default=None, description="Optional qualitative summary of paraverbal performance."
    )


class PitchSection(BaseModel):
    """One narrative beat of the restructured pitch."""

    label: str = Field(
        description="Nombre del bloque narrativo (p. ej. 'Gancho', 'Problema', "
        "'Solución', 'Valor', 'Cierre')."
    )
    content: str = Field(
        description="El texto reescrito de ese bloque, en primera persona, listo "
        "para decirse en voz alta."
    )


class StructuredPitch(BaseModel):
    """A restructured, better-told version of what the user actually said.

    Keeps the user's own ideas and facts; improves narrative arc, clarity and
    flow. Produced by the PitchRewriterAgent after the evaluation.
    """

    headline: str = Field(description="La idea central destilada en una sola frase memorable.")
    sections: list[PitchSection] = Field(
        min_length=2,
        max_length=6,
        description="Los bloques narrativos ordenados (arco: gancho → desarrollo → cierre).",
    )
    delivery_note: str = Field(
        description="Una nota breve sobre CÓMO decirlo mejor, basada en cómo habló "
        "la persona (ritmo, muletillas, energía)."
    )


class EvaluationReport(BaseModel):
    """Full evaluation produced by the evaluator agent."""

    score: int = Field(ge=0, le=100, description="Overall score from 0 to 100.")
    summary: str = Field(description="One-paragraph summary of the performance.")
    strengths: list[Strength] = Field(
        min_length=1,
        max_length=3,
        description="Top 3 strengths with concrete evidence.",
    )
    improvements: list[Improvement] = Field(
        min_length=1,
        max_length=3,
        description="Top 3 improvement areas, each actionable.",
    )
    paraverbal_metrics: ParaverbalMetrics
    next_steps: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Concrete next exercises or practice goals.",
    )
