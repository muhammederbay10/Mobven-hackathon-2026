"""Simulated registry read and stable-ID mutation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from api.config import Settings, get_settings
from api.db import get_session
from api.errors import demo_mode_disabled, not_found
from api.models import AuditAction, AuditEntity
from api.schemas import Registry, RegistryCompany, RegistryRepresentativeUpdateRequest
from api.services import audit_service, registry_service

router = APIRouter(prefix="/api/registry", tags=["registry"])


@router.get("", response_model=Registry)
def get_registry(settings: Annotated[Settings, Depends(get_settings)]) -> Registry:
    return registry_service.load(settings)


@router.put("/{mersis}/reps/{rep_id}", response_model=RegistryCompany)
def update_representative(
    mersis: str,
    rep_id: str,
    payload: RegistryRepresentativeUpdateRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> RegistryCompany:
    if not settings.demo_mode:
        raise demo_mode_disabled()
    before = registry_service.get_company(mersis, settings)
    if before is None:
        raise not_found("Sicil şirketi", mersis)
    representative = next((item for item in before.representatives if item.id == rep_id), None)
    if representative is None:
        raise not_found("Sicil temsilcisi", rep_id)
    old_status = representative.status
    company = registry_service.set_representative_status(mersis, rep_id, payload.status, settings)
    audit_service.record_branch_action(
        session,
        action=AuditAction.REGISTRY_REPRESENTATIVE_UPDATED,
        entity_type=AuditEntity.REGISTRY,
        entity_id=rep_id,
        correlation_id=request.state.correlation_id,
        detail={"mersis": mersis, "old_status": old_status.value, "new_status": payload.status.value},
    )
    try:
        session.commit()
    except Exception:
        registry_service.set_representative_status(mersis, rep_id, old_status, settings)
        raise
    return company
