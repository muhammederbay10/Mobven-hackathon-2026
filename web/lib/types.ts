/**
 * Frozen shared contracts — TypeScript mirror.
 *
 * This file is the TypeScript twin of `api/schemas.py` and mirrors the contracts
 * in `docs/fbdocs/IMPLEMENTATION_PLAN.md` section 5, plus the enum, identifier,
 * date and error formats frozen in Phase 0 shared architecture step 3.
 *
 * Ownership: the AI engineer owns `ai/schema.py`. This file mirrors it and is
 * never the place to negotiate a contract change (plan sections 5 and 18.11).
 *
 * Types only — no runtime code. Runtime validation lives in `contracts.ts`,
 * which also type-asserts that the two stay in sync.
 *
 * Frontend rule (plan section 10.1): business verdicts come only from the API.
 * Nothing in the web app may recompute a check, a verdict or a decision.
 */

/* -------------------------------------------------------------------------- */
/* 1. Frozen identifier, date and money formats                               */
/* -------------------------------------------------------------------------- */

export const SCHEMA_VERSION = "1.0" as const;

/** [PLAN] section 8.7 / GAP-08 / GAP-09. Kept identical to api/schemas.py. */
export const PATTERNS = {
  taxNumber: /^\d{10}$/,
  mersis: /^\d{16}$/,
  tcknMasked: /^\d{3}\*{6}\d{2}$/,
  registryRepId: /^rep_[a-z0-9_]+$/,
  // Leading letter is required: plan section 8.7 addresses a representative by
  // its immutable source ID and "never an array position", so a bare integer
  // must not be a syntactically valid source ID.
  extractionSourceId: /^[a-z][a-z0-9_-]{0,63}$/,
  isoDate: /^\d{4}-\d{2}-\d{2}$/,
  isoInstant: /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$/,
  sha256: /^[0-9a-f]{64}$/,
  authorizationCode: /^YTK-[0-9A-HJ-KMNP-TV-Z]{8}$/,
} as const;

/** [PLAN] GAP-08 / section 14. Clients can never supply an audit actor. */
export const BRANCH_ACTOR = "branch_user:kozyatagi01" as const;

/** [PLAN] GAP-12. Money is integer minor units (kuruş); currency is fixed TRY. */
export const CURRENCY = "TRY" as const;
export const MAX_AMOUNT_MINOR = Number.MAX_SAFE_INTEGER;

/* -------------------------------------------------------------------------- */
/* 2. Frozen enums                                                            */
/* -------------------------------------------------------------------------- */

export type Confidence = "HIGH" | "MEDIUM" | "LOW";
export type ReviewSeverity = "INFO" | "WARNING" | "ERROR";
export type AuthorityMode = "SOLE" | "JOINT" | "LIMITED" | "UNKNOWN";
export type TransactionSubject = "GENERAL" | "CREDIT" | "REAL_ESTATE";
export type CheckStatus = "green" | "amber" | "red";
export type OnboardingVerdict =
  | "READY"
  | "CO_SIGNER_REQUIRED"
  | "MISMATCH"
  | "REGISTRY_CONFLICT";
export type CheckSourceKind = "APPLICATION" | "IDENTITY" | "DOCUMENT" | "REGISTRY";
export type TransactionVerdict = "ALLOWED" | "PENDING_COSIGN" | "DENIED";

/** [PLAN] section 7.1 */
export type ApplicationStatus =
  | "DRAFT"
  | "IDENTITY_VERIFIED"
  | "DOCUMENT_SCANNED"
  | "ANALYZING"
  | "ANALYZED"
  | "APPROVED"
  | "DOC_REQUESTED"
  | "ESCALATED"
  | "ANALYSIS_FAILED";

/** [PLAN] section 7.3 */
export type TransactionStatus = "REQUESTED" | "ALLOWED" | "PENDING_COSIGN" | "DENIED";

export type AuthorityRecordStatus = "ACTIVE" | "SUSPENDED";
export type RegistryCompanyStatus = "ACTIVE" | "INACTIVE";
export type RegistryRepresentativeStatus = "ACTIVE" | "REMOVED";
export type ApplicationDecisionAction = "approve" | "request_document" | "escalate";

/**
 * [PLAN] GAP-07. Approval matrix, for enabling/disabling UI actions only.
 * The API re-enforces this server-side; the UI may never be the gate.
 */
export const APPROVABLE_VERDICTS: readonly OnboardingVerdict[] = [
  "READY",
  "CO_SIGNER_REQUIRED",
] as const;
export const VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION: readonly OnboardingVerdict[] = [
  "CO_SIGNER_REQUIRED",
] as const;

/* -------------------------------------------------------------------------- */
/* 3. Common primitives — plan section 5.1                                    */
/* -------------------------------------------------------------------------- */

export type EvidenceRef = {
  /** 1-based */
  page: number;
  /** verbatim source text */
  quote: string;
  /** normalized x1,y1,x2,y2 */
  bbox?: [number, number, number, number] | null;
};

export type Fact<T> = {
  value: T | null;
  confidence: Confidence;
  evidence: EvidenceRef[];
};

export type ReviewFlag = {
  code: string;
  severity: ReviewSeverity;
  field_path: string;
  message: string;
  evidence?: EvidenceRef[] | null;
};

/* -------------------------------------------------------------------------- */
/* 4. Extraction result — plan section 5.2                                    */
/* -------------------------------------------------------------------------- */

export type CanonicalAuthorityRule = {
  id: string;
  subject: TransactionSubject;
  currency: "TRY";
  /** inclusive integer kuruş */
  min_amount_minor: number | null;
  /** inclusive; null means unbounded */
  max_amount_minor: number | null;
  /** representative source_ids */
  required_signers: string[];
  minimum_signature_count: number;
  allowed: boolean;
  valid_from: string | null;
  valid_until: string | null;
  evidence: EvidenceRef[];
};

export type CanonicalRepresentative = {
  /** stable within this extraction, e.g. rep-1 */
  source_id: string;
  name: Fact<string>;
  tckn_masked: Fact<string>;
  title: Fact<string>;
  degree: Fact<string>;
  authority_mode: Fact<AuthorityMode>;
  joint_with_source_ids: string[];
  valid_from: Fact<string>;
  valid_until: Fact<string>;
};

export type CanonicalExtractionCompany = {
  legal_name: Fact<string>;
  tax_number: Fact<string>;
  mersis: Fact<string>;
  trade_registry_number: Fact<string>;
};

export type CanonicalExtractionNotary = {
  name: Fact<string>;
  date: Fact<string>;
  journal_number: Fact<string>;
};

export type CanonicalExtractionAnnex = {
  type: string;
  pages: number[];
  parsed: boolean;
};

export type CanonicalExtractionResult = {
  schema_version: "1.0";
  engine: string;
  document_sha256: string;
  page_count: number;
  company: CanonicalExtractionCompany;
  notary: CanonicalExtractionNotary;
  document_valid_until: Fact<string>;
  representatives: CanonicalRepresentative[];
  rules: CanonicalAuthorityRule[];
  annexes: CanonicalExtractionAnnex[];
  fields_needing_review: ReviewFlag[];
};

/** Public flat wire projection from docs/API_CONTRACT.md. */
export type SourceEvidence = {
  page: number;
  quote: string;
};

export type AuthorityRule = {
  scope: string;
  /** integer kuruş; null means unbounded/not applicable */
  threshold: number | null;
  mode: "SOLE" | "JOINT" | null;
  /** representative IDs such as rep-1; never display names */
  coSigners: string[];
  blocked: boolean;
  evidence: SourceEvidence;
};

export type Representative = {
  /** stable document-order ID, e.g. rep-1 */
  id: string;
  name: string;
  nameNormalized: string;
  nationalId: string | null;
  title: string | null;
  mode: "SOLE" | "JOINT";
  /** human-readable names for display */
  coSigners: string[];
  /** integer kuruş */
  limits: number | null;
};

export type ExtractionCompany = {
  name: string;
  taxNumber: string | null;
  mersisNumber: string | null;
  legalNameNormalized: string;
};

export type ExtractionNotary = {
  name: string | null;
  date: string | null;
  yevmiye: string | null;
};

export type ExtractionResult = {
  schema_version: "1.0";
  document_id: string;
  company: ExtractionCompany;
  notary: ExtractionNotary;
  validUntil: string | null;
  representatives: Representative[];
  fieldsNeedingReview: string[];
  evidence: {
    authorityClause: string;
    page: number;
  };
  rules: AuthorityRule[];
};

/* -------------------------------------------------------------------------- */
/* 5. Onboarding check report — plan sections 5.3 and 6                       */
/* -------------------------------------------------------------------------- */

/** [PLAN] section 6. Exactly nine checks, always returned in this order. */
export const CHECK_IDS = [
  "company_name_match",
  "tax_number_match",
  "mersis_number_match",
  "applicant_in_document",
  "identity_match",
  "authority_mode",
  "registry_status",
  "registry_representative_match",
  "document_validity",
] as const;

export type CheckId = (typeof CHECK_IDS)[number];

export type CheckEvidence = Record<string, string | number | boolean | null>;

export type CheckResult = {
  id: string;
  status: CheckStatus;
  title: string;
  reason: string;
  evidence: CheckEvidence;
};

export type CheckReport = {
  /** exactly nine, in CHECK_IDS order */
  checks: CheckResult[];
  verdict: OnboardingVerdict;
};

/* -------------------------------------------------------------------------- */
/* 6. Registry record — plan section 5.4                                      */
/* -------------------------------------------------------------------------- */

export type RegistryRepresentative = {
  id: string;
  name: string;
  /** always masked, e.g. 123******01 */
  tckn: string;
  mode: AuthorityMode;
  status: RegistryRepresentativeStatus;
  effective_at: string;
};

export type RegistryCompany = {
  mersis: string;
  legal_name: string;
  tax_number: string;
  status: RegistryCompanyStatus;
  representatives: RegistryRepresentative[];
};

export type Registry = {
  schema_version: "1.0";
  companies: RegistryCompany[];
};

/* -------------------------------------------------------------------------- */
/* 7. Transaction decision — plan section 5.5                                 */
/* -------------------------------------------------------------------------- */

export type DecisionCheck = {
  status: CheckStatus;
  title: string;
  reason: string;
};

export type TransactionDecisionSource = {
  authority_id: number;
  document_id: number;
  verified_at: string;
  channel: "BRANCH_ORIGINAL_SEEN";
};

export type TransactionDecision = {
  transaction_id: number;
  verdict: TransactionVerdict;
  required_cosigner: string | null;
  checks: DecisionCheck[];
  authorization_code: string | null;
  /** measured server-side, never hardcoded */
  latency_ms: number;
  source: TransactionDecisionSource;
};

/* -------------------------------------------------------------------------- */
/* 8. Authority record view — plan section 5.6                                */
/* -------------------------------------------------------------------------- */

export type AuthorityPerson = {
  id: string;
  source_id: string;
  name: string;
  tckn_masked: string;
  title: string;
  degree: string | null;
  valid_from: string | null;
  valid_until: string | null;
};

export type AuthorityRecordView = {
  id: number;
  mersis: string;
  version: number;
  status: AuthorityRecordStatus;
  source_application_id: number;
  source_document_id: number;
  verified_at: string;
  verified_by: string;
  valid_until: string | null;
  persons: AuthorityPerson[];
  rules: AuthorityRule[];
};

/* -------------------------------------------------------------------------- */
/* 8b. Bank-API resource views — plan section 8.3                             */
/* -------------------------------------------------------------------------- */
/* Mirrors api/schemas.py section 11. Bank-owned resources are snake_case;    */
/* the embedded AI extraction stays camelCase where ExtractionResult defines  */
/* it (alignment guide section 7).                                            */

export type ApplicationView = {
  id: number;
  company_name: string;
  tax_number: string;
  mersis: string;
  applicant_name: string;
  applicant_tckn_masked: string;
  branch_code: string;
  identity_verified_at_branch: boolean;
  status: ApplicationStatus;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentView = {
  id: number;
  application_id: number;
  original_filename: string;
  mime_type: "application/pdf" | "image/png" | "image/jpeg";
  size_bytes: number;
  document_sha256: string;
  page_count: number;
  original_seen: boolean;
  scanned_by: string;
  created_at: string;
};

/** One row of the append-only review history (alignment guide section 7). */
export type CorrectionView = {
  id: number;
  field_path: string;
  old_value_json: { value: unknown };
  new_value_json: { value: unknown };
  reviewer: string;
  reason: string;
  created_at: string;
};

/**
 * The single server-backed payload used to restore the branch screen.
 * `extraction` is already the effective, corrected projection — the raw
 * database row is never exposed (guide section 7).
 */
export type ApplicationAggregate = {
  application: ApplicationView;
  document: DocumentView | null;
  extraction: ExtractionResult | null;
  report: CheckReport | null;
  corrections: CorrectionView[];
  authority: AuthorityRecordView | null;
};

export type AuthorityHistoryResponse = {
  items: AuthorityRecordView[];
};

export type AuditItem = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  correlation_id: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type AuditHistoryResponse = { items: AuditItem[] };

/* -------------------------------------------------------------------------- */
/* 9. Standard error body — plan section 5.7                                  */
/* -------------------------------------------------------------------------- */

/** Frozen by addition only: members may be added, none renamed. */
export type ErrorCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "DOCUMENT_REQUIRED"
  | "INVALID_STATE_TRANSITION"
  | "STALE_CORRECTION"
  | "CORRECTION_PATH_NOT_ALLOWED"
  | "ATTESTATION_REQUIRED"
  | "UNSUPPORTED_MEDIA_TYPE"
  | "PAYLOAD_TOO_LARGE"
  | "ANALYSIS_IN_PROGRESS"
  | "AI_TIMEOUT"
  | "AI_UNAVAILABLE"
  | "AI_CONTRACT_ERROR"
  | "REGISTRY_UNAVAILABLE"
  | "APPROVAL_NOT_ALLOWED"
  | "OVERRIDE_JUSTIFICATION_REQUIRED"
  | "AUTHORITY_NOT_FOUND"
  | "DUPLICATE_AUTHORITY"
  | "COSIGN_NOT_ALLOWED"
  | "DEMO_MODE_DISABLED"
  | "UNKNOWN_CASE"
  | "INTERNAL_ERROR";

export type ErrorDetail = {
  code: ErrorCode;
  /** user-facing Turkish copy */
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
  correlation_id: string;
};

export type ErrorResponse = {
  error: ErrorDetail;
};

/* -------------------------------------------------------------------------- */
/* 10. Mutation request bodies — plan section 8.7                             */
/* -------------------------------------------------------------------------- */

/**
 * [PLAN] section 8.7. The only correction paths the API will ever accept.
 * `<source_id>` resolves against the immutable representative source ID,
 * never an array position or display name.
 */
export const CORRECTION_PATH_ALLOWLIST = [
  "company.name",
  "company.taxNumber",
  "company.mersisNumber",
  "representatives[<source_id>].name",
  "representatives[<source_id>].mode",
  "validUntil",
] as const;

export const CORRECTION_PATH_PATTERN =
  /^(company\.(name|taxNumber|mersisNumber)|representatives\[[a-z][a-z0-9_-]{0,63}\]\.(name|mode)|validUntil)$/;

export type CreateApplicationRequest = {
  company_name: string;
  tax_number: string;
  mersis: string;
  applicant_name: string;
  applicant_tckn_masked: string;
  branch_code: string;
  identity_verified_at_branch: boolean;
};

/**
 * POST /api/applications/{id}/document is multipart/form-data:
 *   file: File
 *   original_seen: "true" | "false"
 *   scanned_by: string
 */
export type UploadDocumentFields = {
  original_seen: "true" | "false";
  scanned_by: string;
};

export type ExtractionCorrectionItem = {
  field_path: string;
  /** optimistic concurrency guard; 409 STALE_CORRECTION on drift */
  expected_old_value: unknown;
  new_value: unknown;
};

export type ExtractionCorrectionRequest = {
  reason: string;
  corrections: ExtractionCorrectionItem[];
};

export type ApplicationDecisionRequest = {
  action: ApplicationDecisionAction;
  note?: string;
  /** required only for CO_SIGNER_REQUIRED approval */
  override_justification?: string;
};

export type RegistryRepresentativeUpdateRequest = {
  status: RegistryRepresentativeStatus;
};

export type AuthorizeTransactionRequest = {
  mersis: string;
  subject: TransactionSubject;
  currency: "TRY";
  /** non-negative integer kuruş */
  amount_minor: number;
  /** authority person ID, not a display name */
  initiator: string;
};

export type CosignTransactionRequest = {
  /** authority person ID */
  cosigner: string;
};
