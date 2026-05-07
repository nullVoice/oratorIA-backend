"""User profile routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/me")
async def get_me() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")


@router.patch("/me")
async def update_me() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")
