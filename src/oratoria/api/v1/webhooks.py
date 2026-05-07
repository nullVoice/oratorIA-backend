"""External webhook receivers (Stripe, Culqi, Resend, etc)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/stripe")
async def stripe_webhook() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO: verify Stripe signature + dispatch")


@router.post("/culqi")
async def culqi_webhook() -> dict[str, str]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")
