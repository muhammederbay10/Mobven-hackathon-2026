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

from sqlmodel import Session

from api.db import utc_now
from api.errors import invalid_state_transition
from api.models import Application, AuditAction, AuditEntity
from api.schemas import APPLICATION_TRANSITIONS, ApplicationStatus, CreateApplicationRequest
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
