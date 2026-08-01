"""Application lifecycle — plan sections 7.2 and 8.3.

Only this module transitions application state. Section 7.2: "Only the service
layer may transition state", and an invalid transition is
``409 INVALID_STATE_TRANSITION``.

**No case awareness.** Section 1.4 and section 18: this service must never
receive or inspect a case number, a fixture filename, a fictional name, a preset
amount or an expected verdict. Demo case loaders create ordinary domain records
and then call the functions below, exactly as a non-demo request would.
"""

from __future__ import annotations

from sqlmodel import Session, select

from api.db import to_iso_instant, utc_now
from api.errors import invalid_state_transition, not_found
from api.models import (
    Application,
    AuditAction,
    AuditEntity,
    AuthorityRecord,
    CheckReportRow,
    Document,
    Extraction,
    ExtractionCorrection,
)
from api.schemas import (
    APPLICATION_TRANSITIONS,
    ApplicationAggregate,
    ApplicationStatus,
    ApplicationView,
    CreateApplicationRequest,
    DocumentView,
)
from api.services import audit_service


def create_application(
    session: Session,
    request: CreateApplicationRequest,
    *,
    correlation_id: str,
) -> Application:
    """Create an application and record the branch identity attestation.

    Section 8.3: "identity attestation is required to reach IDENTITY_VERIFIED".
    An application created without it stays in DRAFT — the caller decides how to
    surface that, but it can never be skipped.
    """
    application = Application(
        company_name=request.company_name.strip(),
        tax_number=request.tax_number,
        mersis=request.mersis,
        applicant_name=request.applicant_name.strip(),
        applicant_tckn_masked=request.applicant_tckn_masked,
        branch_code=request.branch_code.strip(),
        identity_verified_at_branch=request.identity_verified_at_branch,
        status=ApplicationStatus.DRAFT,
    )
    session.add(application)
    session.flush()  # assign the primary key without ending the transaction

    audit_service.record_branch_action(
        session,
        action=AuditAction.APPLICATION_CREATED,
        entity_type=AuditEntity.APPLICATION,
        entity_id=application.id,
        correlation_id=correlation_id,
        detail={
            "company_name": application.company_name,
            "mersis": application.mersis,
            "tax_number": application.tax_number,
            "applicant_name": application.applicant_name,
            "applicant_tckn_masked": application.applicant_tckn_masked,
            "branch_code": application.branch_code,
        },
    )

    if request.identity_verified_at_branch:
        transition(
            session,
            application,
            ApplicationStatus.IDENTITY_VERIFIED,
            correlation_id=correlation_id,
        )
        audit_service.record_branch_action(
            session,
            action=AuditAction.IDENTITY_ATTESTED,
            entity_type=AuditEntity.APPLICATION,
            entity_id=application.id,
            correlation_id=correlation_id,
            detail={"applicant_tckn_masked": application.applicant_tckn_masked},
        )

    return application


def transition(
    session: Session,
    application: Application,
    target: ApplicationStatus,
    *,
    correlation_id: str,
) -> Application:
    """Move an application to `target`, or refuse with 409.

    The transition table in ``api/schemas.py`` is the single definition of what
    is legal; nothing here re-states it.
    """
    current = application.status
    if target not in APPLICATION_TRANSITIONS[current]:
        raise invalid_state_transition(current.value, target.value)

    application.status = target
    application.version += 1
    application.updated_at = utc_now()
    session.add(application)
    return application


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in APPLICATION_TRANSITIONS[current]


def get_application(session: Session, application_id: int) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise not_found("Başvuru", application_id)
    return application


def application_view(application: Application) -> ApplicationView:
    assert application.id is not None
    return ApplicationView(
        id=application.id,
        company_name=application.company_name,
        tax_number=application.tax_number,
        mersis=application.mersis,
        applicant_name=application.applicant_name,
        applicant_tckn_masked=application.applicant_tckn_masked,
        branch_code=application.branch_code,
        identity_verified_at_branch=application.identity_verified_at_branch,
        status=application.status,
        version=application.version,
        created_at=to_iso_instant(application.created_at),
        updated_at=to_iso_instant(application.updated_at),
    )


def document_view(document: Document) -> DocumentView:
    assert document.id is not None
    return DocumentView(
        id=document.id,
        application_id=document.application_id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        document_sha256=document.sha256,
        page_count=document.page_count,
        original_seen=document.original_seen,
        scanned_by=document.scanned_by,
        created_at=to_iso_instant(document.created_at),
    )


def aggregate(session: Session, application_id: int) -> ApplicationAggregate:
    """Return the complete server-backed branch state in one read."""
    application = get_application(session, application_id)
    document = session.exec(
        select(Document)
        .where(Document.application_id == application_id)
        .order_by(Document.id.desc())
    ).first()

    extraction = None
    extraction_payload = None
    report = None
    corrections: list[dict[str, object]] = []
    if document is not None:
        extraction = session.exec(
            select(Extraction)
            .where(Extraction.document_id == document.id)
            .order_by(Extraction.id.desc())
        ).first()
        if extraction is not None:
            report = session.exec(
                select(CheckReportRow)
                .where(
                    CheckReportRow.application_id == application_id,
                    CheckReportRow.extraction_id == extraction.id,
                )
                .order_by(CheckReportRow.id.desc())
            ).first()
            correction_rows = session.exec(
                select(ExtractionCorrection)
                .where(ExtractionCorrection.extraction_id == extraction.id)
                .order_by(ExtractionCorrection.id)
            ).all()
            corrections = [
                {
                    "id": row.id,
                    "field_path": row.field_path,
                    "old_value_json": row.old_value_json,
                    "new_value_json": row.new_value_json,
                    "reviewer": row.reviewer,
                    "reason": row.reason,
                    "created_at": to_iso_instant(row.created_at),
                }
                for row in correction_rows
            ]
            from api.services.extraction_service import effective_payload

            extraction_payload = effective_payload(session, extraction)

    authority = session.exec(
        select(AuthorityRecord)
        .where(AuthorityRecord.source_application_id == application_id)
        .order_by(AuthorityRecord.id.desc())
    ).first()

    authority_payload = None
    if authority is not None:
        from api.services.authority_service import view

        authority_payload = view(authority)

    return ApplicationAggregate(
        application=application_view(application),
        document=document_view(document) if document is not None else None,
        extraction=extraction_payload,
        report=report.payload if report is not None else None,
        corrections=corrections,
        authority=authority_payload,
    )
