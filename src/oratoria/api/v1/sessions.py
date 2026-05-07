"""Session endpoints — create, list, get, upload audio, finish, delete."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from oratoria.dependencies import DbSession
from oratoria.schemas.session import SessionCreate, SessionRead

router = APIRouter()


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, db: DbSession) -> SessionRead:  # noqa: ARG001
    """Create a new practice session."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement in domain.sessions.service")


@router.get("", response_model=list[SessionRead])
async def list_sessions(db: DbSession) -> list[SessionRead]:  # noqa: ARG001
    """List sessions for the current user."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement in domain.sessions.service")


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: uuid.UUID, db: DbSession) -> SessionRead:  # noqa: ARG001
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement in domain.sessions.service")


@router.post("/{session_id}/audio", status_code=status.HTTP_202_ACCEPTED)
async def upload_audio(
    session_id: uuid.UUID,
    db: DbSession,  # noqa: ARG001
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Upload an audio chunk for an async session — enqueues processing."""
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Audio file required.")
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: enqueue Celery task")


@router.post("/{session_id}/finish", response_model=SessionRead)
async def finish_session(session_id: uuid.UUID, db: DbSession) -> SessionRead:  # noqa: ARG001
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement in domain.sessions.service")


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, db: DbSession) -> None:  # noqa: ARG001
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement in domain.sessions.service")
