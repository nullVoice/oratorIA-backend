"""Billing DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    plan: str
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    url: str
    session_id: str
