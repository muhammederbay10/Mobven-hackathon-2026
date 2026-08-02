"""Append-only audit trail — plan sections 7.1, 14 and 15.

Two rules shape this module:

* **The client never chooses the actor.** Branch actions are always recorded as
  the fixed ``branch_user:kozyatagi01``; mobile actions carry the selected
  fixed-cast authority-person ID (section 14).
* **A failed audit write rolls back the action it describes** (section 15). The
  service therefore never opens its own session or swallows an exception — it
  writes into the caller's session so both land, or neither does.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlmodel import Session

from api.models import AuditAction, AuditEntity, AuditLog
from api.schemas import BRANCH_ACTOR

# Belt and braces for section 14: even though masked values are enforced at the
# schema edge, anything that reaches an audit row is re-checked here. An audit
# trail is the last place a raw identifier should be able to hide.
_UNMASKED_TCKN = re.compile(r"(?<!\d)\d{11}(?!\d)")
_MAX_DETAIL_STRING = 500


def new_correlation_id() -> str:
    """One ID per request, threaded through logs, errors and audit rows (§15)."""
    return uuid.uuid4().hex[:16]


def redact(value: Any) -> Any:
    """Strip anything that must never reach an audit row or a log line.

    Masks plausible unmasked TCKNs and truncates long strings so document text
    and model output cannot leak into the trail (section 14).
    """
    if isinstance(value, str):
        cleaned = _UNMASKED_TCKN.sub("[REDACTED_TCKN]", value)
        if len(cleaned) > _MAX_DETAIL_STRING:
            cleaned = cleaned[:_MAX_DETAIL_STRING] + "…[truncated]"
        return cleaned
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return f"<{len(value)} bytes omitted>"
    return value


def record(
    session: Session,
    *,
    actor: str,
    action: AuditAction,
    entity_type: AuditEntity,
    entity_id: str | int | None = None,
    correlation_id: str,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit row to the caller's transaction.

    Deliberately does not commit: the caller's `session_scope` decides whether
    the business action and its audit row both survive.
    """
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        correlation_id=correlation_id,
        detail=redact(detail or {}),
    )
    session.add(entry)
    return entry


def record_branch_action(
    session: Session,
    *,
    action: AuditAction,
    entity_type: AuditEntity,
    entity_id: str | int | None = None,
    correlation_id: str,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an action taken at the branch by the fixed demo actor (GAP-08)."""
    return record(
        session,
        actor=BRANCH_ACTOR,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        detail=detail,
    )
