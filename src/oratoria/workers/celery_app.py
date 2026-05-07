"""Celery application configured against Redis."""

from __future__ import annotations

from celery import Celery

from oratoria.config import settings
from oratoria.workers.beat_schedule import BEAT_SCHEDULE

celery_app = Celery(
    "oratoria",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "oratoria.workers.tasks.video_processing",
        "oratoria.workers.tasks.report_generation",
        "oratoria.workers.tasks.email_notifications",
        "oratoria.workers.tasks.progress_calculation",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule=BEAT_SCHEDULE,
)

celery_app.autodiscover_tasks(["oratoria.workers.tasks"])
