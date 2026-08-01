"""SQLModel tables — plan section 7.1.

Conventions held to throughout:

* Explicit enums, stored by *value* so the database reads the same as the JSON.
* UTC timestamps everywhere (see ``api/db.py``).
* Money is ``INTEGER`` minor units (kuruş). Float money columns are forbidden
  (GAP-12) — there is deliberately not a single ``float`` in this module.
* Raw AI payloads are stored verbatim in JSON columns and never mutated.
  Corrections are append-only rows applied on read to build the *effective*
  extraction (section 7.1).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel, UniqueConstraint

from api.db import utc_now
from api.schemas import (
    ApplicationStatus,
    AuthorityRecordStatus,
    OnboardingVerdict,
    TransactionStatus,
    TransactionSubject,
    TransactionVerdict,
)


def enum_column(enum_cls: type[Enum], **kwargs: Any) -> Column:
    """A VARCHAR column storing the enum's *value*, not its Python name.

    `native_enum=False` keeps SQLite portable; `values_callable` is what makes
    the stored text identical to the JSON contract.
    """
    return Column(
        SAEnum(
            enum_cls,
            values_callable=lambda cls: [member.value for member in cls],
            native_enum=False,
        ),
        **kwargs,
    )


def utc_column(**kwargs: Any) -> Column:
    return Column(DateTime(timezone=True), **kwargs)


# ---------------------------------------------------------------------------
# Audit vocabulary — plan section 14
# ---------------------------------------------------------------------------


class AuditAction(str, Enum):
    """Every material action section 14 requires to be auditable."""

    APPLICATION_CREATED = "APPLICATION_CREATED"
    IDENTITY_ATTESTED = "IDENTITY_ATTESTED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    ORIGINAL_ATTESTED = "ORIGINAL_ATTESTED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    EXTRACTION_CORRECTED = "EXTRACTION_CORRECTED"
    APPLICATION_DECIDED = "APPLICATION_DECIDED"
    APPROVAL_OVERRIDE = "APPROVAL_OVERRIDE"
    REGISTRY_REPRESENTATIVE_UPDATED = "REGISTRY_REPRESENTATIVE_UPDATED"
    AUTHORITY_CREATED = "AUTHORITY_CREATED"
    AUTHORITY_SUSPENDED = "AUTHORITY_SUSPENDED"
    TRANSACTION_AUTHORIZED = "TRANSACTION_AUTHORIZED"
    TRANSACTION_COSIGNED = "TRANSACTION_COSIGNED"
    DEMO_CASE_LOADED = "DEMO_CASE_LOADED"
    DEMO_RESET = "DEMO_RESET"


class AuditEntity(str, Enum):
    APPLICATION = "APPLICATION"
    DOCUMENT = "DOCUMENT"
    EXTRACTION = "EXTRACTION"
    CHECK_REPORT = "CHECK_REPORT"
    AUTHORITY_RECORD = "AUTHORITY_RECORD"
    TRANSACTION = "TRANSACTION"
    REGISTRY = "REGISTRY"
    DEMO = "DEMO"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class Application(SQLModel, table=True):
    __tablename__ = "application"

    id: int | None = Field(default=None, primary_key=True)

    company_name: str
    tax_number: str
    mersis: str = Field(index=True)
    applicant_name: str
    applicant_tckn_masked: str
    branch_code: str

    identity_verified_at_branch: bool = False
    status: ApplicationStatus = Field(
        default=ApplicationStatus.DRAFT,
        sa_column=enum_column(ApplicationStatus, index=True, nullable=False),
    )

    # Optimistic concurrency for the analyze/correct/decide sequence.
    version: int = Field(default=1)

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class Document(SQLModel, table=True):
    """An uploaded signature circular.

    Uniqueness is ``(application_id, sha256)`` rather than a global unique
    ``sha256``. Plan section 7.1 asks for "unique sha256", but section 11 has
    case 4 reuse "the same clean document as case 1" and Phase 4 requires case
    loading to be "deterministic in any order" — a global constraint makes those
    two requirements contradictory, since loading cases 1 and 4 in one run would
    insert the same bytes twice. Per-application uniqueness keeps the intent
    (one document row per application per file) while letting each application
    own its own ``original_seen`` attestation, which is an auditable per-branch
    event and must not be shared across applications. Cross-document work-sharing
    still happens where the plan actually placed it: the extraction cache keyed
    by ``(document_sha256, schema_version, engine)``, which is unaffected.
    """

    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("application_id", "sha256", name="uq_document_app_sha"),)

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    # Server-generated. The client filename is never trusted as a path (§14).
    stored_filename: str
    original_filename: str
    # Workspace-relative, never an absolute or client-supplied path (§7.1).
    stored_path: str
    mime_type: str
    size_bytes: int
    sha256: str = Field(index=True)
    page_count: int

    original_seen: bool = False
    scanned_by: str

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class Extraction(SQLModel, table=True):
    """The raw AI ``ExtractionResult``, stored verbatim and never mutated."""

    __tablename__ = "extraction"
    __table_args__ = (
        UniqueConstraint("document_id", "schema_version", "engine", name="uq_extraction_doc"),
    )

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", index=True)

    schema_version: str
    engine: str
    document_sha256: str = Field(index=True)
    # Verbatim AI payload. Corrections live in their own table (§7.1).
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class ExtractionCorrection(SQLModel, table=True):
    """Append-only human corrections (GAP-06). Never updated, never deleted."""

    __tablename__ = "extraction_correction"

    id: int | None = Field(default=None, primary_key=True)
    extraction_id: int = Field(foreign_key="extraction.id", index=True)

    field_path: str
    old_value_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    new_value_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    reviewer: str
    reason: str

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class CheckReportRow(SQLModel, table=True):
    """The AI ``CheckReport``, stored verbatim.

    The bank API never recomputes a check or a verdict (GAP-02, section 6);
    ``verdict`` is denormalized here only so approval guards and history queries
    do not have to parse the payload.
    """

    __tablename__ = "check_report"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    extraction_id: int = Field(foreign_key="extraction.id", index=True)

    schema_version: str
    verdict: OnboardingVerdict = Field(sa_column=enum_column(OnboardingVerdict, nullable=False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class AuthorityRecord(SQLModel, table=True):
    """A document-derived authority record (section 7.1, section 9.1).

    At most one ACTIVE record may exist per MERSİS. Creating a new approved
    version suspends the old one in the same transaction. Registry mutation does
    **not** write through to ``status`` (GAP-13) — current registry state is
    joined at read and authorization time instead.

    ``persons`` and ``rules`` are JSON snapshots because section 7.1 enumerates
    the tables and does not include a person table, and because a record must be
    created or superseded atomically as one row.
    """

    __tablename__ = "authority_record"

    id: int | None = Field(default=None, primary_key=True)
    mersis: str = Field(index=True)
    version: int = Field(default=1)
    status: AuthorityRecordStatus = Field(
        default=AuthorityRecordStatus.ACTIVE,
        sa_column=enum_column(AuthorityRecordStatus, index=True, nullable=False),
    )

    source_application_id: int = Field(foreign_key="application.id", index=True)
    source_document_id: int = Field(foreign_key="document.id")

    verified_at: datetime = Field(sa_column=utc_column(nullable=False))
    verified_by: str
    valid_until: str | None = Field(default=None)

    persons: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    rules: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    superseded_by_id: int | None = Field(default=None, foreign_key="authority_record.id")

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class Transaction(SQLModel, table=True):
    """A mobile authorization attempt. Every attempt is persisted (§8.5)."""

    __tablename__ = "transaction"

    id: int | None = Field(default=None, primary_key=True)

    mersis: str = Field(index=True)
    subject: TransactionSubject = Field(sa_column=enum_column(TransactionSubject, nullable=False))
    currency: str = Field(default="TRY")
    # GAP-12: integer minor units (kuruş). Never a float.
    amount_minor: int
    initiator: str

    status: TransactionStatus = Field(
        default=TransactionStatus.REQUESTED,
        sa_column=enum_column(TransactionStatus, index=True, nullable=False),
    )
    verdict: TransactionVerdict | None = Field(
        default=None, sa_column=enum_column(TransactionVerdict, nullable=True)
    )
    required_cosigner: str | None = Field(default=None)
    cosigner: str | None = Field(default=None)
    # Issued only for ALLOWED transactions, exactly once (§7.1, §9.3).
    authorization_code: str | None = Field(default=None, unique=True)

    authority_id: int | None = Field(default=None, foreign_key="authority_record.id")
    # Measured with a monotonic timer around the full service call, never hardcoded.
    latency_ms: int = Field(default=0)
    decision: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))


class AuditLog(SQLModel, table=True):
    """Append-only. Never updated or deleted during normal operation (§7.1)."""

    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)

    # Always server-assigned. A client can never supply an audit actor (§14).
    actor: str
    action: AuditAction = Field(sa_column=enum_column(AuditAction, index=True, nullable=False))
    entity_type: AuditEntity = Field(sa_column=enum_column(AuditEntity, nullable=False))
    entity_id: str | None = Field(default=None, index=True)
    correlation_id: str = Field(index=True)
    # Structured, redacted detail. Never document bytes or unmasked personal data.
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_column(nullable=False))
