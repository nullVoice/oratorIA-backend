"""Session CRUD + audio upload + evaluate pipeline endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession as DBSession
from sqlalchemy.orm import selectinload

from oratoria.ai.agents.evaluator import EvaluatorAgent
from oratoria.core.security import current_active_user
from oratoria.dependencies import get_db
from oratoria.models import Report, Transcript
from oratoria.models import Session as SessionModel
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import User
from oratoria.schemas.report import ReportRead
from oratoria.schemas.session import SessionCreate, SessionRead
from oratoria.services.paraverbal.analyzer import ParaverbalAnalyzer
from oratoria.services.storage import get_storage
from oratoria.services.stt.whisper import WhisperSTT

logger = logging.getLogger(__name__)

router = APIRouter()

# Audio upload guards: cap memory use (the whole blob is read into RAM) and
# reject non-audio extensions so storage keys can't be abused.
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB
_ALLOWED_AUDIO_EXTENSIONS = {"mp3", "webm", "ogg", "wav", "m4a", "opus", "mp4"}


@router.post(
    "",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreate,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> SessionRead:
    sess = SessionModel(
        user_id=user.id,
        type=SessionType(payload.type),
        context=payload.context,
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return SessionRead(
        id=sess.id,
        user_id=sess.user_id,
        type=sess.type.value,
        status=sess.status.value,
        title=None,
        context=sess.context or {},
        started_at=sess.started_at,
        ended_at=sess.ended_at,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
    )


class SessionSummary(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    score: int | None
    summary: str | None
    context: dict[str, Any]
    created_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    page: int
    page_size: int


class SessionDetail(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    context: dict[str, Any]
    transcript: str | None
    report: dict[str, Any] | None
    created_at: datetime


@router.post("/{session_id}/audio", response_model=SessionRead)
async def upload_session_audio(
    session_id: uuid.UUID,
    audio: UploadFile,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> SessionRead:
    sess = await db.get(SessionModel, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")

    data = await audio.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio payload.")
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Audio exceeds the {_MAX_AUDIO_BYTES // (1024 * 1024)} MB limit.",
        )

    extension = (audio.filename or "").rsplit(".", 1)[-1].lower() or "mp3"
    if extension not in _ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported audio format '.{extension}'.",
        )
    content_type = audio.content_type or "audio/mpeg"
    key = f"audio/{session_id}.{extension}"

    storage = get_storage()
    url = await storage.upload(key, data, content_type)

    sess.audio_url = url
    sess.context = {**(sess.context or {}), "audio_storage_key": key}
    sess.status = SessionStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(sess)

    return SessionRead(
        id=sess.id,
        user_id=sess.user_id,
        type=sess.type.value,
        status=sess.status.value,
        title=None,
        context=sess.context or {},
        started_at=sess.started_at,
        ended_at=sess.ended_at,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
    )


@router.post("/{session_id}/evaluate", response_model=ReportRead)
async def evaluate_session(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> ReportRead:
    sess = await db.get(SessionModel, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if not sess.audio_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Session has no audio. Upload audio before evaluating.",
        )
    audio_key = (sess.context or {}).get("audio_storage_key")
    if not audio_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Audio storage key missing. Re-upload audio.",
        )

    sess.status = SessionStatus.PROCESSING
    await db.commit()

    try:
        storage = get_storage()
        audio_bytes = await storage.download(audio_key)

        stt = WhisperSTT()
        stt_result = await stt.transcribe(audio_bytes, language="es")

        analyzer = ParaverbalAnalyzer()
        duration_hint = max((s.end for s in stt_result.segments), default=0.0)
        metrics = await analyzer.analyze(
            audio_bytes, transcript=stt_result.text, duration_hint=duration_hint
        )

        agent = EvaluatorAgent()
        evaluation = await agent.evaluate(
            transcript=stt_result.text,
            context=sess.context or {},
            paraverbal_metrics=metrics,
        )

        # Replace any prior transcript/report from a previous evaluate attempt.
        await _delete_existing_transcript_and_report(db, sess.id)

        db.add(
            Transcript(
                session_id=sess.id,
                text=stt_result.text,
                language=stt_result.language,
                segments=[
                    {"start": s.start, "end": s.end, "text": s.text} for s in stt_result.segments
                ],
            )
        )

        report_row = Report(
            session_id=sess.id,
            score=evaluation.score,
            summary=evaluation.summary,
            strengths=[s.model_dump() for s in evaluation.strengths],
            improvements=[i.model_dump() for i in evaluation.improvements],
            paraverbal_metrics=evaluation.paraverbal_metrics.model_dump(),
            next_steps=evaluation.next_steps,
        )
        # Best-effort restructured pitch (never raises — enhancement only).
        report_row.structured_pitch = await try_generate_pitch(
            stt_result.text, sess.context or {}, evaluation.paraverbal_metrics
        )
        db.add(report_row)

        sess.status = SessionStatus.COMPLETED
        sess.ended_at = datetime.now(UTC)
        if stt_result.duration_seconds:
            sess.duration_seconds = int(round(stt_result.duration_seconds))

        await db.commit()
        await db.refresh(report_row)
        return ReportRead.model_validate(report_row)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Evaluate session %s failed", session_id)
        sess.status = SessionStatus.FAILED
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        # Full detail is already captured by logger.exception above; never leak
        # internal exception text (paths, DB errors, key fragments) to clients.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Evaluation pipeline failed. Please try again.",
        ) from exc


async def _delete_existing_transcript_and_report(db: DBSession, session_id: uuid.UUID) -> None:
    existing_t = (
        await db.execute(select(Transcript).where(Transcript.session_id == session_id))
    ).scalar_one_or_none()
    if existing_t:
        await db.delete(existing_t)
    existing_r = (
        await db.execute(select(Report).where(Report.session_id == session_id))
    ).scalar_one_or_none()
    if existing_r:
        await db.delete(existing_r)
    await db.flush()


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> SessionListResponse:
    base_where = SessionModel.user_id == user.id

    total = int(
        (
            await db.execute(select(func.count()).select_from(SessionModel).where(base_where))
        ).scalar_one()
    )

    offset = (page - 1) * page_size
    stmt = (
        select(SessionModel)
        .where(base_where)
        .order_by(desc(SessionModel.created_at))
        .options(selectinload(SessionModel.report))
        .offset(offset)
        .limit(page_size)
    )
    sessions = (await db.execute(stmt)).scalars().all()
    items = [
        SessionSummary(
            id=s.id,
            type=s.type.value,
            status=s.status.value,
            started_at=s.started_at,
            ended_at=s.ended_at,
            duration_seconds=s.duration_seconds,
            score=s.report.score if s.report else None,
            summary=s.report.summary if s.report else None,
            context=s.context or {},
            created_at=s.created_at,
        )
        for s in sessions
    ]
    return SessionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> SessionDetail:
    stmt = (
        select(SessionModel)
        .where(
            SessionModel.id == session_id,
            SessionModel.user_id == user.id,
        )
        .options(
            selectinload(SessionModel.report),
            selectinload(SessionModel.transcript),
        )
    )
    sess = (await db.execute(stmt)).scalar_one_or_none()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    return SessionDetail(
        id=sess.id,
        type=sess.type.value,
        status=sess.status.value,
        started_at=sess.started_at,
        ended_at=sess.ended_at,
        duration_seconds=sess.duration_seconds,
        context=sess.context or {},
        transcript=sess.transcript.text if sess.transcript else None,
        report=(
            {
                "score": sess.report.score,
                "summary": sess.report.summary,
                "strengths": sess.report.strengths,
                "improvements": sess.report.improvements,
                "paraverbal_metrics": sess.report.paraverbal_metrics,
                "next_steps": sess.report.next_steps,
                "structured_pitch": sess.report.structured_pitch,
            }
            if sess.report
            else None
        ),
        created_at=sess.created_at,
    )
