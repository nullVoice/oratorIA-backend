"""Celery Beat schedule."""

from __future__ import annotations

from celery.schedules import crontab

BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "recompute-progress-daily": {
        "task": "oratoria.workers.tasks.progress_calculation.recompute_all_progress",
        "schedule": crontab(hour="3", minute="0"),
    },
}
