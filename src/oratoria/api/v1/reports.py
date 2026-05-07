"""Report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/{report_id}")
async def get_report(report_id: uuid.UUID) -> dict[str, str]:  # noqa: ARG001
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")


@router.get("/{report_id}/pdf")
async def download_report_pdf(report_id: uuid.UUID) -> dict[str, str]:  # noqa: ARG001
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "TODO")
