/**
 * Runtime validation for the frozen shared contracts.
 *
 * `types.ts` holds the hand-written mirror of `docs/fbdocs/IMPLEMENTATION_PLAN.md`
 * section 5 — it is what the app codes against and what diffs cleanly against the
 * plan. This file holds the runtime schemas used by the contract tests, plus
 * compile-time assertions that the two descriptions cannot drift apart: if a zod
 * schema and its hand-written type stop agreeing, `npm run typecheck` fails.
 *
 * Strictness mirrors `api/schemas.py`: unknown keys are rejected. On AI-delivered
 * payloads an unknown key is drift, and plan section 8.8 requires drift to be
 * reported as a contract defect to the AI engineer rather than silently absorbed.
 *
 * This module performs no business logic. It never derives a verdict, a check
 * status or a decision (plan sections 6 and 10.1).
 */

import { z } from "zod";

import { CHECK_IDS, CORRECTION_PATH_PATTERN, PATTERNS } from "./types";
import type {
  AuthorityRecordView,
  CheckReport,
  ErrorResponse,
  ExtractionResult,
  Registry,
  TransactionDecision,
} from "./types";

/* -------------------------------------------------------------------------- */
/* Frozen primitives                                                          */
/* -------------------------------------------------------------------------- */

const schemaVersion = z.literal("1.0");
const taxNumber = z.string().regex(PATTERNS.taxNumber);
const mersis = z.string().regex(PATTERNS.mersis);
const tcknMasked = z.string().regex(PATTERNS.tcknMasked);
const registryRepId = z.string().regex(PATTERNS.registryRepId);
const sourceId = z.string().regex(PATTERNS.extractionSourceId);
const isoDate = z.string().regex(PATTERNS.isoDate);
const isoInstant = z.string().regex(PATTERNS.isoInstant);
const sha256 = z.string().regex(PATTERNS.sha256);
const authorizationCode = z.string().regex(PATTERNS.authorizationCode);
const amountMinor = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);

export const confidenceSchema = z.enum(["HIGH", "MEDIUM", "LOW"]);
export const reviewSeveritySchema = z.enum(["INFO", "WARNING", "ERROR"]);
export const authorityModeSchema = z.enum(["SOLE", "JOINT", "LIMITED", "UNKNOWN"]);
export const transactionSubjectSchema = z.enum(["GENERAL", "CREDIT", "REAL_ESTATE"]);
export const checkStatusSchema = z.enum(["GREEN", "AMBER", "RED"]);
export const onboardingVerdictSchema = z.enum([
  "READY",
  "CO_SIGNER_REQUIRED",
  "MISMATCH",
  "REGISTRY_CONFLICT",
]);
export const checkSourceKindSchema = z.enum([
  "APPLICATION",
  "IDENTITY",
  "DOCUMENT",
  "REGISTRY",
]);
export const transactionVerdictSchema = z.enum(["ALLOWED", "PENDING_COSIGN", "DENIED"]);

/* -------------------------------------------------------------------------- */
/* Common primitives — plan section 5.1                                       */
/* -------------------------------------------------------------------------- */

export const evidenceRefSchema = z
  .object({
    page: z.number().int().min(1),
    quote: z.string().min(1),
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable().optional(),
  })
  .strict();

const fact = <T extends z.ZodTypeAny>(value: T) =>
  z
    .object({
      value: value.nullable(),
      confidence: confidenceSchema,
      evidence: z.array(evidenceRefSchema),
    })
    .strict();

export const reviewFlagSchema = z
  .object({
    code: z.string().min(1),
    severity: reviewSeveritySchema,
    field_path: z.string().min(1),
    message: z.string().min(1),
    evidence: z.array(evidenceRefSchema).nullable().optional(),
  })
  .strict();

/* -------------------------------------------------------------------------- */
/* Extraction result — plan section 5.2                                       */
/* -------------------------------------------------------------------------- */

export const authorityRuleSchema = z
  .object({
    id: z.string().min(1),
    subject: transactionSubjectSchema,
    currency: z.literal("TRY"),
    min_amount_minor: amountMinor.nullable(),
    max_amount_minor: amountMinor.nullable(),
    required_signers: z.array(sourceId),
    minimum_signature_count: z.number().int().min(1),
    allowed: z.boolean(),
    valid_from: isoDate.nullable(),
    valid_until: isoDate.nullable(),
    evidence: z.array(evidenceRefSchema),
  })
  .strict();

export const representativeSchema = z
  .object({
    source_id: sourceId,
    name: fact(z.string()),
    tckn_masked: fact(tcknMasked),
    title: fact(z.string()),
    degree: fact(z.string()),
    authority_mode: fact(authorityModeSchema),
    joint_with_source_ids: z.array(sourceId),
    valid_from: fact(isoDate),
    valid_until: fact(isoDate),
  })
  .strict();

export const extractionResultSchema = z
  .object({
    schema_version: schemaVersion,
    engine: z.string().min(1),
    document_sha256: sha256,
    page_count: z.number().int().min(1),
    company: z
      .object({
        legal_name: fact(z.string()),
        tax_number: fact(taxNumber),
        mersis: fact(mersis),
        trade_registry_number: fact(z.string()),
      })
      .strict(),
    notary: z
      .object({
        name: fact(z.string()),
        date: fact(isoDate),
        journal_number: fact(z.string()),
      })
      .strict(),
    document_valid_until: fact(isoDate),
    representatives: z.array(representativeSchema),
    rules: z.array(authorityRuleSchema),
    annexes: z.array(
      z
        .object({
          type: z.string().min(1),
          pages: z.array(z.number().int()),
          parsed: z.boolean(),
        })
        .strict(),
    ),
    fields_needing_review: z.array(reviewFlagSchema),
  })
  .strict()
  .superRefine((value, ctx) => {
    const ids = value.representatives.map((r) => r.source_id);
    if (new Set(ids).size !== ids.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["representatives"],
        message: "representative source_id values must be unique",
      });
    }
  });

/* -------------------------------------------------------------------------- */
/* Check report — plan sections 5.3 and 6                                     */
/* -------------------------------------------------------------------------- */

export const checkResultSchema = z
  .object({
    id: z.string().min(1),
    status: checkStatusSchema,
    title: z.string().min(1),
    reason: z.string().min(1),
    source_kind: checkSourceKindSchema,
    evidence: z.array(
      z
        .object({
          label: z.string().min(1),
          value: z.string(),
          document_evidence: z.array(evidenceRefSchema).nullable().optional(),
        })
        .strict(),
    ),
  })
  .strict();

export const checkReportSchema = z
  .object({
    schema_version: schemaVersion,
    verdict: onboardingVerdictSchema,
    checks: z.array(checkResultSchema),
    blocking_check_ids: z.array(z.string()),
    generated_at: isoInstant,
  })
  .strict()
  .superRefine((value, ctx) => {
    // Structural guard only: shape, not verdict. Plan section 6 forbids the bank
    // API and the frontend from holding a second copy of the comparison engine.
    const got = value.checks.map((c) => c.id);
    if (got.length !== CHECK_IDS.length || got.some((id, i) => id !== CHECK_IDS[i])) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["checks"],
        message: `checks must be exactly [${CHECK_IDS.join(", ")}] in order, got [${got.join(", ")}]`,
      });
    }
    const unknown = value.blocking_check_ids.filter(
      (id) => !(CHECK_IDS as readonly string[]).includes(id),
    );
    if (unknown.length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["blocking_check_ids"],
        message: `unknown check ids: ${unknown.join(", ")}`,
      });
    }
  });

/* -------------------------------------------------------------------------- */
/* Registry — plan section 5.4                                                */
/* -------------------------------------------------------------------------- */

export const registryCompanySchema = z
  .object({
    mersis,
    legal_name: z.string().min(1),
    tax_number: taxNumber,
    status: z.enum(["ACTIVE", "INACTIVE"]),
    representatives: z.array(
      z
        .object({
          id: registryRepId,
          name: z.string().min(1),
          tckn: tcknMasked,
          mode: authorityModeSchema,
          status: z.enum(["ACTIVE", "REMOVED"]),
          effective_at: isoDate,
        })
        .strict(),
    ),
  })
  .strict();

export const registrySchema = z
  .object({
    schema_version: schemaVersion,
    companies: z.array(registryCompanySchema),
  })
  .strict();

/* -------------------------------------------------------------------------- */
/* Transaction decision — plan section 5.5                                    */
/* -------------------------------------------------------------------------- */

export const transactionDecisionSchema = z
  .object({
    transaction_id: z.number().int(),
    verdict: transactionVerdictSchema,
    required_cosigner: z.string().nullable(),
    checks: z.array(
      z
        .object({
          status: checkStatusSchema,
          title: z.string().min(1),
          reason: z.string().min(1),
        })
        .strict(),
    ),
    authorization_code: authorizationCode.nullable(),
    latency_ms: z.number().int().min(0),
    source: z
      .object({
        authority_id: z.number().int(),
        document_id: z.number().int(),
        verified_at: isoInstant,
        channel: z.literal("BRANCH_ORIGINAL_SEEN"),
      })
      .strict(),
  })
  .strict();

/* -------------------------------------------------------------------------- */
/* Authority record view — plan section 5.6                                   */
/* -------------------------------------------------------------------------- */

export const authorityRecordViewSchema = z
  .object({
    id: z.number().int(),
    mersis,
    version: z.number().int().min(1),
    status: z.enum(["ACTIVE", "SUSPENDED"]),
    source_application_id: z.number().int(),
    source_document_id: z.number().int(),
    verified_at: isoInstant,
    verified_by: z.string().min(1),
    valid_until: isoDate.nullable(),
    persons: z.array(
      z
        .object({
          id: z.string().min(1),
          source_id: sourceId,
          name: z.string().min(1),
          tckn_masked: tcknMasked,
          title: z.string(),
          degree: z.string().nullable(),
          valid_from: isoDate.nullable(),
          valid_until: isoDate.nullable(),
        })
        .strict(),
    ),
    rules: z.array(authorityRuleSchema),
  })
  .strict();

/* -------------------------------------------------------------------------- */
/* Standard error body — plan section 5.7                                     */
/* -------------------------------------------------------------------------- */

export const errorCodeSchema = z.enum([
  "VALIDATION_ERROR",
  "NOT_FOUND",
  "DOCUMENT_REQUIRED",
  "INVALID_STATE_TRANSITION",
  "STALE_CORRECTION",
  "CORRECTION_PATH_NOT_ALLOWED",
  "ATTESTATION_REQUIRED",
  "UNSUPPORTED_MEDIA_TYPE",
  "PAYLOAD_TOO_LARGE",
  "ANALYSIS_IN_PROGRESS",
  "AI_TIMEOUT",
  "AI_UNAVAILABLE",
  "AI_CONTRACT_ERROR",
  "REGISTRY_UNAVAILABLE",
  "APPROVAL_NOT_ALLOWED",
  "OVERRIDE_JUSTIFICATION_REQUIRED",
  "AUTHORITY_NOT_FOUND",
  "DUPLICATE_AUTHORITY",
  "COSIGN_NOT_ALLOWED",
  "DEMO_MODE_DISABLED",
  "UNKNOWN_CASE",
  "INTERNAL_ERROR",
]);

export const errorResponseSchema = z
  .object({
    error: z
      .object({
        code: errorCodeSchema,
        message: z.string().min(1),
        retryable: z.boolean(),
        details: z.record(z.unknown()),
        correlation_id: z.string().min(1),
      })
      .strict(),
  })
  .strict();

/* -------------------------------------------------------------------------- */
/* Mutation request bodies — plan section 8.7                                 */
/* -------------------------------------------------------------------------- */

export const createApplicationRequestSchema = z
  .object({
    company_name: z.string().min(1),
    tax_number: taxNumber,
    mersis,
    applicant_name: z.string().min(1),
    applicant_tckn_masked: tcknMasked,
    branch_code: z.string().min(1),
    identity_verified_at_branch: z.boolean(),
  })
  .strict();

export const extractionCorrectionRequestSchema = z
  .object({
    reason: z.string().min(1),
    corrections: z
      .array(
        z
          .object({
            field_path: z.string().regex(CORRECTION_PATH_PATTERN),
            expected_old_value: z.unknown(),
            new_value: z.unknown(),
          })
          .strict(),
      )
      .min(1),
  })
  .strict();

export const applicationDecisionRequestSchema = z
  .object({
    action: z.enum(["approve", "request_document", "escalate"]),
    note: z.string().optional(),
    override_justification: z.string().optional(),
  })
  .strict();

export const registryRepresentativeUpdateRequestSchema = z
  .object({ status: z.enum(["ACTIVE", "REMOVED"]) })
  .strict();

export const authorizeTransactionRequestSchema = z
  .object({
    mersis,
    subject: transactionSubjectSchema,
    currency: z.literal("TRY"),
    amount_minor: amountMinor,
    initiator: z.string().min(1),
  })
  .strict();

export const cosignTransactionRequestSchema = z
  .object({ cosigner: z.string().min(1) })
  .strict();

/* -------------------------------------------------------------------------- */
/* Drift guards                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Fails `npm run typecheck` if a zod schema and its hand-written twin in
 * `types.ts` stop describing the same shape. Each pair is asserted in both
 * directions, so neither a missing nor an extra field can slip through.
 */
type MutuallyAssignable<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;

const _extractionResultInSync: MutuallyAssignable<
  z.infer<typeof extractionResultSchema>,
  ExtractionResult
> = true;
const _checkReportInSync: MutuallyAssignable<
  z.infer<typeof checkReportSchema>,
  CheckReport
> = true;
const _registryInSync: MutuallyAssignable<z.infer<typeof registrySchema>, Registry> = true;
const _transactionDecisionInSync: MutuallyAssignable<
  z.infer<typeof transactionDecisionSchema>,
  TransactionDecision
> = true;
const _authorityRecordViewInSync: MutuallyAssignable<
  z.infer<typeof authorityRecordViewSchema>,
  AuthorityRecordView
> = true;
const _errorResponseInSync: MutuallyAssignable<
  z.infer<typeof errorResponseSchema>,
  ErrorResponse
> = true;

void _extractionResultInSync;
void _checkReportInSync;
void _registryInSync;
void _transactionDecisionInSync;
void _authorityRecordViewInSync;
void _errorResponseInSync;
