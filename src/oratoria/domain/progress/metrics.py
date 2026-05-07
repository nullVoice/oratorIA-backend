"""Progress metric aggregations."""

from __future__ import annotations


def average_score(scores: list[int]) -> float:
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
