"""Session listing + detail endpoints.

The persistence side-effects of `POST /api/v1/practice/finalize` populate
the `sessions` / `transcripts` / `reports` tables; this module just reads
them back for the dashboard and the report deep-link.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession as DBSession
from sqlalchemy.orm import selectinload

from oratoria.core.security import current_active_user
from oratoria.dependencies import get_db
from oratoria.models import Session as SessionModel
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import User
from oratoria.schemas.session import SessionCreate, SessionRead
from oratoria.services.storage import get_storage

router = APIRouter()


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
    created_at: datetime


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
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Empty audio payload."
        )

    content_type = audio.content_type or "audio/mpeg"
    extension = (audio.filename or "").rsplit(".", 1)[-1].lower() or "mp3"
    key = f"audio/{session_id}.{extension}"

    storage = get_storage()
    url = await storage.upload(key, data, content_type)

    sess.audio_url = url
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


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    user: User = Depends(current_active_user),
    db: DBSession = Depends(get_db),
) -> list[SessionSummary]:
    stmt = (
        select(SessionModel)
        .where(SessionModel.user_id == user.id)
        .order_by(desc(SessionModel.created_at))
        .options(selectinload(SessionModel.report))
        .limit(100)
    )
    sessions = (await db.execute(stmt)).scalars().all()
    return [
        SessionSummary(
            id=s.id,
            type=s.type.value,
            status=s.status.value,
            started_at=s.started_at,
            ended_at=s.ended_at,
            duration_seconds=s.duration_seconds,
            score=s.report.score if s.report else None,
            summary=s.report.summary if s.report else None,
            created_at=s.created_at,
        )
        for s in sessions
    ]


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
            }
            if sess.report
            else None
        ),
        created_at=sess.created_at,
    )
