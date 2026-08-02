"""Application and document intake endpoints — task P1-02."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from sqlmodel import Session

from api.config import Settings, get_settings
from api.db import get_session
from api.schemas import (
    ApplicationAggregate,
    ApplicationDecisionRequest,
    ApplicationView,
    CreateApplicationRequest,
    DocumentView,
    ExtractionCorrectionRequest,
)
from api.services import analysis_service, application_service, document_service

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("", response_model=ApplicationView, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: CreateApplicationRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> ApplicationView:
    application = application_service.create_application(
        session,
        payload,
        correlation_id=request.state.correlation_id,
    )
    session.commit()
    session.refresh(application)
    return application_service.application_view(application)


@router.post(
    "/{application_id}/document",
    response_model=DocumentView,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    application_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    original_seen: Annotated[bool, Form()],
    scanned_by: Annotated[str, Form()],
) -> DocumentView:
    application = application_service.get_application(session, application_id)
    # Read one byte beyond the configured cap so a too-large upload is detected
    # without buffering an unbounded request body in memory.
    payload = await file.read(settings.max_upload_bytes + 1)
    document = document_service.store_document(
        session,
        application,
        file_bytes=payload,
        original_filename=file.filename,
        original_seen=original_seen,
        scanned_by=scanned_by,
        correlation_id=request.state.correlation_id,
        settings=settings,
    )
    session.commit()
    session.refresh(document)
    return application_service.document_view(document)


@router.get("/{application_id}", response_model=ApplicationAggregate)
def get_application(
    application_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> ApplicationAggregate:
    return application_service.aggregate(session, application_id)


@router.post("/{application_id}/analyze", response_model=ApplicationAggregate)
async def analyze_application(
    application_id: int,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApplicationAggregate:
    outcome = await analysis_service.analyze_application_with_metadata(
        session,
        application_id,
        correlation_id=request.state.correlation_id,
        settings=settings,
    )
    response.headers["X-Extraction-Cache"] = (
        "hit" if outcome.extraction_cache_hit else "miss"
    )
    return outcome.aggregate


@router.patch("/{application_id}/extraction", response_model=ApplicationAggregate)
async def correct_extraction(
    application_id: int,
    payload: ExtractionCorrectionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApplicationAggregate:
    from api.services import correction_service

    return await correction_service.correct_extraction(
        session,
        application_id,
        payload,
        correlation_id=request.state.correlation_id,
        settings=settings,
    )


@router.post("/{application_id}/decision", response_model=ApplicationAggregate)
def decide_application(
    application_id: int,
    payload: ApplicationDecisionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApplicationAggregate:
    from api.services import decision_service

    return decision_service.decide_application(
        session,
        application_id,
        payload,
        correlation_id=request.state.correlation_id,
        settings=settings,
    )
