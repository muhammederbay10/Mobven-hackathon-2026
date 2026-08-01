/**
 * Strict-parsing tests for the bank-API resource schemas added by the
 * frontend/backend alignment work (guide sections 7 and 19). Where a real
 * fixture exists in the repo it is used, so these tests double as drift
 * detectors against the delivered AI payloads.
 */

import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  applicationAggregateSchema,
  applicationViewSchema,
  auditHistoryResponseSchema,
  authorityHistoryResponseSchema,
  correctionViewSchema,
  documentViewSchema,
} from "./contracts";

const REPO_ROOT = resolve(__dirname, "..", "..");

function fixture(...segments: string[]): unknown | null {
  const path = join(REPO_ROOT, ...segments);
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf-8")) : null;
}

const APPLICATION_VIEW = {
  id: 1,
  company_name: "ABC Teknoloji Ltd. Şti.",
  tax_number: "1234567890",
  mersis: "0123456789000017",
  applicant_name: "Ali Yılmaz",
  applicant_tckn_masked: "123******01",
  branch_code: "kozyatagi01",
  identity_verified_at_branch: true,
  status: "ANALYZED",
  version: 3,
  created_at: "2026-08-01T10:00:00Z",
  updated_at: "2026-08-01T10:05:00Z",
};

const DOCUMENT_VIEW = {
  id: 7,
  application_id: 1,
  original_filename: "case1.pdf",
  mime_type: "application/pdf",
  size_bytes: 48211,
  document_sha256: "a".repeat(64),
  page_count: 2,
  original_seen: true,
  scanned_by: "Şube görevlisi",
  created_at: "2026-08-01T10:01:00Z",
};

const CORRECTION_VIEW = {
  id: 4,
  field_path: "representatives[rep-1].name",
  old_value_json: { value: "Ali Yilmaz" },
  new_value_json: { value: "Ali Yılmaz" },
  reviewer: "branch_user:kozyatagi01",
  reason: "Noter belgesiyle tekrar kontrol edildi.",
  created_at: "2026-08-01T10:03:00Z",
};

const AUDIT_ITEM = {
  id: 11,
  actor: "branch_user:kozyatagi01",
  action: "APPLICATION_DECIDED",
  entity_type: "APPLICATION",
  entity_id: "1",
  correlation_id: "corr-123",
  detail: { action: "approve" },
  created_at: "2026-08-01T10:06:00Z",
};

describe("ApplicationView schema", () => {
  it("accepts the backend shape", () => {
    expect(applicationViewSchema.safeParse(APPLICATION_VIEW).success).toBe(true);
  });

  it("rejects unknown keys and unknown statuses", () => {
    expect(
      applicationViewSchema.safeParse({ ...APPLICATION_VIEW, surprise: 1 }).success,
    ).toBe(false);
    expect(
      applicationViewSchema.safeParse({ ...APPLICATION_VIEW, status: "PENDING" }).success,
    ).toBe(false);
  });

  it("rejects an unmasked TCKN", () => {
    expect(
      applicationViewSchema.safeParse({
        ...APPLICATION_VIEW,
        applicant_tckn_masked: "12345678901",
      }).success,
    ).toBe(false);
  });
});

describe("DocumentView schema", () => {
  it("accepts the backend shape", () => {
    expect(documentViewSchema.safeParse(DOCUMENT_VIEW).success).toBe(true);
  });

  it("rejects unsupported mime types and malformed hashes", () => {
    expect(
      documentViewSchema.safeParse({ ...DOCUMENT_VIEW, mime_type: "image/webp" }).success,
    ).toBe(false);
    expect(
      documentViewSchema.safeParse({ ...DOCUMENT_VIEW, document_sha256: "zz" }).success,
    ).toBe(false);
  });
});

describe("CorrectionView schema", () => {
  it("accepts an append-only history row", () => {
    expect(correctionViewSchema.safeParse(CORRECTION_VIEW).success).toBe(true);
  });

  it("requires the {value} box shape on both sides", () => {
    expect(
      correctionViewSchema.safeParse({ ...CORRECTION_VIEW, old_value_json: {} }).success,
    ).toBe(false);
    expect(
      correctionViewSchema.safeParse({
        ...CORRECTION_VIEW,
        new_value_json: { value: "x", extra: 1 },
      }).success,
    ).toBe(false);
  });

  it("rejects field paths outside the frozen allowlist", () => {
    expect(
      correctionViewSchema.safeParse({ ...CORRECTION_VIEW, field_path: "notary.name" }).success,
    ).toBe(false);
    expect(
      correctionViewSchema.safeParse({ ...CORRECTION_VIEW, field_path: "representatives[0].name" })
        .success,
    ).toBe(false);
  });
});

describe("ApplicationAggregate schema", () => {
  it("accepts a pre-analysis aggregate with nulls", () => {
    const aggregate = {
      application: { ...APPLICATION_VIEW, status: "IDENTITY_VERIFIED" },
      document: null,
      extraction: null,
      report: null,
      corrections: [],
      authority: null,
    };
    expect(applicationAggregateSchema.safeParse(aggregate).success).toBe(true);
  });

  it("accepts a fully analyzed aggregate built from delivered fixtures", () => {
    const extraction = fixture("data", "fixtures", "extractions", "case1.json");
    const report = fixture("data", "fixtures", "reports", "case1.json");
    if (extraction === null || report === null) return; // fixtures not delivered here
    const aggregate = {
      application: APPLICATION_VIEW,
      document: DOCUMENT_VIEW,
      extraction,
      report,
      corrections: [CORRECTION_VIEW],
      authority: null,
    };
    const parsed = applicationAggregateSchema.safeParse(aggregate);
    expect(parsed.success ? null : parsed.error.format()).toBeNull();
  });

  it("rejects unknown top-level keys", () => {
    const aggregate = {
      application: APPLICATION_VIEW,
      document: null,
      extraction: null,
      report: null,
      corrections: [],
      authority: null,
      raw_extraction_row: {},
    };
    expect(applicationAggregateSchema.safeParse(aggregate).success).toBe(false);
  });
});

describe("history and audit envelopes", () => {
  it("parses an empty authority history", () => {
    expect(authorityHistoryResponseSchema.safeParse({ items: [] }).success).toBe(true);
  });

  it("parses audit items and rejects non-envelope bodies", () => {
    expect(auditHistoryResponseSchema.safeParse({ items: [AUDIT_ITEM] }).success).toBe(true);
    expect(auditHistoryResponseSchema.safeParse([AUDIT_ITEM]).success).toBe(false);
    expect(
      auditHistoryResponseSchema.safeParse({ items: [{ ...AUDIT_ITEM, entity_id: 1 }] }).success,
    ).toBe(false);
  });
});
