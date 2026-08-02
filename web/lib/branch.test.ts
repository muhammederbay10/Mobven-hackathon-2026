/**
 * Tests for the pure `/branch` presentation logic: status → step mapping,
 * the decision-availability matrix and correction-path construction
 * (guide section 19).
 */

import { describe, expect, it } from "vitest";

import {
  branchStepForStatus,
  correctionCurrentValue,
  correctionFieldPath,
  decisionAvailability,
  isTerminalStatus,
} from "./branch";
import { CORRECTION_PATH_PATTERN } from "./types";
import type { ApplicationStatus, CheckReport, ExtractionResult } from "./types";

const CHECKS: CheckReport["checks"] = [
  "company_name_match",
  "tax_number_match",
  "mersis_number_match",
  "applicant_in_document",
  "identity_match",
  "authority_mode",
  "registry_status",
  "registry_representative_match",
  "document_validity",
].map((id) => ({ id, status: "green" as const, title: id, reason: "ok", evidence: {} }));

function report(verdict: CheckReport["verdict"]): CheckReport {
  return { verdict, checks: CHECKS };
}

const EXTRACTION: ExtractionResult = {
  schema_version: "1.0",
  document_id: "doc-1",
  company: {
    name: "ABC Teknoloji Limited Şirketi",
    taxNumber: "1234567890",
    mersisNumber: "0123456789000017",
    legalNameNormalized: "abc teknoloji",
  },
  notary: { name: null, date: null, yevmiye: null },
  validUntil: "2027-03-15",
  representatives: [
    {
      id: "rep-1",
      name: "Ali Yılmaz",
      nameNormalized: "ali yilmaz",
      nationalId: "123******01",
      title: "Müdür",
      mode: "SOLE",
      coSigners: [],
      limits: 50_000_000,
    },
  ],
  fieldsNeedingReview: [],
  evidence: { authorityClause: "münferiden temsile yetkilidir", page: 1 },
  rules: [],
};

describe("branchStepForStatus", () => {
  it("maps every backend status to the documented step", () => {
    const expected: Array<[ApplicationStatus | null, 1 | 2 | 3]> = [
      [null, 1],
      ["DRAFT", 1],
      ["IDENTITY_VERIFIED", 2],
      ["DOCUMENT_SCANNED", 2],
      ["ANALYZING", 2],
      ["ANALYSIS_FAILED", 2],
      ["ANALYZED", 3],
      ["APPROVED", 3],
      ["DOC_REQUESTED", 3],
      ["ESCALATED", 3],
    ];
    for (const [status, step] of expected) {
      expect(branchStepForStatus(status)).toBe(step);
    }
  });

  it("marks only the closing states as terminal", () => {
    expect(isTerminalStatus("APPROVED")).toBe(true);
    expect(isTerminalStatus("DOC_REQUESTED")).toBe(true);
    expect(isTerminalStatus("ESCALATED")).toBe(true);
    expect(isTerminalStatus("ANALYZED")).toBe(false);
    expect(isTerminalStatus("ANALYSIS_FAILED")).toBe(false);
  });
});

describe("decisionAvailability — the four-verdict approval matrix", () => {
  it("READY: normal approve", () => {
    const availability = decisionAvailability(report("READY"), EXTRACTION);
    expect(availability.approve).toBe("normal");
    expect(availability.requestDocument).toBe(true);
    expect(availability.escalate).toBe(true);
  });

  it("CO_SIGNER_REQUIRED: approve only as a justified override", () => {
    const availability = decisionAvailability(report("CO_SIGNER_REQUIRED"), EXTRACTION);
    expect(availability.approve).toBe("override");
    expect(availability.requestDocument).toBe(true);
    expect(availability.escalate).toBe(true);
  });

  it("MISMATCH and REGISTRY_CONFLICT: no approve at all", () => {
    for (const verdict of ["MISMATCH", "REGISTRY_CONFLICT"] as const) {
      const availability = decisionAvailability(report(verdict), EXTRACTION);
      expect(availability.approve).toBe("hidden");
      expect(availability.approveBlockedReason).toBeTruthy();
      expect(availability.requestDocument).toBe(true);
      expect(availability.escalate).toBe(true);
    }
  });

  it("open review flags hide approve even for READY", () => {
    const flagged = { ...EXTRACTION, fieldsNeedingReview: ["company.taxNumber"] };
    const availability = decisionAvailability(report("READY"), flagged);
    expect(availability.approve).toBe("hidden");
    expect(availability.approveBlockedReason).toBeTruthy();
  });

  it("internal AI diagnostics do not create a hidden approval deadlock", () => {
    const flagged = {
      ...EXTRACTION,
      fieldsNeedingReview: [
        "raw_chunks[3].output.rules[10].joint_with",
        "rules[27]",
        "representatives[2].mode",
      ],
    };
    const availability = decisionAvailability(report("CO_SIGNER_REQUIRED"), flagged);
    expect(availability.approve).toBe("override");
  });

  it("a human correction resolves its matching blocking review flag", () => {
    const flagged = { ...EXTRACTION, fieldsNeedingReview: ["company.taxNumber"] };
    const availability = decisionAvailability(
      report("READY"),
      flagged,
      ["company.taxNumber"],
    );
    expect(availability.approve).toBe("normal");
  });

  it("no report: no decisions at all", () => {
    const availability = decisionAvailability(null, EXTRACTION);
    expect(availability.approve).toBe("hidden");
    expect(availability.requestDocument).toBe(false);
    expect(availability.escalate).toBe(false);
  });
});

describe("correction paths", () => {
  it("builds exactly the six allowed shapes, all matching the frozen pattern", () => {
    const paths = [
      correctionFieldPath({ kind: "company", field: "name" }),
      correctionFieldPath({ kind: "company", field: "taxNumber" }),
      correctionFieldPath({ kind: "company", field: "mersisNumber" }),
      correctionFieldPath({ kind: "representative", sourceId: "rep-1", field: "name" }),
      correctionFieldPath({ kind: "representative", sourceId: "rep-1", field: "mode" }),
      correctionFieldPath({ kind: "validUntil" }),
    ];
    expect(paths).toEqual([
      "company.name",
      "company.taxNumber",
      "company.mersisNumber",
      "representatives[rep-1].name",
      "representatives[rep-1].mode",
      "validUntil",
    ]);
    for (const path of paths) {
      expect(CORRECTION_PATH_PATTERN.test(path)).toBe(true);
    }
  });

  it("reads the currently displayed value for expected_old_value", () => {
    expect(correctionCurrentValue(EXTRACTION, { kind: "company", field: "name" })).toBe(
      "ABC Teknoloji Limited Şirketi",
    );
    expect(
      correctionCurrentValue(EXTRACTION, {
        kind: "representative",
        sourceId: "rep-1",
        field: "mode",
      }),
    ).toBe("SOLE");
    expect(correctionCurrentValue(EXTRACTION, { kind: "validUntil" })).toBe("2027-03-15");
    expect(
      correctionCurrentValue(EXTRACTION, {
        kind: "representative",
        sourceId: "rep-404",
        field: "name",
      }),
    ).toBeUndefined();
  });
});
