"""Current and historical authority-record queries."""

from __future__ import annotations

from sqlmodel import Session, select

from api.db import to_iso_instant
from api.errors import ApiError
from api.models import AuthorityRecord
from api.schemas import AuthorityRecordStatus, ErrorCode
from api.services import registry_service


def get_active(session: Session, mersis: str) -> AuthorityRecord:
    authority = session.exec(
        select(AuthorityRecord)
        .where(
            AuthorityRecord.mersis == mersis,
            AuthorityRecord.status == AuthorityRecordStatus.ACTIVE,
        )
        .order_by(AuthorityRecord.version.desc())
    ).first()
    if authority is None:
        raise ApiError(
            ErrorCode.AUTHORITY_NOT_FOUND,
            "Aktif yetki kaydı bulunamadı.",
            status_code=404,
            details={"mersis": mersis},
        )
    return authority


def view(authority: AuthorityRecord) -> dict[str, object]:
    company = registry_service.get_company(authority.mersis)
    effective_dates = {
        representative.id: representative.effective_at
        for representative in (company.representatives if company else [])
    }
    persons = [
        {
            "id": person["id"],
            "source_id": person["source_id"],
            "name": person["name"],
            "tckn_masked": person["tckn_masked"],
            "title": person.get("title", ""),
            "degree": None,
            "valid_from": effective_dates.get(str(person.get("id"))),
            "valid_until": authority.valid_until,
        }
        for person in authority.persons
    ]
    return {
        "id": authority.id,
        "mersis": authority.mersis,
        "version": authority.version,
        "status": authority.status.value,
        "source_application_id": authority.source_application_id,
        "source_document_id": authority.source_document_id,
        "verified_at": to_iso_instant(authority.verified_at),
        "verified_by": authority.verified_by,
        "valid_until": authority.valid_until,
        "persons": persons,
        "rules": authority.rules,
    }


def history(session: Session, mersis: str) -> list[dict[str, object]]:
    rows = session.exec(
        select(AuthorityRecord)
        .where(AuthorityRecord.mersis == mersis)
        .order_by(AuthorityRecord.version.desc())
    ).all()
    return [view(row) for row in rows]
