"""Async report PDF generation."""

from __future__ import annotations

from oratoria.workers.celery_app import celery_app


@celery_app.task(name="oratoria.workers.tasks.report_generation.generate_pdf")
def generate_pdf(report_id: str) -> str:  # noqa: ARG001
    """TODO."""
    raise NotImplementedError
