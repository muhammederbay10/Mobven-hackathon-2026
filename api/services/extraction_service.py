"""Immutable raw extraction plus ordered append-only correction projection."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from sqlmodel import Session, select

from api.models import Extraction, ExtractionCorrection
from api.schemas import ExtractionResult
from api.services.normalization_service import normalize_name

_REP_PATH = re.compile(r"^representatives\[([a-z][a-z0-9_-]{0,63})\]\.(name|mode)$")


def latest_for_application(session: Session, application_id: int) -> Extraction | None:
    from api.models import Document

    document = session.exec(
        select(Document).where(Document.application_id == application_id).order_by(Document.id.desc())
    ).first()
    if document is None:
        return None
    return session.exec(
        select(Extraction).where(Extraction.document_id == document.id).order_by(Extraction.id.desc())
    ).first()


def effective_payload(session: Session, extraction: Extraction) -> dict[str, Any]:
    payload = deepcopy(extraction.payload)
    rows = session.exec(
        select(ExtractionCorrection)
        .where(ExtractionCorrection.extraction_id == extraction.id)
        .order_by(ExtractionCorrection.id)
    ).all()
    for row in rows:
        apply_value(payload, row.field_path, row.new_value_json.get("value"))
    return ExtractionResult.model_validate(payload).model_dump(mode="json", by_alias=True)


def corrected_field_paths(session: Session, extraction_id: int) -> set[str]:
    """Fields with at least one append-only human correction."""

    rows = session.exec(
        select(ExtractionCorrection.field_path).where(
            ExtractionCorrection.extraction_id == extraction_id
        )
    ).all()
    return set(rows)


def get_value(payload: dict[str, Any], field_path: str) -> Any:
    company_paths = {
        "company.name": ("company", "name"),
        "company.taxNumber": ("company", "taxNumber"),
        "company.mersisNumber": ("company", "mersisNumber"),
        "validUntil": ("validUntil",),
    }
    if field_path in company_paths:
        current: Any = payload
        for key in company_paths[field_path]:
            current = current[key]
        return current
    match = _REP_PATH.fullmatch(field_path)
    if match:
        source_id, field = match.groups()
        representative = next(
            (item for item in payload["representatives"] if item["id"] == source_id), None
        )
        if representative is None:
            raise KeyError(source_id)
        return representative[field]
    raise KeyError(field_path)


def apply_value(payload: dict[str, Any], field_path: str, value: Any) -> None:
    if field_path == "company.name":
        payload["company"]["name"] = value
        payload["company"]["legalNameNormalized"] = normalize_name(str(value))
        return
    if field_path == "company.taxNumber":
        payload["company"]["taxNumber"] = value
        return
    if field_path == "company.mersisNumber":
        payload["company"]["mersisNumber"] = value
        return
    if field_path == "validUntil":
        payload["validUntil"] = value
        return
    match = _REP_PATH.fullmatch(field_path)
    if match:
        source_id, field = match.groups()
        representative = next(
            (item for item in payload["representatives"] if item["id"] == source_id), None
        )
        if representative is None:
            raise KeyError(source_id)
        representative[field] = value
        if field == "name":
            representative["nameNormalized"] = normalize_name(str(value))
        return
    raise KeyError(field_path)
