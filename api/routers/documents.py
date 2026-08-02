"""Rendered document-page endpoint — task P1-02."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session

from api.config import Settings, get_settings
from api.db import get_session
from api.services import document_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{document_id}/page/{page_number}", response_class=FileResponse)
def get_document_page(
    document_id: int,
    page_number: int,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    page = document_service.page_path(session, document_id, page_number, settings)
    return FileResponse(page, media_type="image/png", filename=f"page-{page_number}.png")
