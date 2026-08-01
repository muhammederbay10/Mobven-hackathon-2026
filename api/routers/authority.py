"""Authority current-state and version-history endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.db import get_session
from api.schemas import AuthorityRecordView
from api.services import authority_service

router = APIRouter(prefix="/api/authority", tags=["authority"])


@router.get("/{mersis}", response_model=AuthorityRecordView)
def get_authority(
    mersis: str, session: Annotated[Session, Depends(get_session)]
) -> AuthorityRecordView:
    return AuthorityRecordView.model_validate(
        authority_service.view(authority_service.get_active(session, mersis))
    )


@router.get("/{mersis}/history")
def get_authority_history(
    mersis: str, session: Annotated[Session, Depends(get_session)]
) -> dict[str, list[AuthorityRecordView]]:
    return {
        "items": [AuthorityRecordView.model_validate(item) for item in authority_service.history(session, mersis)]
    }
