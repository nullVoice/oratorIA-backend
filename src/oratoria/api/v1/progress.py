"""Progress endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("")
async def list_progress() -> list[dict[str, str]]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")
