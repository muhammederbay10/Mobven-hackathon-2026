/**
 * Pure presentation logic for the `/branch` screen.
 *
 * Everything here maps **server-returned** state to UI affordances. Nothing
 * computes a verdict, a check or a decision — the alignment guide (sections 9
 * and 10) makes the backend the enforcement authority; these helpers only
 * choose what to show for a state the backend already returned, and they are
 * unit-tested in `branch.test.ts`.
 */

import type {
  ApplicationStatus,
  CheckReport,
  ExtractionResult,
  OnboardingVerdict,
} from "./types";

/* -------------------------------------------------------------------------- */
/* Status → stepper mapping (guide section 9)                                 */
/* -------------------------------------------------------------------------- */

export type BranchStep = 1 | 2 | 3;

/** Which of the three header steps is active for a backend status. */
export function branchStepForStatus(status: ApplicationStatus | null): BranchStep {
  switch (status) {
    case null:
    case "DRAFT":
      return 1;
    case "IDENTITY_VERIFIED":
    case "DOCUMENT_SCANNED":
    case "ANALYZING":
    case "ANALYSIS_FAILED":
      return 2;
    case "ANALYZED":
    case "APPROVED":
    case "DOC_REQUESTED":
    case "ESCALATED":
      return 3;
  }
}

/** Statuses whose branch flow is finished (terminal or hinge). */
export function isTerminalStatus(status: ApplicationStatus): boolean {
  return status === "APPROVED" || status === "DOC_REQUESTED" || status === "ESCALATED";
}

/* -------------------------------------------------------------------------- */
/* Decision availability (guide section 10, step 3)                           */
/* -------------------------------------------------------------------------- */

/**
 * What the decision controls may offer for the current server aggregate.
 * Usability filtering only — the backend re-enforces all of it and remains the
 * authority (guide: "The frontend may hide obviously invalid actions for
 * usability, but the backend remains the enforcement authority.").
 *
 * - `approve: "normal"` — READY with nothing needing review.
 * - `approve: "override"` — CO_SIGNER_REQUIRED; exceptional approve requiring a
 *   typed `override_justification`.
 * - `approve: "hidden"` — MISMATCH, REGISTRY_CONFLICT, or open review flags.
 */
export type DecisionAvailability = {
  approve: "normal" | "override" | "hidden";
  requestDocument: boolean;
  escalate: boolean;
  /** Turkish explanation shown when approve is hidden. */
  approveBlockedReason: string | null;
};

export function decisionAvailability(
  report: CheckReport | null,
  extraction: ExtractionResult | null,
): DecisionAvailability {
  if (report === null) {
    return {
      approve: "hidden",
      requestDocument: false,
      escalate: false,
      approveBlockedReason: null,
    };
  }

  const openReviewFields = extraction?.fieldsNeedingReview ?? [];
  if (openReviewFields.length > 0) {
    return {
      approve: "hidden",
      requestDocument: true,
      escalate: true,
      approveBlockedReason:
        "İncelenmesi gereken alanlar var. Düzeltme yapılıp yeniden analiz edilmeden onay verilemez.",
    };
  }

  const byVerdict: Record<OnboardingVerdict, DecisionAvailability> = {
    READY: {
      approve: "normal",
      requestDocument: true,
      escalate: true,
      approveBlockedReason: null,
    },
    CO_SIGNER_REQUIRED: {
      approve: "override",
      requestDocument: true,
      escalate: true,
      approveBlockedReason: null,
    },
    MISMATCH: {
      approve: "hidden",
      requestDocument: true,
      escalate: true,
      approveBlockedReason: "Başvuru ile belge uyuşmuyor; onay kapalı.",
    },
    REGISTRY_CONFLICT: {
      approve: "hidden",
      requestDocument: true,
      escalate: true,
      approveBlockedReason: "Sicil kaydıyla çelişki var; onay kapalı.",
    },
  };
  return byVerdict[report.verdict];
}

/* -------------------------------------------------------------------------- */
/* Correction paths (guide section 10 — the six allowed targets)              */
/* -------------------------------------------------------------------------- */

export type CorrectionTarget =
  | { kind: "company"; field: "name" | "taxNumber" | "mersisNumber" }
  | { kind: "representative"; sourceId: string; field: "name" | "mode" }
  | { kind: "validUntil" };

/** Builds the exact `field_path` string the backend allowlist accepts. */
export function correctionFieldPath(target: CorrectionTarget): string {
  switch (target.kind) {
    case "company":
      return `company.${target.field}`;
    case "representative":
      return `representatives[${target.sourceId}].${target.field}`;
    case "validUntil":
      return "validUntil";
  }
}

/** The value currently displayed for a target — sent as `expected_old_value`. */
export function correctionCurrentValue(
  extraction: ExtractionResult,
  target: CorrectionTarget,
): unknown {
  switch (target.kind) {
    case "company":
      return extraction.company[target.field];
    case "representative": {
      const representative = extraction.representatives.find(
        (item) => item.id === target.sourceId,
      );
      return representative ? representative[target.field] : undefined;
    }
    case "validUntil":
      return extraction.validUntil;
  }
}
