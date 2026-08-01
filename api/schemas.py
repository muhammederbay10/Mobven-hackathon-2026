"""Frozen shared contracts for the YetkiCheck bank API.

This module is the Python mirror of the contracts defined in
``docs/fbdocs/IMPLEMENTATION_PLAN.md`` section 5, together with the enum,
identifier, date and error formats frozen in Phase 0 shared architecture
step 3.  Its TypeScript twin is ``web/lib/types.ts`` / ``web/lib/contracts.ts``.

Ownership
---------
The AI engineer owns ``ai/schema.py``.  This file *mirrors* it; it never
replaces it and is never the place to negotiate a contract change.  Per
IMPLEMENTATION_PLAN.md section 5 and section 18.11, a contract change is
coordinated with the AI engineer, who updates the AI-owned file first.

Strictness policy
-----------------
Every model sets ``extra="forbid"``.  On AI-delivered payloads an unknown key
is drift, and section 8.8 requires drift to be *reported* as a contract defect
rather than silently absorbed.  Section 15 defines the runtime consequence:
"Invalid AI schema: store no partial extraction/report; return a retryable
integration error."

What this module deliberately does NOT do
-----------------------------------------
It does not recompute onboarding checks or re-derive ``verdict`` from
``checks``.  GAP-02 places the nine-check comparison engine in ``ai/compare.py``
and section 6 forbids a second copy in the bank API.  Report-level consistency
is asserted in ``api/tests/test_contract_freeze.py`` as a *defect detector*
against delivered fixtures, never as runtime business logic.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# ---------------------------------------------------------------------------
# 1. Frozen identifier, date and money formats
# ---------------------------------------------------------------------------
# Plan-mandated formats are marked [PLAN]; formats chosen here to close an
# otherwise open detail are marked [FROZEN-HERE] and may only be changed by a
# coordinated update to this file, web/lib/types.ts and docs/CONTRACT_FREEZE.md.

SCHEMA_VERSION: Literal["1.0"] = "1.0"

TAX_NUMBER_PATTERN = r"^\d{10}$"  # [PLAN] section 8.7: exactly 10 digits
MERSIS_PATTERN = r"^\d{16}$"  # [PLAN] section 8.7: exactly 16 digits
TCKN_MASKED_PATTERN = r"^\d{3}\*{6}\d{2}$"  # [PLAN] GAP-08: e.g. 123******01

# [PLAN] GAP-09 registry representatives are addressed by stable ID.
REGISTRY_REP_ID_PATTERN = r"^rep_[a-z0-9_]+$"
# [FROZEN-HERE] Extraction-local representative IDs. The agreed convention is
# rep-1, rep-2, ...; the pattern stays deliberately wider than the convention so
# a convention breach surfaces as a contract-test defect rather than a runtime
# crash mid-demo. The convention itself is asserted in the contract tests.
# The leading character must be a letter: section 8.7 requires a correction path
# to address a representative by its immutable source ID and "never an array
# position", so a bare integer must not be a syntactically valid source ID.
EXTRACTION_SOURCE_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"

# [FROZEN-HERE] Dates are ISO-8601. Calendar dates carry no time or zone;
# instants are always UTC with a literal Z. This is the "date format" seam
# called out in phase 3 backend step 2 and must be confirmed with the AI
# engineer at the H4 contract freeze.
ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
ISO_INSTANT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"

# [FROZEN-HERE] Authorization codes are bank-API owned (not an AI contract).
# Crockford-style alphabet: no I, L, O or U, so a projected code cannot be
# misread from the stage.
AUTHORIZATION_CODE_PATTERN = r"^YTK-[0-9A-HJ-KMNP-TV-Z]{8}$"

# [PLAN] GAP-08 / section 14: the branch audit actor is a constant. Clients
# can never supply an arbitrary audit actor.
BRANCH_ACTOR = "branch_user:kozyatagi01"

# [PLAN] GAP-12: money is integer minor units (kuruş); currency is fixed TRY.
CURRENCY: Literal["TRY"] = "TRY"
MAX_AMOUNT_MINOR = 2**53 - 1  # stays inside the JS safe-integer range

TaxNumberStr = Annotated[str, StringConstraints(pattern=TAX_NUMBER_PATTERN)]
MersisStr = Annotated[str, StringConstraints(pattern=MERSIS_PATTERN)]
TcknMaskedStr = Annotated[str, StringConstraints(pattern=TCKN_MASKED_PATTERN)]
RegistryRepIdStr = Annotated[str, StringConstraints(pattern=REGISTRY_REP_ID_PATTERN)]
SourceIdStr = Annotated[str, StringConstraints(pattern=EXTRACTION_SOURCE_ID_PATTERN)]
IsoDateStr = Annotated[str, StringConstraints(pattern=ISO_DATE_PATTERN)]
IsoInstantStr = Annotated[str, StringConstraints(pattern=ISO_INSTANT_PATTERN)]
AmountMinorInt = Annotated[int, Field(ge=0, le=MAX_AMOUNT_MINOR)]


class FrozenModel(BaseModel):
    """Base for every contract model: unknown keys are a reportable defect."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# ---------------------------------------------------------------------------
# 2. Frozen enums
# ---------------------------------------------------------------------------


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AuthorityMode(str, Enum):
    SOLE = "SOLE"
    JOINT = "JOINT"
    LIMITED = "LIMITED"
    UNKNOWN = "UNKNOWN"


class TransactionSubject(str, Enum):
    GENERAL = "GENERAL"
    CREDIT = "CREDIT"
    REAL_ESTATE = "REAL_ESTATE"


class CheckStatus(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class OnboardingVerdict(str, Enum):
    READY = "READY"
    CO_SIGNER_REQUIRED = "CO_SIGNER_REQUIRED"
    MISMATCH = "MISMATCH"
    REGISTRY_CONFLICT = "REGISTRY_CONFLICT"


class CheckSourceKind(str, Enum):
    APPLICATION = "APPLICATION"
    IDENTITY = "IDENTITY"
    DOCUMENT = "DOCUMENT"
    REGISTRY = "REGISTRY"


class TransactionVerdict(str, Enum):
    ALLOWED = "ALLOWED"
    PENDING_COSIGN = "PENDING_COSIGN"
    DENIED = "DENIED"


class ApplicationStatus(str, Enum):
    """[PLAN] section 7.1. Transitions are enforced in the service layer only."""

    DRAFT = "DRAFT"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    DOCUMENT_SCANNED = "DOCUMENT_SCANNED"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    APPROVED = "APPROVED"
    DOC_REQUESTED = "DOC_REQUESTED"
    ESCALATED = "ESCALATED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class TransactionStatus(str, Enum):
    """[PLAN] section 7.3. REQUESTED is the pre-decision state."""

    REQUESTED = "REQUESTED"
    ALLOWED = "ALLOWED"
    PENDING_COSIGN = "PENDING_COSIGN"
    DENIED = "DENIED"


class AuthorityRecordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class RegistryCompanyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RegistryRepresentativeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"


class ApplicationDecisionAction(str, Enum):
    APPROVE = "approve"
    REQUEST_DOCUMENT = "request_document"
    ESCALATE = "escalate"


# [PLAN] section 7.2 / 7.3. The service layer is the only place allowed to
# transition state; these tables are the single definition of what is legal.
APPLICATION_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: frozenset({ApplicationStatus.IDENTITY_VERIFIED}),
    ApplicationStatus.IDENTITY_VERIFIED: frozenset({ApplicationStatus.DOCUMENT_SCANNED}),
    ApplicationStatus.DOCUMENT_SCANNED: frozenset({ApplicationStatus.ANALYZING}),
    ApplicationStatus.ANALYZING: frozenset(
        {ApplicationStatus.ANALYZED, ApplicationStatus.ANALYSIS_FAILED}
    ),
    ApplicationStatus.ANALYSIS_FAILED: frozenset({ApplicationStatus.ANALYZING}),
    ApplicationStatus.ANALYZED: frozenset(
        {
            ApplicationStatus.APPROVED,
            ApplicationStatus.DOC_REQUESTED,
            ApplicationStatus.ESCALATED,
            ApplicationStatus.ANALYZING,
        }
    ),
    ApplicationStatus.APPROVED: frozenset(),
    ApplicationStatus.DOC_REQUESTED: frozenset(),
    ApplicationStatus.ESCALATED: frozenset(),
}

TRANSACTION_TRANSITIONS: dict[TransactionStatus, frozenset[TransactionStatus]] = {
    TransactionStatus.REQUESTED: frozenset(
        {
            TransactionStatus.ALLOWED,
            TransactionStatus.PENDING_COSIGN,
            TransactionStatus.DENIED,
        }
    ),
    TransactionStatus.PENDING_COSIGN: frozenset(
        {TransactionStatus.ALLOWED, TransactionStatus.DENIED}
    ),
    TransactionStatus.ALLOWED: frozenset(),
    TransactionStatus.DENIED: frozenset(),
}

# [PLAN] GAP-07. Which verdicts a human may approve, and how.
APPROVABLE_VERDICTS: frozenset[OnboardingVerdict] = frozenset(
    {OnboardingVerdict.READY, OnboardingVerdict.CO_SIGNER_REQUIRED}
)
VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION: frozenset[OnboardingVerdict] = frozenset(
    {OnboardingVerdict.CO_SIGNER_REQUIRED}
)


# ---------------------------------------------------------------------------
# 3. Common primitives — IMPLEMENTATION_PLAN.md section 5.1
# ---------------------------------------------------------------------------

T = TypeVar("T")


class EvidenceRef(FrozenModel):
    page: int = Field(ge=1, description="1-based page number")
    quote: str = Field(min_length=1, description="verbatim source text")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="normalized x1,y1,x2,y2"
    )


class Fact(FrozenModel, Generic[T]):
    """A document-derived value with its confidence and supporting evidence.

    Section 5.1: every non-null document-derived legal fact must carry at least
    one evidence item. Unknown content must be ``null`` plus a review flag; the
    model must not guess. The evidence rule is asserted against delivered
    fixtures in the contract tests rather than enforced here, so a thin-evidence
    payload is reported as a defect instead of crashing the demo mid-analysis.
    """

    value: T | None = None
    confidence: Confidence
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ReviewFlag(FrozenModel):
    code: str = Field(min_length=1)
    severity: ReviewSeverity
    field_path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence: list[EvidenceRef] | None = None


# ---------------------------------------------------------------------------
# 4. Extraction result — IMPLEMENTATION_PLAN.md section 5.2
# ---------------------------------------------------------------------------


class AuthorityRule(FrozenModel):
    id: str = Field(min_length=1)
    subject: TransactionSubject
    currency: Literal["TRY"] = CURRENCY
    min_amount_minor: AmountMinorInt | None = Field(
        default=None, description="inclusive integer kuruş"
    )
    max_amount_minor: AmountMinorInt | None = Field(
        default=None, description="inclusive; null means unbounded"
    )
    required_signers: list[SourceIdStr] = Field(default_factory=list)
    minimum_signature_count: int = Field(ge=1)
    allowed: bool
    valid_from: IsoDateStr | None = None
    valid_until: IsoDateStr | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Representative(FrozenModel):
    source_id: SourceIdStr = Field(description="stable within this extraction, e.g. rep-1")
    name: Fact[str]
    tckn_masked: Fact[TcknMaskedStr]
    title: Fact[str]
    degree: Fact[str]
    authority_mode: Fact[AuthorityMode]
    joint_with_source_ids: list[SourceIdStr] = Field(default_factory=list)
    valid_from: Fact[IsoDateStr]
    valid_until: Fact[IsoDateStr]


class ExtractionCompany(FrozenModel):
    legal_name: Fact[str]
    tax_number: Fact[TaxNumberStr]
    mersis: Fact[MersisStr]
    trade_registry_number: Fact[str]


class ExtractionNotary(FrozenModel):
    name: Fact[str]
    date: Fact[IsoDateStr]
    journal_number: Fact[str]


class ExtractionAnnex(FrozenModel):
    type: str = Field(min_length=1)
    pages: list[int] = Field(default_factory=list)
    parsed: bool


class ExtractionResult(FrozenModel):
    schema_version: Literal["1.0"]
    engine: str = Field(min_length=1)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    company: ExtractionCompany
    notary: ExtractionNotary
    document_valid_until: Fact[IsoDateStr]
    representatives: list[Representative] = Field(default_factory=list)
    rules: list[AuthorityRule] = Field(default_factory=list)
    annexes: list[ExtractionAnnex] = Field(default_factory=list)
    fields_needing_review: list[ReviewFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _source_ids_are_unique(self) -> ExtractionResult:
        seen = [r.source_id for r in self.representatives]
        if len(seen) != len(set(seen)):
            raise ValueError("representative source_id values must be unique")
        return self


# ---------------------------------------------------------------------------
# 5. Onboarding check report — IMPLEMENTATION_PLAN.md sections 5.3 and 6
# ---------------------------------------------------------------------------

# [PLAN] section 6. Exactly nine checks, always returned in this order.
CHECK_IDS: tuple[str, ...] = (
    "company_name_match",
    "tax_number_match",
    "mersis_number_match",
    "applicant_in_document",
    "identity_match",
    "authority_mode",
    "registry_company_status",
    "registry_representative_status",
    "document_validity",
)

# [PLAN] section 6.1. Documented here for the UI and for defect detection in
# tests. The bank API never applies this to derive a verdict of its own.
VERDICT_PRECEDENCE_NOTE = (
    "1 MISMATCH if any of checks 1-5 is RED; "
    "2 REGISTRY_CONFLICT if check 7 or 8 is RED and 1-5 are not; "
    "3 MISMATCH if check 6 or 9 is RED for a document-side reason; "
    "4 CO_SIGNER_REQUIRED if check 6 is AMBER and nothing is RED; "
    "5 READY if nothing is RED and authority_mode is not AMBER."
)


class CheckEvidenceItem(FrozenModel):
    label: str = Field(min_length=1)
    value: str
    document_evidence: list[EvidenceRef] | None = None


class CheckResult(FrozenModel):
    id: str = Field(min_length=1)
    status: CheckStatus
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_kind: CheckSourceKind
    evidence: list[CheckEvidenceItem] = Field(default_factory=list)


class CheckReport(FrozenModel):
    schema_version: Literal["1.0"]
    verdict: OnboardingVerdict
    checks: list[CheckResult] = Field(description="exactly nine, in the defined order")
    blocking_check_ids: list[str] = Field(default_factory=list)
    generated_at: IsoInstantStr

    @model_validator(mode="after")
    def _checks_match_the_frozen_nine(self) -> CheckReport:
        """Structural guard only — this asserts shape, never a verdict.

        Section 5.3 and section 6 both state the report carries exactly nine
        checks in a fixed order. A report that fails this is malformed, not
        merely disagreeable, so rejecting it here is contract validation rather
        than the forbidden second copy of the comparison engine.
        """
        got = tuple(c.id for c in self.checks)
        if got != CHECK_IDS:
            raise ValueError(
                f"checks must be exactly {list(CHECK_IDS)} in order, got {list(got)}"
            )
        unknown = set(self.blocking_check_ids) - set(CHECK_IDS)
        if unknown:
            raise ValueError(f"blocking_check_ids contains unknown ids: {sorted(unknown)}")
        return self


class AnalyzeRequest(FrozenModel):
    """Body the bank API sends to the AI service ``POST /analyze`` (GAP-03).

    The API loads the registry and passes it in; the AI service is stateless and
    file-system-free, so it never reads registry.json, application rows or
    uploaded files by path.
    """

    extraction: ExtractionResult
    application: "ApplicationContext"
    registry: "RegistryCompany | None"


class ApplicationContext(FrozenModel):
    """Application + branch-verified identity, as seen by the AI comparison."""

    company_name: str = Field(min_length=1)
    tax_number: TaxNumberStr
    mersis: MersisStr
    applicant_name: str = Field(min_length=1)
    applicant_tckn_masked: TcknMaskedStr
    branch_code: str = Field(min_length=1)
    identity_verified_at_branch: bool
    analysis_date: IsoDateStr = Field(
        description="date the checks are evaluated against (check 9)"
    )


# ---------------------------------------------------------------------------
# 6. Registry record — IMPLEMENTATION_PLAN.md section 5.4
# ---------------------------------------------------------------------------


class RegistryRepresentative(FrozenModel):
    id: RegistryRepIdStr
    name: str = Field(min_length=1)
    tckn: TcknMaskedStr = Field(description="always masked, e.g. 123******01")
    mode: AuthorityMode
    status: RegistryRepresentativeStatus
    effective_at: IsoDateStr


class RegistryCompany(FrozenModel):
    mersis: MersisStr
    legal_name: str = Field(min_length=1)
    tax_number: TaxNumberStr
    status: RegistryCompanyStatus
    representatives: list[RegistryRepresentative] = Field(default_factory=list)


class Registry(FrozenModel):
    """Envelope of ``data/registry.json`` and ``GET /api/registry``."""

    schema_version: Literal["1.0"]
    companies: list[RegistryCompany] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 7. Transaction decision — IMPLEMENTATION_PLAN.md section 5.5
# ---------------------------------------------------------------------------


class DecisionCheck(FrozenModel):
    status: CheckStatus
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class TransactionDecisionSource(FrozenModel):
    authority_id: int
    document_id: int
    verified_at: IsoInstantStr
    channel: Literal["BRANCH_ORIGINAL_SEEN"]


class TransactionDecision(FrozenModel):
    transaction_id: int
    verdict: TransactionVerdict
    required_cosigner: str | None = None
    checks: list[DecisionCheck] = Field(default_factory=list)
    authorization_code: Annotated[str, StringConstraints(pattern=AUTHORIZATION_CODE_PATTERN)] | None = None
    latency_ms: int = Field(ge=0, description="measured, never hardcoded")
    source: TransactionDecisionSource


# ---------------------------------------------------------------------------
# 8. Authority record view — IMPLEMENTATION_PLAN.md section 5.6
# ---------------------------------------------------------------------------


class AuthorityPerson(FrozenModel):
    id: str = Field(min_length=1)
    source_id: SourceIdStr
    name: str = Field(min_length=1)
    tckn_masked: TcknMaskedStr
    title: str
    degree: str | None = None
    valid_from: IsoDateStr | None = None
    valid_until: IsoDateStr | None = None


class AuthorityRecordView(FrozenModel):
    id: int
    mersis: MersisStr
    version: int = Field(ge=1)
    status: AuthorityRecordStatus
    source_application_id: int
    source_document_id: int
    verified_at: IsoInstantStr
    verified_by: str = Field(min_length=1)
    valid_until: IsoDateStr | None = None
    persons: list[AuthorityPerson] = Field(default_factory=list)
    rules: list[AuthorityRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 9. Standard error body — IMPLEMENTATION_PLAN.md section 5.7
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    """Frozen by addition only: new members may be added, none renamed.

    DOCUMENT_REQUIRED, INVALID_STATE_TRANSITION and STALE_CORRECTION are named
    directly in the plan (sections 5.7, 7.2, 8.7). The rest are [FROZEN-HERE] to
    cover the failure modes sections 8, 14 and 15 require to be distinguishable.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    STALE_CORRECTION = "STALE_CORRECTION"
    CORRECTION_PATH_NOT_ALLOWED = "CORRECTION_PATH_NOT_ALLOWED"
    ATTESTATION_REQUIRED = "ATTESTATION_REQUIRED"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_CONTRACT_ERROR = "AI_CONTRACT_ERROR"
    REGISTRY_UNAVAILABLE = "REGISTRY_UNAVAILABLE"
    APPROVAL_NOT_ALLOWED = "APPROVAL_NOT_ALLOWED"
    OVERRIDE_JUSTIFICATION_REQUIRED = "OVERRIDE_JUSTIFICATION_REQUIRED"
    AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"
    DUPLICATE_AUTHORITY = "DUPLICATE_AUTHORITY"
    COSIGN_NOT_ALLOWED = "COSIGN_NOT_ALLOWED"
    DEMO_MODE_DISABLED = "DEMO_MODE_DISABLED"
    UNKNOWN_CASE = "UNKNOWN_CASE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(FrozenModel):
    code: ErrorCode
    message: str = Field(min_length=1, description="user-facing Turkish copy")
    retryable: bool
    details: dict[str, object] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1)


class ErrorResponse(FrozenModel):
    """The body of every non-2xx API response.

    Section 5.7: never return stack traces, raw model responses, local paths or
    secrets. Section 14: never log or return raw document bytes or unmasked
    personal data.
    """

    error: ErrorDetail


# ---------------------------------------------------------------------------
# 10. Mutation request bodies — IMPLEMENTATION_PLAN.md section 8.7
# ---------------------------------------------------------------------------

# [PLAN] section 8.7. The only correction paths the API will ever accept.
# <source_id> resolves against the immutable representative source ID, never an
# array position or display name.
CORRECTION_PATH_ALLOWLIST: tuple[str, ...] = (
    "company.legal_name.value",
    "company.tax_number.value",
    "company.mersis.value",
    "representatives[<source_id>].name.value",
    "representatives[<source_id>].authority_mode.value",
    "document_valid_until.value",
)
CORRECTION_PATH_PATTERN = (
    r"^(company\.(legal_name|tax_number|mersis)\.value"
    r"|representatives\[[a-z][a-z0-9_-]{0,63}\]\.(name|authority_mode)\.value"
    r"|document_valid_until\.value)$"
)


class CreateApplicationRequest(FrozenModel):
    company_name: str = Field(min_length=1)
    tax_number: TaxNumberStr
    mersis: MersisStr
    applicant_name: str = Field(min_length=1)
    applicant_tckn_masked: TcknMaskedStr
    branch_code: str = Field(min_length=1)
    identity_verified_at_branch: bool


# POST /api/applications/{id}/document is multipart/form-data:
#   file: File
#   original_seen: "true" | "false"
#   scanned_by: string


class ExtractionCorrectionItem(FrozenModel):
    field_path: Annotated[str, StringConstraints(pattern=CORRECTION_PATH_PATTERN)]
    expected_old_value: object | None = Field(
        default=None, description="optimistic concurrency guard; 409 STALE_CORRECTION on drift"
    )
    new_value: object | None = None


class ExtractionCorrectionRequest(FrozenModel):
    reason: str = Field(min_length=1)
    corrections: list[ExtractionCorrectionItem] = Field(min_length=1)


class ApplicationDecisionRequest(FrozenModel):
    action: ApplicationDecisionAction
    note: str | None = None
    override_justification: str | None = Field(
        default=None, description="required only for CO_SIGNER_REQUIRED approval"
    )


class RegistryRepresentativeUpdateRequest(FrozenModel):
    status: RegistryRepresentativeStatus


class AuthorizeTransactionRequest(FrozenModel):
    mersis: MersisStr
    subject: TransactionSubject
    currency: Literal["TRY"] = CURRENCY
    amount_minor: AmountMinorInt
    initiator: str = Field(min_length=1, description="authority person ID, not a display name")


class CosignTransactionRequest(FrozenModel):
    cosigner: str = Field(min_length=1, description="authority person ID")


AnalyzeRequest.model_rebuild()
