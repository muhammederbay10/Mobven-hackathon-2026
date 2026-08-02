"""Append-only extraction corrections and AI-owned report regeneration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from copy import deepcopy

from pydantic import ValidationError
from sqlmodel import Session

from api.config import Settings, get_settings
from api.db import to_iso_date, utc_now
from api.errors import ApiError, invalid_state_transition
from api.models import AuditAction, AuditEntity, CheckReportRow, ExtractionCorrection
from api.schemas import (
    BRANCH_ACTOR,
    ApplicationAggregate,
    ApplicationStatus,
    ErrorCode,
    ExtractionCorrectionRequest,
    ExtractionResult,
)

_LOCKS: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
from api.services import (
    ai_client,
    application_service,
    audit_service,
    extraction_service,
    registry_service,
)


async def correct_extraction(
    session: Session,
    application_id: int,
    payload: ExtractionCorrectionRequest,
    *,
    correlation_id: str,
    settings: Settings | None = None,
    client: ai_client.AIServiceClient | None = None,
) -> ApplicationAggregate:
    async with _LOCKS[application_id]:
        return await _correct_extraction_locked(
            session,
            application_id,
            payload,
            correlation_id=correlation_id,
            settings=settings,
            client=client,
        )


async def _correct_extraction_locked(
    session: Session,
    application_id: int,
    payload: ExtractionCorrectionRequest,
    *,
    correlation_id: str,
    settings: Settings | None = None,
    client: ai_client.AIServiceClient | None = None,
) -> ApplicationAggregate:
    settings = settings or get_settings()
    application = application_service.get_application(session, application_id)
    if application.status is not ApplicationStatus.ANALYZED:
        raise invalid_state_transition(application.status.value, "CORRECT_EXTRACTION")

    extraction = extraction_service.latest_for_application(session, application_id)
    if extraction is None:
        raise ApiError(
            ErrorCode.DOCUMENT_REQUIRED,
            "Düzeltilecek analiz sonucu bulunamadı.",
            status_code=409,
        )
    effective = extraction_service.effective_payload(session, extraction)
    candidate = deepcopy(effective)
    changes: list[tuple[str, object, object]] = []
    for item in payload.corrections:
        try:
            old = extraction_service.get_value(candidate, item.field_path)
        except KeyError as exc:
            raise ApiError(
                ErrorCode.CORRECTION_PATH_NOT_ALLOWED,
                "Düzeltme alanı mevcut analiz sonucunda bulunamadı.",
                status_code=422,
                details={"field_path": item.field_path},
            ) from exc
        if old != item.expected_old_value:
            raise ApiError(
                ErrorCode.STALE_CORRECTION,
                "Analiz alanı başka bir işlem tarafından değiştirilmiş.",
                status_code=409,
                retryable=True,
                details={"field_path": item.field_path, "current_value": old},
            )
        extraction_service.apply_value(candidate, item.field_path, item.new_value)
        changes.append((item.field_path, old, item.new_value))
    try:
        reviewed = ExtractionResult.model_validate(candidate)
    except ValidationError as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Düzeltme yeni API sözleşmesine uygun değil.",
            status_code=422,
            details={"fields": [".".join(str(v) for v in e["loc"]) for e in exc.errors()]},
        ) from exc

    service = client or ai_client.get_ai_service(settings)
    registry = registry_service.load(settings)
    request = ai_client.build_analyze_request(
        extraction=reviewed,
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

    application_service.transition(
        session,
        application,
        ApplicationStatus.ANALYZING,
        correlation_id=correlation_id,
    )
    for field_path, old, new in changes:
        row = ExtractionCorrection(
            extraction_id=extraction.id,
            field_path=field_path,
            old_value_json={"value": old},
            new_value_json={"value": new},
            reviewer=BRANCH_ACTOR,
            reason=payload.reason.strip(),
        )
        session.add(row)
        session.flush()
        audit_service.record_branch_action(
            session,
            action=AuditAction.EXTRACTION_CORRECTED,
            entity_type=AuditEntity.EXTRACTION,
            entity_id=extraction.id,
            correlation_id=correlation_id,
            detail={
                "correction_id": row.id,
                "field_path": field_path,
                "old_value": old,
                "new_value": new,
                "reason": payload.reason.strip(),
            },
        )
    report_row = CheckReportRow(
        application_id=application_id,
        extraction_id=extraction.id,
        schema_version=reviewed.schema_version,
        verdict=report.verdict,
        payload=report.model_dump(mode="json", by_alias=True),
    )
    session.add(report_row)
    application_service.transition(
        session,
        application,
        ApplicationStatus.ANALYZED,
        correlation_id=correlation_id,
    )
    session.commit()
    return application_service.aggregate(session, application_id)
