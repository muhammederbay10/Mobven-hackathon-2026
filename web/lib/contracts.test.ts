/**
 * Frontend contract tests.
 *
 * Phase 0 shared architecture step 5: "Add backend/frontend contract tests that
 * load the AI engineer's delivered fixtures without network access."
 *
 * Every input below is a committed local file. Nothing here opens a socket, and
 * nothing here computes a check, a verdict or a decision — plan section 10.1
 * puts business verdicts exclusively in the API.
 *
 * Plan section 8.8: a failing assertion is a contract defect handed back to the
 * AI engineer, never a reason to edit anything under `ai/`.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  checkReportSchema,
  extractionResultSchema,
  registrySchema,
} from "./contracts";
import { CHECK_IDS, CORRECTION_PATH_PATTERN, PATTERNS } from "./types";

const REPO_ROOT = resolve(__dirname, "..", "..");

/** AI-engineer-owned deliverable (GAP-10, due H4). Read-only to this track. */
const AI_FIXTURES_DIR = join(REPO_ROOT, "ai", "tests", "fixtures");
const EXTRACTION_FIXTURES_DIR = join(REPO_ROOT, "data", "fixtures", "extractions");
const REPORT_FIXTURES_DIR = join(REPO_ROOT, "data", "fixtures", "reports");
const REGISTRY_SEED = join(REPO_ROOT, "data", "registry.seed.json");

type Fixture = { label: string; body: unknown };

function collectJson(...dirs: string[]): Fixture[] {
  const found: Fixture[] = [];
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    for (const name of readdirSync(dir).sort()) {
      if (!name.endsWith(".json")) continue;
      const path = join(dir, name);
      found.push({
        label: relative(REPO_ROOT, path).replace(/\\/g, "/"),
        body: JSON.parse(readFileSync(path, "utf-8")),
      });
    }
  }
  return found;
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null;

const extractions = collectJson(AI_FIXTURES_DIR, EXTRACTION_FIXTURES_DIR).filter(
  (f) => isRecord(f.body) && "representatives" in f.body,
);
const reports = collectJson(AI_FIXTURES_DIR, REPORT_FIXTURES_DIR).filter(
  (f) => isRecord(f.body) && "checks" in f.body,
);

/**
 * Skips with an explicit hand-off message while a deliverable is outstanding.
 * After the H4 freeze a skip here means a missed deliverable, not a green run.
 */
function describeDelivered(name: string, fixtures: Fixture[], body: () => void) {
  if (fixtures.length === 0) {
    describe.skip(`${name} — not delivered yet (GAP-10, due H4)`, body);
  } else {
    describe(name, body);
  }
}

/* -------------------------------------------------------------------------- */
/* Frozen values — these need no delivery and must always run                  */
/* -------------------------------------------------------------------------- */

describe("contract freeze", () => {
  it("keeps the nine check ids in the frozen order", () => {
    expect([...CHECK_IDS]).toEqual([
      "company_name_match",
      "tax_number_match",
      "mersis_number_match",
      "applicant_in_document",
      "identity_match",
      "authority_mode",
      "registry_company_status",
      "registry_representative_status",
      "document_validity",
    ]);
  });

  it("accepts only the six closed-decision correction paths", () => {
    const allowed = [
      "company.legal_name.value",
      "company.tax_number.value",
      "company.mersis.value",
      "representatives[rep-1].name.value",
      "representatives[rep-2].authority_mode.value",
      "document_valid_until.value",
    ];
    const rejected = [
      "company.trade_registry_number.value",
      "notary.name.value",
      "rules[0].max_amount_minor",
      "representatives[0].name.value",
      "representatives[rep-1].tckn_masked.value",
    ];
    for (const path of allowed) expect(CORRECTION_PATH_PATTERN.test(path)).toBe(true);
    for (const path of rejected) expect(CORRECTION_PATH_PATTERN.test(path)).toBe(false);
  });

  it("masks TCKNs and rejects a plausible unmasked one", () => {
    for (const value of ["123******01", "987******45", "456******07", "555******22"]) {
      expect(PATTERNS.tcknMasked.test(value)).toBe(true);
    }
    // Plan section 14: a plausible unmasked 11-digit TCKN is never acceptable.
    expect(PATTERNS.tcknMasked.test("12345678901")).toBe(false);
  });

  it("requires exactly nine checks in order", () => {
    const check = (id: string) => ({
      id,
      status: "GREEN" as const,
      title: id,
      reason: "kontrol edildi",
      source_kind: "DOCUMENT" as const,
      evidence: [],
    });
    const base = {
      schema_version: "1.0" as const,
      verdict: "READY" as const,
      checks: CHECK_IDS.map(check),
      blocking_check_ids: [],
      generated_at: "2026-08-01T10:00:00Z",
    };
    expect(checkReportSchema.safeParse(base).success).toBe(true);
    expect(
      checkReportSchema.safeParse({ ...base, checks: CHECK_IDS.slice(0, 8).map(check) }).success,
    ).toBe(false);
    expect(
      checkReportSchema.safeParse({ ...base, blocking_check_ids: ["nope"] }).success,
    ).toBe(false);
  });

  it("treats an unknown key as a reportable contract defect", () => {
    // Plan section 8.8: drift is reported, never silently absorbed.
    const result = checkReportSchema.safeParse({
      schema_version: "1.0",
      verdict: "READY",
      checks: CHECK_IDS.map((id) => ({
        id,
        status: "GREEN",
        title: id,
        reason: "kontrol edildi",
        source_kind: "DOCUMENT",
        evidence: [],
      })),
      blocking_check_ids: [],
      generated_at: "2026-08-01T10:00:00Z",
      confidence_score: 0.91,
    });
    expect(result.success).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* Delivered fixtures                                                          */
/* -------------------------------------------------------------------------- */

describeDelivered("delivered ExtractionResult fixtures", extractions, () => {
  it.each(extractions)("$label validates against the frozen schema", ({ body }) => {
    const result = extractionResultSchema.safeParse(body);
    expect(result.success ? null : result.error.format()).toBeNull();
  });

  it.each(extractions)("$label cites pages that exist", ({ body }) => {
    const extraction = extractionResultSchema.parse(body);
    const pages: number[] = [];
    const walk = (node: unknown): void => {
      if (Array.isArray(node)) return node.forEach(walk);
      if (!isRecord(node)) return;
      if (typeof node.page === "number" && typeof node.quote === "string") {
        pages.push(node.page);
      }
      Object.values(node).forEach(walk);
    };
    walk(body);
    for (const page of pages) {
      expect(page).toBeGreaterThanOrEqual(1);
      expect(page).toBeLessThanOrEqual(extraction.page_count);
    }
  });

  it.each(extractions)("$label keeps money as integer kuruş", ({ body }) => {
    const extraction = extractionResultSchema.parse(body);
    for (const rule of extraction.rules) {
      for (const amount of [rule.min_amount_minor, rule.max_amount_minor]) {
        if (amount === null) continue;
        expect(Number.isSafeInteger(amount)).toBe(true);
      }
      if (rule.min_amount_minor !== null && rule.max_amount_minor !== null) {
        expect(rule.min_amount_minor).toBeLessThanOrEqual(rule.max_amount_minor);
      }
    }
  });
});

describeDelivered("delivered CheckReport fixtures", reports, () => {
  it.each(reports)("$label validates against the frozen schema", ({ body }) => {
    const result = checkReportSchema.safeParse(body);
    expect(result.success ? null : result.error.format()).toBeNull();
  });
});

describe("registry seed", () => {
  it.skipIf(!existsSync(REGISTRY_SEED))("validates against the frozen schema", () => {
    const registry = registrySchema.parse(JSON.parse(readFileSync(REGISTRY_SEED, "utf-8")));
    expect(registry.companies.length).toBeGreaterThan(0);
    for (const company of registry.companies) {
      for (const rep of company.representatives) {
        // GAP-09: representatives are addressed by stable ID, never by name.
        expect(PATTERNS.registryRepId.test(rep.id)).toBe(true);
      }
    }
  });
});
