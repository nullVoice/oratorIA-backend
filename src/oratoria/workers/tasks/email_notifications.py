"""Outbound email tasks."""

from __future__ import annotations

from oratoria.workers.celery_app import celery_app


@celery_app.task(name="oratoria.workers.tasks.email_notifications.send_report_ready")
def send_report_ready(user_id: str, report_id: str) -> None:  # noqa: ARG001
    """TODO."""
    raise NotImplementedError
