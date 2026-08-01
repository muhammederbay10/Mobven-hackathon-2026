"""Human decisions and reviewed authority-record construction."""

from __future__ import annotations

from threading import Lock

from sqlmodel import Session, select

from api.config import Settings, get_settings
from api.db import utc_now
from api.errors import ApiError
from api.models import (
    AuditAction,
    AuditEntity,
    AuthorityRecord,
    CheckReportRow,
    Document,
)
from api.schemas import (
    APPROVABLE_VERDICTS,
    BRANCH_ACTOR,
    VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION,
    ApplicationAggregate,
    ApplicationDecisionAction,
    ApplicationDecisionRequest,
    ApplicationStatus,
    AuthorityRecordStatus,
    ErrorCode,
    ExtractionResult,
    RegistryCompanyStatus,
    RegistryRepresentativeStatus,
)
from api.services import (
    application_service,
    audit_service,
    extraction_service,
    registry_service,
)
from api.services.normalization_service import normalize_name

_APPROVAL_LOCK = Lock()


def decide_application(
    session: Session,
    application_id: int,
    payload: ApplicationDecisionRequest,
    *,
    correlation_id: str,
    settings: Settings | None = None,
) -> ApplicationAggregate:
    settings = settings or get_settings()
    application = application_service.get_application(session, application_id)
    if payload.action is ApplicationDecisionAction.REQUEST_DOCUMENT:
        application_service.transition(
            session, application, ApplicationStatus.DOC_REQUESTED, correlation_id=correlation_id
        )
        _audit_decision(session, application_id, payload, correlation_id)
        session.commit()
        return application_service.aggregate(session, application_id)
    if payload.action is ApplicationDecisionAction.ESCALATE:
        application_service.transition(
            session, application, ApplicationStatus.ESCALATED, correlation_id=correlation_id
        )
        _audit_decision(session, application_id, payload, correlation_id)
        session.commit()
        return application_service.aggregate(session, application_id)

    with _APPROVAL_LOCK:
        application = application_service.get_application(session, application_id)
        existing = session.exec(
            select(AuthorityRecord)
            .where(AuthorityRecord.source_application_id == application_id)
            .order_by(AuthorityRecord.id.desc())
        ).first()
        if application.status is ApplicationStatus.APPROVED and existing is not None:
            return application_service.aggregate(session, application_id)
        if application.status is not ApplicationStatus.ANALYZED:
            application_service.transition(
                session, application, ApplicationStatus.APPROVED, correlation_id=correlation_id
            )

        extraction = extraction_service.latest_for_application(session, application_id)
        if extraction is None:
            raise _approval_error("Geçerli analiz sonucu bulunamadı.")
        reviewed = ExtractionResult.model_validate(
            extraction_service.effective_payload(session, extraction)
        )
        report = session.exec(
            select(CheckReportRow)
            .where(
                CheckReportRow.application_id == application_id,
                CheckReportRow.extraction_id == extraction.id,
            )
            .order_by(CheckReportRow.id.desc())
        ).first()
        if report is None or report.verdict not in APPROVABLE_VERDICTS:
            raise _approval_error("Bu analiz kararı onaya uygun değil.")
        if report.verdict in VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION:
            if not (payload.override_justification or "").strip():
                raise ApiError(
                    ErrorCode.OVERRIDE_JUSTIFICATION_REQUIRED,
                    "Çift imza sonucu için gerekçeli onay zorunludur.",
                    status_code=422,
                )
        if reviewed.fields_needing_review:
            raise _approval_error("İnceleme bekleyen alanlar çözülmeden onay verilemez.")
        if not application.identity_verified_at_branch:
            raise _approval_error("Şube kimlik teyidi eksik.")
        document = session.get(Document, extraction.document_id)
        if document is None or not document.original_seen:
            raise _approval_error("Belge aslı teyidi eksik.")

        company = registry_service.get_company(application.mersis, settings)
        if company is None or company.status is not RegistryCompanyStatus.ACTIVE:
            raise _approval_error("Şirket güncel sicilde aktif değil.")
        if (
            reviewed.company.mersis_number != application.mersis
            or reviewed.company.tax_number != application.tax_number
        ):
            raise _approval_error("İncelenen belge başvuru şirketine ait değil.")

        persons: list[dict[str, object]] = []
        source_to_registry: dict[str, str] = {}
        for representative in reviewed.representatives:
            matches = [
                item
                for item in company.representatives
                if (
                    representative.national_id is not None
                    and item.tckn == representative.national_id
                )
                or normalize_name(item.name) == normalize_name(representative.name)
            ]
            if len(matches) != 1 or matches[0].status is not RegistryRepresentativeStatus.ACTIVE:
                raise _approval_error(
                    f"{representative.name} güncel sicilde tekil ve aktif olarak doğrulanamadı."
                )
            registry_person = matches[0]
            source_to_registry[representative.id] = registry_person.id
            persons.append(
                {
                    "id": registry_person.id,
                    "source_id": representative.id,
                    "name": representative.name,
                    "name_normalized": representative.name_normalized,
                    "tckn_masked": registry_person.tckn,
                    "title": representative.title or "",
                    "mode": representative.mode.value,
                    "limits": representative.limits,
                    "registry_effective_at": registry_person.effective_at,
                }
            )
        if application.applicant_tckn_masked not in {p["tckn_masked"] for p in persons}:
            raise _approval_error("Başvuru sahibi aktif yetkili kişiler arasında değil.")

        all_authorities = session.exec(
            select(AuthorityRecord).where(AuthorityRecord.mersis == application.mersis)
        ).all()
        active = [row for row in all_authorities if row.status is AuthorityRecordStatus.ACTIVE]
        version = max((row.version for row in all_authorities), default=0) + 1
        for row in active:
            row.status = AuthorityRecordStatus.SUSPENDED
            session.add(row)

        authority = AuthorityRecord(
            mersis=application.mersis,
            version=version,
            status=AuthorityRecordStatus.ACTIVE,
            source_application_id=application_id,
            source_document_id=document.id,
            verified_at=utc_now(),
            verified_by=BRANCH_ACTOR,
            valid_until=reviewed.valid_until,
            persons=persons,
            rules=[rule.model_dump(mode="json", by_alias=True) for rule in reviewed.rules],
        )
        session.add(authority)
        session.flush()
        for row in active:
            row.superseded_by_id = authority.id
            audit_service.record_branch_action(
                session,
                action=AuditAction.AUTHORITY_SUSPENDED,
                entity_type=AuditEntity.AUTHORITY_RECORD,
                entity_id=row.id,
                correlation_id=correlation_id,
                detail={"superseded_by_id": authority.id},
            )

        application_service.transition(
            session, application, ApplicationStatus.APPROVED, correlation_id=correlation_id
        )
        _audit_decision(session, application_id, payload, correlation_id)
        if report.verdict in VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION:
            audit_service.record_branch_action(
                session,
                action=AuditAction.APPROVAL_OVERRIDE,
                entity_type=AuditEntity.APPLICATION,
                entity_id=application_id,
                correlation_id=correlation_id,
                detail={"justification": payload.override_justification},
            )
        audit_service.record_branch_action(
            session,
            action=AuditAction.AUTHORITY_CREATED,
            entity_type=AuditEntity.AUTHORITY_RECORD,
            entity_id=authority.id,
            correlation_id=correlation_id,
            detail={
                "application_id": application_id,
                "document_id": document.id,
                "mersis": application.mersis,
                "version": version,
            },
        )
        session.commit()
    return application_service.aggregate(session, application_id)


def _approval_error(message: str) -> ApiError:
    return ApiError(ErrorCode.APPROVAL_NOT_ALLOWED, message, status_code=409)


def _audit_decision(
    session: Session,
    application_id: int,
    payload: ApplicationDecisionRequest,
    correlation_id: str,
) -> None:
    audit_service.record_branch_action(
        session,
        action=AuditAction.APPLICATION_DECIDED,
        entity_type=AuditEntity.APPLICATION,
        entity_id=application_id,
        correlation_id=correlation_id,
        detail={"action": payload.action.value, "note": payload.note},
    )
