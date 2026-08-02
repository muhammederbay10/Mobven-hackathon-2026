# ai/schema.py
"""Defines every Pydantic model used or emitted by the AI service."""

from __future__ import annotations

from datetime import date as Date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

if __package__:
    from .turkish import strip_company_suffix, tr_normalize
else:  # uvicorn main:app started from inside ai/
    from turkish import strip_company_suffix, tr_normalize


SCHEMA_VERSION = "1.0"
MaskedNationalId = Annotated[
    str,
    StringConstraints(pattern=r"^\d{3}\*{6}\d{2}$"),
]


class StrictModel(BaseModel):
    """Rejects contract drift while accepting Python names and JSON aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SignatureMode(StrEnum):
    SOLE = "SOLE"
    JOINT = "JOINT"


class CheckStatus(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class CheckVerdict(StrEnum):
    READY = "READY"
    CO_SIGNER_REQUIRED = "CO_SIGNER_REQUIRED"
    MISMATCH = "MISMATCH"
    REGISTRY_CONFLICT = "REGISTRY_CONFLICT"


class CheckId(StrEnum):
    COMPANY_NAME_MATCH = "company_name_match"
    TAX_NUMBER_MATCH = "tax_number_match"
    MERSIS_NUMBER_MATCH = "mersis_number_match"
    APPLICANT_IN_DOCUMENT = "applicant_in_document"
    IDENTITY_MATCH = "identity_match"
    AUTHORITY_MODE = "authority_mode"
    REGISTRY_STATUS = "registry_status"
    REGISTRY_REPRESENTATIVE_MATCH = "registry_representative_match"
    DOCUMENT_VALIDITY = "document_validity"


CHECK_IDS = tuple(CheckId)


class PageLabel(StrEnum):
    IDENTITY_HEADER = "identity_header"
    DAYANAK = "dayanak"
    APPOINTMENTS = "appointments"
    RULES = "rules"
    SPECIMENS = "specimens"
    NOTARY_BLOCK = "notary_block"
    IC_YONERGE_ANNEX = "ic_yonerge_annex"
    BOARD_RESOLUTION_ANNEX = "board_resolution_annex"
    GAZETTE_ANNEX = "gazette_annex"
    IMZA_BEYANNAMESI = "imza_beyannamesi"
    COVER_OR_BLANK = "cover_or_blank"
    OTHER_UNKNOWN = "other_unknown"


class RulePartyType(StrEnum):
    GROUP = "group"
    PERSON = "person"
    UNRESOLVED_EXTERNAL = "unresolved_external"


class RuleSource(StrEnum):
    CIRCULAR = "circular"
    DIRECTIVE = "directive"
    ANNEX = "annex"


class RuleConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleSigningForm(StrEnum):
    SOLE = "sole"
    JOINT = "joint"


class FlagSeverity(StrEnum):
    INFO = "info"
    WARN = "warn"
    SERIOUS = "serious"


class ReferenceResolution(StrEnum):
    IN_FILE = "in_file"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class DocumentReferenceType(StrEnum):
    BOARD_RESOLUTION = "board_resolution"
    IC_YONERGE = "ic_yonerge"
    GAZETTE = "gazette"
    CIRCULAR = "circular"
    OTHER = "other"


class ExtractorAgent(StrEnum):
    APPOINTMENTS = "appointments"
    RULES = "rules"
    SPECIMENS = "specimens"
    ANNEX = "annex"
    REVIEW = "review"


class ExtractorRole(StrEnum):
    PRIMARY = "primary"
    WITNESS = "witness"


class ExtractorStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProgressState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineMode(StrEnum):
    LIVE = "live"
    STUB = "stub"
    REPLAY = "replay"


class PipelineStageStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class SourceEvidence(StrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)


class RulePartyRef(StrictModel):
    type: RulePartyType
    ref: str | None = None
    name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_reference_shape(self) -> RulePartyRef:
        if self.type in {RulePartyType.GROUP, RulePartyType.PERSON} and not self.ref:
            raise ValueError("group and person references require ref")
        if self.type is RulePartyType.UNRESOLVED_EXTERNAL and not self.name:
            raise ValueError("unresolved_external references require name")
        return self


class AuthorityRule(StrictModel):
    """Amounts are integer kuruş (1 TL = 100 kuruş), matching the flat contract's money unit
    so no float-rounding conversion ever happens between the rich and flat representations."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    who: RulePartyRef
    sole_or_joint: RuleSigningForm
    joint_with: list[RulePartyRef] = Field(default_factory=list)
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    currency: str | None = None
    scope_tags: list[str] = Field(default_factory=list)
    scope_text: str
    valid_until: Date | None = None
    source: RuleSource
    evidence: SourceEvidence
    confidence: RuleConfidence
    partial: bool = False

    @model_validator(mode="after")
    def validate_amount_range(self) -> AuthorityRule:
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_max <= self.amount_min
        ):
            raise ValueError("amount_max must be greater than amount_min")
        return self


class SpecimenBoundingBox(StrictModel):
    page: int = Field(ge=1)
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_coordinates(self) -> SpecimenBoundingBox:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("specimen bounding box must have positive area")
        return self


class SignatoryRecord(StrictModel):
    id: str
    name_printed: str = Field(min_length=1)
    name_normalized: str = Field(min_length=1)
    title: str | None = None
    id_no_masked: MaskedNationalId | None = None
    group_code: str | None = None
    valid_from: Date | None = None
    valid_until: Date | None = None
    authority_form: str | None = None
    joint_with_names: list[str] = Field(default_factory=list)
    evidence: SourceEvidence | None = None
    specimen_bboxes: list[SpecimenBoundingBox] = Field(default_factory=list)


class PageClassification(StrictModel):
    page: int = Field(ge=1)
    labels: list[PageLabel] = Field(min_length=1)
    continues_on_next: bool = False


class PageMap(StrictModel):
    company_name_line: str | None = None
    structure_hints: list[str] = Field(default_factory=list)
    pages: list[PageClassification] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_page_numbers(self) -> PageMap:
        page_numbers = [page.page for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("page map contains duplicate page numbers")
        if page_numbers != sorted(page_numbers):
            raise ValueError("page map must be ordered by page number")
        return self


RawDate = Date | Literal["UNREADABLE"]


class RawCompanyExtraction(StrictModel):
    legal_name: str = Field(min_length=1)
    vkn: str | None = None
    trade_registry_no: str | None = None
    mersis: str | None = None
    address: str | None = None
    evidence: list[SourceEvidence] = Field(default_factory=list)


class RawNotaryExtraction(StrictModel):
    name: str | None = None
    date: RawDate | None = None
    yevmiye_no: str | None = None
    evidence: list[SourceEvidence] = Field(default_factory=list)


class RawDocumentReference(StrictModel):
    ref_doc_type: DocumentReferenceType
    ref_date: RawDate | None = None
    ref_number: str | None = None
    evidence: SourceEvidence


class RawAppointment(StrictModel):
    name_printed: str = Field(min_length=1)
    title: str | None = None
    id_no_masked: str | None = None
    group_code: str | None = None
    authority_form: str | None = None
    joint_with_names: list[str] = Field(default_factory=list)
    valid_from: RawDate | None = None
    valid_until: RawDate | None = None
    evidence: SourceEvidence


class AppointmentsAgentOutput(StrictModel):
    company: RawCompanyExtraction
    notary: RawNotaryExtraction | None = None
    document_valid_until: RawDate | None = None
    appointments: list[RawAppointment] = Field(default_factory=list)
    references: list[RawDocumentReference] = Field(default_factory=list)


class RawRuleParty(StrictModel):
    type: RulePartyType
    ref: str | None = None
    name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_raw_reference_shape(self) -> RawRuleParty:
        if self.type is RulePartyType.GROUP and not self.ref:
            raise ValueError("raw group references require ref")
        if self.type in {RulePartyType.PERSON, RulePartyType.UNRESOLVED_EXTERNAL} and not self.name:
            raise ValueError("raw person references require name")
        return self


class RawAuthorityRule(StrictModel):
    who: RawRuleParty
    sole_or_joint: RuleSigningForm
    joint_with: list[RawRuleParty] = Field(default_factory=list)
    amount_min: int | None = Field(default=None, ge=0)
    amount_max: int | None = Field(default=None, ge=0)
    currency: str | None = None
    scope_tags: list[str] = Field(default_factory=list)
    scope_text: str
    valid_until: RawDate | None = None
    evidence: SourceEvidence
    partial: bool = False

    @model_validator(mode="after")
    def validate_raw_amount_range(self) -> RawAuthorityRule:
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_max <= self.amount_min
        ):
            raise ValueError("amount_max must be greater than amount_min")
        return self


class RulesAgentOutput(StrictModel):
    rules: list[RawAuthorityRule] = Field(default_factory=list)


class RawSpecimen(StrictModel):
    name_printed: str = Field(min_length=1)
    title: str | None = None
    group_code: str | None = None
    signature_bbox: SpecimenBoundingBox


class SpecimensAgentOutput(StrictModel):
    specimens: list[RawSpecimen] = Field(default_factory=list)


AgentOutput = AppointmentsAgentOutput | RulesAgentOutput | SpecimensAgentOutput


class ChunkExtractionResult(StrictModel):
    chunk_id: str = Field(min_length=1)
    agent: ExtractorAgent
    role: ExtractorRole
    status: ExtractorStatus
    model: str | None = None
    supporting_only: bool = False
    attempts: int = Field(ge=0, le=2)
    chunk_failed: bool = False
    output: AgentOutput | None = None
    error: str | None = None
    raw_responses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> ChunkExtractionResult:
        if self.status is ExtractorStatus.SUCCESS:
            if self.output is None or self.error is not None or self.chunk_failed:
                raise ValueError("successful chunk results require output and no failure fields")
            if self.attempts not in {1, 2}:
                raise ValueError("successful chunk results require one or two attempts")
        elif self.status is ExtractorStatus.FAILED:
            if self.output is not None or not self.error or not self.chunk_failed:
                raise ValueError("failed chunk results require error and chunk_failed=true")
            if self.attempts != 2:
                raise ValueError("failed chunk results require two attempts")
        elif self.output is not None or self.attempts != 0 or self.chunk_failed:
            raise ValueError("skipped chunk results cannot carry output, attempts, or failure")
        return self


class ExtractorProgress(StrictModel):
    name: str
    state: ProgressState
    detail: str = ""
    chunk_id: str
    role: ExtractorRole


class CompanyRecord(StrictModel):
    legal_name: str
    vkn: str | None = None
    trade_registry_no: str | None = None
    mersis: str | None = None
    address: str | None = None
    evidence: list[SourceEvidence] = Field(default_factory=list)


class NotaryRecord(StrictModel):
    name: str | None = None
    date: Date | None = None
    yevmiye_no: str | None = None
    evidence: list[SourceEvidence] = Field(default_factory=list)


class DocumentReference(StrictModel):
    ref_doc_type: DocumentReferenceType
    ref_date: Date | None = None
    ref_number: str | None = None
    resolved: ReferenceResolution = ReferenceResolution.UNKNOWN


class ProvenanceFlag(StrictModel):
    severity: FlagSeverity
    check_name: str
    message: str
    field_path: str
    evidence_page: int | None = Field(default=None, ge=1)
    anomaly_code: str | None = None


class ValidationOutcome(StrictModel):
    flags: list[ProvenanceFlag] = Field(default_factory=list)
    fields_needing_review: list[str] = Field(
        default_factory=list, alias="fieldsNeedingReview"
    )
    anomaly_codes: list[str] = Field(default_factory=list, alias="anomalyCodes")


class CircularExtraction(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_id: str
    company: CompanyRecord
    notary: NotaryRecord | None = None
    valid_until: Date | None = None
    signatories: list[SignatoryRecord] = Field(default_factory=list)
    rules: list[AuthorityRule] = Field(default_factory=list)
    page_map: PageMap
    references: list[DocumentReference] = Field(default_factory=list)
    provenance_flags: list[ProvenanceFlag] = Field(default_factory=list)
    raw_chunks: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionCompany(StrictModel):
    """Company identity in the flat contract.

    `name` is the printed value and is authoritative for display, evidence and audit.
    `legal_name_normalized` is derived, non-authoritative and recomputable; it exists
    only so consumers can compare without re-implementing Turkish normalization.
    """

    name: str
    tax_number: str | None = Field(default=None, alias="taxNumber")
    mersis_number: str | None = Field(default=None, alias="mersisNumber")
    legal_name_normalized: str | None = Field(default=None, alias="legalNameNormalized")

    @model_validator(mode="after")
    def derive_legal_name_normalized(self) -> ExtractionCompany:
        # Derived here rather than in the projection so the two can never disagree.
        object.__setattr__(self, "legal_name_normalized", strip_company_suffix(self.name))
        return self


class ExtractionNotary(StrictModel):
    name: str | None = None
    date: Date | None = None
    yevmiye: str | None = None


class Representative(StrictModel):
    """A signatory in the flat contract.

    `id` is a stable source identifier ('rep-1', 'rep-2', ...) assigned by document order —
    a join key that survives a name correction, unlike matching on `name`.
    `name` is the printed value and is authoritative for display, evidence and audit.
    `name_normalized` is derived, non-authoritative and recomputable. Consumers such as
    api/ must match people on `name_normalized`; comparing printed names re-introduces
    Turkish casing bugs (ALİ YILMAZ vs Ali Yılmaz) outside the single source of truth.
    `limits` is integer kuruş (1 TL = 100 kuruş): 500,000.00 TL is 50000000.
    """

    id: str = Field(min_length=1)
    name: str
    name_normalized: str | None = Field(default=None, alias="nameNormalized")
    national_id: MaskedNationalId | None = Field(default=None, alias="nationalId")
    title: str | None = None
    mode: SignatureMode
    co_signers: list[str] = Field(default_factory=list, alias="coSigners")
    limits: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def derive_name_normalized(self) -> Representative:
        # Derived here rather than in the projection so the two can never disagree.
        object.__setattr__(self, "name_normalized", tr_normalize(self.name))
        return self


class AuthorityClauseEvidence(StrictModel):
    authority_clause: str = Field(alias="authorityClause")
    page: int = Field(ge=1)


class ExtractionRule(StrictModel):
    """Flat optional projection agreed in PLAN_ALIGNMENT conflict 1.

    `threshold` is integer kuruş (1 TL = 100 kuruş); null means unbounded within this scope.
    `coSigners` holds representative `id`s (e.g. "rep-2"), NOT names — a rule is machine-consumed
    by the authority engine, which must resolve signers by stable ID rather than by fragile,
    Turkish-casing-sensitive name strings. (Representative.coSigners is the opposite case: it
    stays names, because compare.py reads it to print a human-readable Turkish check reason.)
    `blocked` represents either a scope the circular explicitly excludes or a clause that cannot
    be executed safely because a required party did not resolve to the roster. A blocked rule
    carries `mode: null` and empty `coSigners`; its evidence remains visible for human review
    instead of being silently dropped.
    """

    scope: str
    threshold: int | None = Field(default=None, ge=0)
    mode: SignatureMode | None = None
    co_signers: list[str] = Field(default_factory=list, alias="coSigners")
    blocked: bool = False
    evidence: SourceEvidence

    @model_validator(mode="after")
    def validate_blocked_shape(self) -> ExtractionRule:
        if self.blocked:
            if self.mode is not None or self.co_signers:
                raise ValueError("a blocked rule must not carry a mode or coSigners")
        elif self.mode is None:
            raise ValueError("a non-blocked rule requires a mode")
        return self


class ExtractionResult(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_id: str
    company: ExtractionCompany
    notary: ExtractionNotary
    valid_until: Date | None = Field(default=None, alias="validUntil")
    representatives: list[Representative]
    fields_needing_review: list[str] = Field(
        default_factory=list, alias="fieldsNeedingReview"
    )
    evidence: AuthorityClauseEvidence
    rules: list[ExtractionRule] | None = None

    @model_validator(mode="after")
    def validate_rule_signer_ids_resolve(self) -> ExtractionResult:
        # A rule co-signer that resolves to nobody would let the authority engine silently
        # skip a required signature instead of flagging it — fail loudly here instead.
        known_ids = {representative.id for representative in self.representatives}
        for index, rule in enumerate(self.rules or []):
            for signer_id in rule.co_signers:
                if signer_id not in known_ids:
                    raise ValueError(
                        f"rules[{index}].coSigners references unknown representative id {signer_id!r}"
                    )
        return self


class PipelineStageTiming(StrictModel):
    stage: str = Field(min_length=1)
    seconds: float = Field(ge=0)
    status: PipelineStageStatus = PipelineStageStatus.OK
    detail: str | None = None


class ExtractionCacheEntry(StrictModel):
    """Private sha256-keyed replay artifact; never returned by the HTTP API."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: ExtractionResult
    circular: CircularExtraction | None = None
    timings: list[PipelineStageTiming] = Field(default_factory=list)
    sorter_raw_responses: list[str] = Field(default_factory=list)
    page_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    degraded: bool = False


CheckEvidenceValue = str | int | float | bool | None


class CheckItem(StrictModel):
    id: CheckId
    status: CheckStatus
    title: str
    reason: str
    evidence: dict[str, CheckEvidenceValue] = Field(default_factory=dict)


class CheckReport(StrictModel):
    verdict: CheckVerdict
    checks: list[CheckItem]

    @model_validator(mode="after")
    def validate_check_order(self) -> CheckReport:
        check_ids = tuple(check.id for check in self.checks)
        if check_ids != CHECK_IDS:
            raise ValueError("checks must contain all nine frozen IDs in order")
        return self


class InboundModel(BaseModel):
    """Tolerates unknown fields on the way in.

    Outbound shapes stay strict, but a caller that sends a whole database row — or a registry file
    a human edited live on stage — must get a report back, never a 422.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ApplicationRecord(InboundModel):
    """The branch application, mirroring the applications table in docs/PLAN.md section 1.3."""

    company_name: str | None = None
    tax_number: str | None = None
    mersis: str | None = None
    applicant_name: str | None = None
    applicant_tckn: str | None = None
    branch_code: str | None = None
    identity_verified_at_branch: bool = False


class RegistryRepresentative(InboundModel):
    """One person in the mock MERSİS registry. Status is free text so a live edit cannot 422."""

    name: str
    tckn: str | None = None
    mode: str | None = None
    status: str = "ACTIVE"


class RegistryCompany(InboundModel):
    name: str | None = None
    status: str = "ACTIVE"
    reps: list[RegistryRepresentative] = Field(default_factory=list)


class AnalyzeRequest(InboundModel):
    """POST /analyze body. Registry is keyed by MERSİS number, exactly as data/registry.json is."""

    extraction: ExtractionResult
    application: ApplicationRecord = Field(default_factory=ApplicationRecord)
    registry: dict[str, RegistryCompany] = Field(default_factory=dict)
    as_of: Date | None = None


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    engine: str
    schema_version: Literal["1.0"] = SCHEMA_VERSION
