"""Async video → audio extraction + transcription pipeline."""

from __future__ import annotations

from oratoria.workers.celery_app import celery_app


@celery_app.task(name="oratoria.workers.tasks.video_processing.process_video")
def process_video(session_id: str) -> str:  # noqa: ARG001
    """TODO: extract audio, run orchestrator, persist report."""
    raise NotImplementedError
