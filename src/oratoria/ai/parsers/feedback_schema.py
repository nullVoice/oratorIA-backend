"""Structured-output schema for the evaluator agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Dimension = Literal["verbal", "paraverbal", "strategic"]


class Strength(BaseModel):
    title: str = Field(description="Short label for the strength.")
    dimension: Dimension = Field(description="Dimension this strength applies to.")
    evidence: str = Field(description="Concrete excerpt or moment that supports this strength.")
    impact: str = Field(description="Why this matters for the audience or goal.")


class Improvement(BaseModel):
    title: str = Field(description="Short label for the area to improve.")
    dimension: Dimension = Field(description="Dimension this improvement applies to.")
    evidence: str = Field(description="Concrete excerpt or moment that exposes the issue.")
    suggestion: str = Field(description="Actionable, specific recommendation.")
    priority: Literal["high", "medium", "low"] = Field(default="medium")


class ParaverbalMetrics(BaseModel):
    words_per_minute: float = Field(ge=0, description="Average words per minute.")
    filler_words_count: int = Field(ge=0, description="Total filler words detected.")
    pause_ratio: float = Field(
        ge=0, le=1, description="Silent time / total time (0–1)."
    )
    tone_variance: float = Field(
        ge=0, description="Pitch variance — proxy for vocal expressiveness."
    )
    notes: str | None = Field(
        default=None, description="Optional qualitative summary of paraverbal performance."
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
    recommended_next_steps: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Concrete next exercises or practice goals.",
    )
