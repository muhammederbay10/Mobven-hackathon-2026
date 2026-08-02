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
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    who: RulePartyRef
    sole_or_joint: RuleSigningForm
    joint_with: list[RulePartyRef] = Field(default_factory=list)
    amount_min: float | None = Field(default=None, ge=0)
    amount_max: float | None = Field(default=None, ge=0)
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

    `name` is the printed value and is authoritative for display, evidence and audit.
    `name_normalized` is derived, non-authoritative and recomputable. Consumers such as
    api/ must match people on `name_normalized`; comparing printed names re-introduces
    Turkish casing bugs (ALİ YILMAZ vs Ali Yılmaz) outside the single source of truth.
    """

    name: str
    name_normalized: str | None = Field(default=None, alias="nameNormalized")
    national_id: MaskedNationalId | None = Field(default=None, alias="nationalId")
    title: str | None = None
    mode: SignatureMode
    co_signers: list[str] = Field(default_factory=list, alias="coSigners")
    limits: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def derive_name_normalized(self) -> Representative:
        # Derived here rather than in the projection so the two can never disagree.
        object.__setattr__(self, "name_normalized", tr_normalize(self.name))
        return self


class AuthorityClauseEvidence(StrictModel):
    authority_clause: str = Field(alias="authorityClause")
    page: int = Field(ge=1)


class ExtractionRule(StrictModel):
    """Flat optional projection agreed in PLAN_ALIGNMENT conflict 1."""

    scope: str
    threshold: float | None = Field(default=None, ge=0)
    mode: SignatureMode
    co_signers: list[str] = Field(default_factory=list, alias="coSigners")
    evidence: SourceEvidence


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
