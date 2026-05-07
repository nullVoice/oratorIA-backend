"""Billing endpoints (checkout, portal)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/checkout")
async def create_checkout_session() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: integrate Stripe Checkout")


@router.post("/portal")
async def create_portal_session() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: integrate Stripe Portal")
