"""Read-only append-only audit trail endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from api.db import get_session, to_iso_instant
from api.models import AuditLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def get_audit(
    session: Annotated[Session, Depends(get_session)],
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
) -> dict[str, object]:
    statement = select(AuditLog)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditLog.entity_id == entity_id)
    rows = session.exec(statement.order_by(AuditLog.id.desc()).limit(200)).all()
    return {
        "items": [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action.value,
                "entity_type": row.entity_type.value,
                "entity_id": row.entity_id,
                "correlation_id": row.correlation_id,
                "detail": row.detail,
                "created_at": to_iso_instant(row.created_at),
            }
            for row in rows
        ]
    }
