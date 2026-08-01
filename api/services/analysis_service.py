"""Application analysis orchestration for Phase 1.

The service owns state, persistence, retry behaviour and transport selection.
It never derives an onboarding check or verdict; both come from the configured
AI client (live, fixture stub, or replay).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from sqlmodel import Session, select

from api.config import Settings, get_settings, resolve_under
from api.db import to_iso_date, utc_now
from api.errors import ApiError, not_found
from api.models import (
    Application,
    AuditAction,
    AuditEntity,
    CheckReportRow,
    Document,
    Extraction,
)
from api.schemas import ApplicationAggregate, ApplicationStatus, ErrorCode
from api.services import ai_client, application_service, audit_service, registry_service

_LOCKS: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


async def analyze_application(
    session: Session,
    application_id: int,
    *,
    correlation_id: str,
    settings: Settings | None = None,
    client: ai_client.AIServiceClient | None = None,
) -> ApplicationAggregate:
    """Analyze once, persist atomically, and return the restored aggregate."""
    settings = settings or get_settings()
    async with _LOCKS[application_id]:
        application = application_service.get_application(session, application_id)
        document = session.exec(
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.id.desc())
        ).first()
        if document is None:
            raise ApiError(
                ErrorCode.DOCUMENT_REQUIRED,
                "Analiz için önce bir belge yüklenmelidir.",
                status_code=409,
            )
        if application.status is ApplicationStatus.ANALYZED:
            return application_service.aggregate(session, application_id)
        if application.status is ApplicationStatus.ANALYZING:
            raise ApiError(
                ErrorCode.ANALYSIS_IN_PROGRESS,
                "Bu başvurunun analizi halen devam ediyor.",
                status_code=409,
                retryable=True,
            )
        if application.status not in {
            ApplicationStatus.DOCUMENT_SCANNED,
            ApplicationStatus.ANALYSIS_FAILED,
        }:
            application_service.transition(
                session,
                application,
                ApplicationStatus.ANALYZING,
                correlation_id=correlation_id,
            )

        application_service.transition(
            session,
            application,
            ApplicationStatus.ANALYZING,
            correlation_id=correlation_id,
        )
        audit_service.record_branch_action(
            session,
            action=AuditAction.ANALYSIS_STARTED,
            entity_type=AuditEntity.APPLICATION,
            entity_id=application_id,
            correlation_id=correlation_id,
            detail={"document_id": document.id, "mode": settings.ai_mode.value},
        )
        # Commit the in-progress marker before the external call so concurrent
        # requests and a crashed worker cannot produce a second analysis.
        session.commit()

        service = client or ai_client.get_ai_service(settings)
        engine = str(getattr(service, "engine", settings.ai_mode.value))
        try:
            original = resolve_under(settings.data_path, document.stored_path)
            file_bytes = original.read_bytes()
            cache = ai_client.ExtractionCache(settings)
            extraction_result = cache.get(document.sha256, engine)
            if extraction_result is None:
                extraction_result = await service.extract(
                    file_bytes=file_bytes,
                    filename=document.original_filename,
                    document_id=document.id or 0,
                )
                engine = str(getattr(service, "engine", engine))
                cache.put(
                    extraction_result,
                    document_sha256=document.sha256,
                    engine=engine,
                )

            registry = registry_service.load(settings)
            request = ai_client.build_analyze_request(
                extraction=extraction_result,
                company_name=application.company_name,
                tax_number=application.tax_number,
                mersis=application.mersis,
                applicant_name=application.applicant_name,
                applicant_tckn_masked=application.applicant_tckn_masked,
                branch_code=application.branch_code,
                identity_verified_at_branch=application.identity_verified_at_branch,
                registry=registry,
                as_of=to_iso_date(utc_now()),
            )
            report = await service.analyze(request)

            extraction = Extraction(
                document_id=document.id,
                schema_version=extraction_result.schema_version,
                engine=engine,
                document_sha256=document.sha256,
                payload=extraction_result.model_dump(mode="json", by_alias=True),
            )
            session.add(extraction)
            session.flush()
            report_row = CheckReportRow(
                application_id=application_id,
                extraction_id=extraction.id,
                schema_version=extraction_result.schema_version,
                verdict=report.verdict,
                payload=report.model_dump(mode="json", by_alias=True),
            )
            session.add(report_row)
            session.flush()
            application = application_service.get_application(session, application_id)
            application_service.transition(
                session,
                application,
                ApplicationStatus.ANALYZED,
                correlation_id=correlation_id,
            )
            audit_service.record_branch_action(
                session,
                action=AuditAction.ANALYSIS_COMPLETED,
                entity_type=AuditEntity.CHECK_REPORT,
                entity_id=report_row.id,
                correlation_id=correlation_id,
                detail={
                    "application_id": application_id,
                    "extraction_id": extraction.id,
                    "verdict": report.verdict.value,
                    "engine": engine,
                },
            )
            session.commit()
        except Exception as exc:
            _mark_failed(session, application_id, correlation_id, exc)
            raise

        return application_service.aggregate(session, application_id)


def _mark_failed(
    session: Session, application_id: int, correlation_id: str, exc: Exception
) -> None:
    session.rollback()
    application = session.get(Application, application_id)
    if application is None:
        raise not_found("Başvuru", application_id)
    if application.status is ApplicationStatus.ANALYZING:
        application_service.transition(
            session,
            application,
            ApplicationStatus.ANALYSIS_FAILED,
            correlation_id=correlation_id,
        )
    audit_service.record_branch_action(
        session,
        action=AuditAction.ANALYSIS_FAILED,
        entity_type=AuditEntity.APPLICATION,
        entity_id=application_id,
        correlation_id=correlation_id,
        detail={
            "error_code": exc.code.value if isinstance(exc, ApiError) else "INTERNAL_ERROR"
        },
    )
    session.commit()
