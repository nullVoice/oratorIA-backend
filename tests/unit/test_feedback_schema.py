"""Tests for feedback_schema dimension/priority normalization.

The evaluator prompt is Spanish, so the model sometimes emits the enum labels
in Spanish ("estratégica", "alta"). These must be coerced to the canonical
English literals rather than failing validation (which left avatar sessions
with no report — see the enum-parse bug).
"""

from __future__ import annotations

import pytest

from oratoria.ai.parsers.feedback_schema import Improvement, Strength


def _strength(dimension: str) -> Strength:
    return Strength(title="t", description="d", dimension=dimension, evidence="e", impact="i")


def _improvement(dimension: str, priority: str = "medium") -> Improvement:
    return Improvement(
        title="t",
        description="d",
        dimension=dimension,
        evidence="e",
        suggestion="s",
        priority=priority,
    )


class TestDimensionNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("verbal", "verbal"),
            ("paraverbal", "paraverbal"),
            ("strategic", "strategic"),
            ("estratégica", "strategic"),
            ("Estratégica", "strategic"),
            ("estrategico", "strategic"),
            ("estrategia", "strategic"),
            ("para-verbal", "paraverbal"),
            ("  Verbal  ", "verbal"),
        ],
    )
    def test_dimension_variants_coerce(self, raw: str, expected: str) -> None:
        assert _strength(raw).dimension == expected
        assert _improvement(raw).dimension == expected

    def test_unknown_dimension_still_rejected(self) -> None:
        with pytest.raises(ValueError):
            _strength("emocional")


class TestPriorityNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("high", "high"),
            ("alta", "high"),
            ("media", "medium"),
            ("baja", "low"),
            ("Baja", "low"),
        ],
    )
    def test_priority_variants_coerce(self, raw: str, expected: str) -> None:
        assert _improvement("verbal", raw).priority == expected
