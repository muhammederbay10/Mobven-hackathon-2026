"""Shared contracts for the YetkiCheck bank API and the external AI service.

The AI-wire models mirror ``docs/API_CONTRACT.md``. Bank-owned resource models
remain governed by ``docs/fbdocs/IMPLEMENTATION_PLAN.md``. Its TypeScript twin
is ``web/lib/types.ts`` / ``web/lib/contracts.ts``.

Ownership
---------
The AI engineer owns ``ai/schema.py``. This file consumes its public JSON
projection; it never replaces the AI-owned source.

Strictness policy
-----------------
AI responses and bank API messages reject unknown fields. ``/analyze`` input
records are the one documented exception: the AI service deliberately ignores
unknown application/registry fields so a whole database row can be sent safely.

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
import re
from typing import Annotated, Any, Generic, Literal, TypeVar

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
AmountMinorInt = Annotated[int, Field(strict=True, ge=0, le=MAX_AMOUNT_MINOR)]


class FrozenModel(BaseModel):
    """Base for every contract model: unknown keys are a reportable defect."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=False,
        populate_by_name=True,
    )


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


class SignatureMode(str, Enum):
    """Closed signature-mode set exposed by the AI wire contract."""

    SOLE = "SOLE"
    JOINT = "JOINT"


class TransactionSubject(str, Enum):
    GENERAL = "GENERAL"
    CREDIT = "CREDIT"
    REAL_ESTATE = "REAL_ESTATE"


class CheckStatus(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class OnboardingVerdict(str, Enum):
    READY = "READY"
    CO_SIGNER_REQUIRED = "CO_SIGNER_REQUIRED"
    MISMATCH = "MISMATCH"
    REGISTRY_CONFLICT = "REGISTRY_CONFLICT"


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


class CanonicalAuthorityRule(FrozenModel):
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


class CanonicalRepresentative(FrozenModel):
    source_id: SourceIdStr = Field(description="stable within this extraction, e.g. rep-1")
    name: Fact[str]
    tckn_masked: Fact[TcknMaskedStr]
    title: Fact[str]
    degree: Fact[str]
    authority_mode: Fact[AuthorityMode]
    joint_with_source_ids: list[SourceIdStr] = Field(default_factory=list)
    valid_from: Fact[IsoDateStr]
    valid_until: Fact[IsoDateStr]


class CanonicalExtractionCompany(FrozenModel):
    legal_name: Fact[str]
    tax_number: Fact[TaxNumberStr]
    mersis: Fact[MersisStr]
    trade_registry_number: Fact[str]


class CanonicalExtractionNotary(FrozenModel):
    name: Fact[str]
    date: Fact[IsoDateStr]
    journal_number: Fact[str]


class CanonicalExtractionAnnex(FrozenModel):
    type: str = Field(min_length=1)
    pages: list[int] = Field(default_factory=list)
    parsed: bool


class CanonicalExtractionResult(FrozenModel):
    schema_version: Literal["1.0"]
    engine: str = Field(min_length=1)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    company: CanonicalExtractionCompany
    notary: CanonicalExtractionNotary
    document_valid_until: Fact[IsoDateStr]
    representatives: list[CanonicalRepresentative] = Field(default_factory=list)
    rules: list[CanonicalAuthorityRule] = Field(default_factory=list)
    annexes: list[CanonicalExtractionAnnex] = Field(default_factory=list)
    fields_needing_review: list[ReviewFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _source_ids_are_unique(self) -> CanonicalExtractionResult:
        seen = [r.source_id for r in self.representatives]
        if len(seen) != len(set(seen)):
            raise ValueError("representative source_id values must be unique")
        return self


# ---------------------------------------------------------------------------
# Public flat extraction contract â€” docs/API_CONTRACT.md section 3
# ---------------------------------------------------------------------------


class SourceEvidence(FrozenModel):
    page: int = Field(ge=1, description="1-based page number")
    quote: str = Field(min_length=1, description="verbatim source text")


class AuthorityClauseEvidence(FrozenModel):
    authority_clause: str = Field(min_length=1, alias="authorityClause")
    page: int = Field(ge=1)


class ExtractionCompany(FrozenModel):
    name: str = Field(min_length=1)
    tax_number: TaxNumberStr | None = Field(default=None, alias="taxNumber")
    mersis_number: MersisStr | None = Field(default=None, alias="mersisNumber")
    legal_name_normalized: str = Field(min_length=1, alias="legalNameNormalized")


class ExtractionNotary(FrozenModel):
    name: str | None = None
    date: IsoDateStr | None = None
    yevmiye: str | None = None


class Representative(FrozenModel):
    id: SourceIdStr = Field(description="stable document-order ID, e.g. rep-1")
    name: str = Field(min_length=1)
    name_normalized: str = Field(min_length=1, alias="nameNormalized")
    national_id: TcknMaskedStr | None = Field(default=None, alias="nationalId")
    title: str | None = None
    mode: SignatureMode
    co_signers: list[str] = Field(default_factory=list, alias="coSigners")
    limits: AmountMinorInt | None = None


class ExtractionRule(FrozenModel):
    scope: str = Field(min_length=1)
    threshold: AmountMinorInt | None = None
    mode: SignatureMode | None = None
    co_signers: list[SourceIdStr] = Field(default_factory=list, alias="coSigners")
    blocked: bool = False
    evidence: SourceEvidence

    @model_validator(mode="after")
    def _blocked_shape_is_consistent(self) -> ExtractionRule:
        if self.blocked and (self.mode is not None or self.co_signers):
            raise ValueError("a blocked rule requires mode=null and coSigners=[]")
        if not self.blocked and self.mode is None:
            raise ValueError("a non-blocked rule requires a signature mode")
        return self


# Approved authority records store the reviewed AI rule projection verbatim.
AuthorityRule = ExtractionRule


class ExtractionResult(FrozenModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_id: str = Field(min_length=1)
    company: ExtractionCompany
    notary: ExtractionNotary
    valid_until: IsoDateStr | None = Field(default=None, alias="validUntil")
    representatives: list[Representative]
    fields_needing_review: list[str] = Field(default_factory=list, alias="fieldsNeedingReview")
    evidence: AuthorityClauseEvidence
    rules: list[ExtractionRule]

    @model_validator(mode="after")
    def _references_are_stable_and_resolved(self) -> ExtractionResult:
        ids = [representative.id for representative in self.representatives]
        if len(ids) != len(set(ids)):
            raise ValueError("representative id values must be unique")
        known = set(ids)
        unresolved = sorted(
            signer
            for rule in self.rules
            for signer in rule.co_signers
            if signer not in known
        )
        if unresolved:
            raise ValueError(f"rule coSigners contain unknown representative ids: {unresolved}")
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
    "registry_status",
    "registry_representative_match",
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


class CheckResult(FrozenModel):
    id: str = Field(min_length=1)
    status: CheckStatus
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CheckReport(FrozenModel):
    verdict: OnboardingVerdict
    checks: list[CheckResult] = Field(description="exactly nine, in the defined order")

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
        return self


class InboundModel(BaseModel):
    """Tolerant records accepted by the AI service's ``/analyze`` endpoint."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ApplicationContext(InboundModel):
    """Application + branch-verified identity, as seen by the AI comparison."""

    company_name: str | None = None
    tax_number: str | None = None
    mersis: str | None = None
    applicant_name: str | None = None
    applicant_tckn: str | None = None
    branch_code: str | None = None
    identity_verified_at_branch: bool = False


class AnalyzeRegistryRepresentative(InboundModel):
    name: str
    tckn: str | None = None
    mode: str | None = None
    status: str = "ACTIVE"


class AnalyzeRegistryCompany(InboundModel):
    name: str | None = None
    status: str = "ACTIVE"
    reps: list[AnalyzeRegistryRepresentative] = Field(default_factory=list)


class AnalyzeRequest(InboundModel):
    """Exact body sent to the deterministic AI ``POST /analyze`` endpoint."""

    extraction: ExtractionResult
    application: ApplicationContext = Field(default_factory=ApplicationContext)
    registry: dict[str, AnalyzeRegistryCompany] = Field(default_factory=dict)
    as_of: IsoDateStr | None = None


class AIHealthResponse(FrozenModel):
    status: Literal["ok"]
    engine: str = Field(min_length=1)
    schema_version: Literal["1.0"]


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
    "company.name",
    "company.taxNumber",
    "company.mersisNumber",
    "representatives[<source_id>].name",
    "representatives[<source_id>].mode",
    "validUntil",
)
CORRECTION_PATH_PATTERN = (
    r"^(company\.(name|taxNumber|mersisNumber)"
    r"|representatives\[[a-z][a-z0-9_-]{0,63}\]\.(name|mode)"
    r"|validUntil)$"
)


def unresolved_blocking_review_fields(
    fields_needing_review: list[str],
    corrected_field_paths: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """Return only unresolved review flags the branch operator can act on.

    The AI response is persisted verbatim, including internal diagnostics such
    as ``raw_chunks`` and ``rules``. Those paths are valuable for audit/debugging
    but are not editable in the branch UI and therefore must not create a hidden
    approval deadlock. The correction allowlist is the single source of truth
    for which review flags are user-actionable and blocking.
    """

    return [
        field_path
        for field_path in fields_needing_review
        if re.fullmatch(CORRECTION_PATH_PATTERN, field_path)
        and field_path not in corrected_field_paths
    ]


class CreateApplicationRequest(FrozenModel):
    company_name: str = Field(min_length=1)
    tax_number: TaxNumberStr
    mersis: MersisStr
    applicant_name: str = Field(min_length=1)
    applicant_tckn_masked: TcknMaskedStr
    branch_code: str = Field(min_length=1)
    identity_verified_at_branch: bool


# ---------------------------------------------------------------------------
# 11. Bank-API resource views — IMPLEMENTATION_PLAN.md section 8.3
# ---------------------------------------------------------------------------


class ApplicationView(FrozenModel):
    id: int
    company_name: str
    tax_number: TaxNumberStr
    mersis: MersisStr
    applicant_name: str
    applicant_tckn_masked: TcknMaskedStr
    branch_code: str
    identity_verified_at_branch: bool
    status: ApplicationStatus
    version: int = Field(ge=1)
    created_at: IsoInstantStr
    updated_at: IsoInstantStr


class DocumentView(FrozenModel):
    id: int
    application_id: int
    original_filename: str
    mime_type: Literal["application/pdf", "image/png", "image/jpeg"]
    size_bytes: int = Field(ge=1)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    original_seen: bool
    scanned_by: str
    created_at: IsoInstantStr


class ApplicationAggregate(FrozenModel):
    """The single server-backed payload used to restore the branch screen."""

    application: ApplicationView
    document: DocumentView | None = None
    extraction: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    authority: dict[str, Any] | None = None


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
