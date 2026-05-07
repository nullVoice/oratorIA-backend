"""Authentication routes (login, refresh, logout, register)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/login")
async def login() -> dict[str, str]:
    """TODO: wire fastapi-users auth backend."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: implement with fastapi-users")


@router.post("/refresh")
async def refresh() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")


@router.post("/logout")
async def logout() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")


@router.post("/register")
async def register() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")
