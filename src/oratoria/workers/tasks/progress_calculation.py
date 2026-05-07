"""Periodic progress aggregation."""

from __future__ import annotations

from oratoria.workers.celery_app import celery_app


@celery_app.task(name="oratoria.workers.tasks.progress_calculation.recompute_all_progress")
def recompute_all_progress() -> None:
    """TODO."""
    raise NotImplementedError
