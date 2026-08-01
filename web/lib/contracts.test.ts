/** Offline contract tests for the public flat AI projection. */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { checkReportSchema, extractionResultSchema, registrySchema } from "./contracts";
import { CHECK_IDS, CORRECTION_PATH_PATTERN, PATTERNS } from "./types";

const REPO_ROOT = resolve(__dirname, "..", "..");
const AI_FIXTURES_DIR = join(REPO_ROOT, "ai", "tests", "fixtures");
const EXTRACTION_FIXTURES_DIR = join(REPO_ROOT, "data", "fixtures", "extractions");
const REPORT_FIXTURES_DIR = join(REPO_ROOT, "data", "fixtures", "reports");
const REGISTRY_SEED = join(REPO_ROOT, "data", "registry.seed.json");

type Fixture = { label: string; body: unknown };

function collectJson(...dirs: string[]): Fixture[] {
  return dirs.flatMap((dir) =>
    existsSync(dir)
      ? readdirSync(dir)
          .filter((name) => name.endsWith(".json"))
          .sort()
          .map((name) => {
            const path = join(dir, name);
            return {
              label: relative(REPO_ROOT, path).replace(/\\/g, "/"),
              body: JSON.parse(readFileSync(path, "utf-8")),
            };
          })
      : [],
  );
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const extractions = collectJson(AI_FIXTURES_DIR, EXTRACTION_FIXTURES_DIR).filter(
  ({ body }) => isRecord(body) && "representatives" in body,
);
const reports = collectJson(AI_FIXTURES_DIR, REPORT_FIXTURES_DIR).filter(
  ({ body }) => isRecord(body) && "checks" in body,
);

function describeDelivered(name: string, fixtures: Fixture[], body: () => void) {
  return fixtures.length === 0 ? describe.skip(`${name} — not delivered`, body) : describe(name, body);
}

describe("contract freeze", () => {
  it("keeps the AI engineer's nine IDs in order", () => {
    expect([...CHECK_IDS]).toEqual([
      "company_name_match",
      "tax_number_match",
      "mersis_number_match",
      "applicant_in_document",
      "identity_match",
      "authority_mode",
      "registry_status",
      "registry_representative_match",
      "document_validity",
    ]);
  });

  it("uses the six flat-contract correction paths", () => {
    const accepted = [
      "company.name",
      "company.taxNumber",
      "company.mersisNumber",
      "representatives[rep-1].name",
      "representatives[rep-2].mode",
      "validUntil",
    ];
    const rejected = ["notary.name", "rules[0].threshold", "representatives[0].name"];
    accepted.forEach((path) => expect(CORRECTION_PATH_PATTERN.test(path)).toBe(true));
    rejected.forEach((path) => expect(CORRECTION_PATH_PATTERN.test(path)).toBe(false));
  });

  it("accepts masked TCKNs only", () => {
    expect(PATTERNS.tcknMasked.test("123******01")).toBe(true);
    expect(PATTERNS.tcknMasked.test("12345678901")).toBe(false);
  });

  it("requires exactly nine lowercase-status checks", () => {
    const check = (id: string) => ({
      id,
      status: "green" as const,
      title: id,
      reason: "kontrol edildi",
      evidence: {},
    });
    const report = { verdict: "READY" as const, checks: CHECK_IDS.map(check) };
    expect(checkReportSchema.safeParse(report).success).toBe(true);
    expect(checkReportSchema.safeParse({ ...report, checks: report.checks.slice(0, 8) }).success).toBe(false);
    expect(checkReportSchema.safeParse({ ...report, generated_at: "2026-08-01T10:00:00Z" }).success).toBe(false);
  });

  it("enforces integer kuruş, rule references, and blocked-rule shape", () => {
    const base = {
      schema_version: "1.0" as const,
      document_id: "doc-1",
      company: {
        name: "ABC Teknoloji Limited Şirketi",
        taxNumber: "1234567890",
        mersisNumber: "0123456789000017",
        legalNameNormalized: "abc teknoloji",
      },
      notary: { name: null, date: null, yevmiye: null },
      validUntil: null,
      representatives: [
        {
          id: "rep-1",
          name: "Ali Yılmaz",
          nameNormalized: "ali yilmaz",
          nationalId: "123******01",
          title: "Müdür",
          mode: "SOLE" as const,
          coSigners: [],
          limits: 50_000_000,
        },
      ],
      fieldsNeedingReview: [],
      evidence: { authorityClause: "münferiden temsile yetkilidir", page: 1 },
      rules: [
        {
          scope: "real_estate",
          threshold: null,
          mode: null,
          coSigners: [],
          blocked: true,
          evidence: { page: 1, quote: "gayrimenkul işlemleri kapsam dışıdır" },
        },
      ],
    };
    expect(extractionResultSchema.safeParse(base).success).toBe(true);
    expect(
      extractionResultSchema.safeParse({
        ...base,
        representatives: [{ ...base.representatives[0], limits: 500_000.5 }],
      }).success,
    ).toBe(false);
    expect(
      extractionResultSchema.safeParse({
        ...base,
        rules: [{ ...base.rules[0], mode: "SOLE" }],
      }).success,
    ).toBe(false);
  });
});

describeDelivered("delivered ExtractionResult fixtures", extractions, () => {
  it.each(extractions)("$label validates", ({ body }) => {
    const parsed = extractionResultSchema.safeParse(body);
    expect(parsed.success ? null : parsed.error.format()).toBeNull();
  });
});

describeDelivered("delivered CheckReport fixtures", reports, () => {
  it.each(reports)("$label validates", ({ body }) => {
    const parsed = checkReportSchema.safeParse(body);
    expect(parsed.success ? null : parsed.error.format()).toBeNull();
  });
});

describe("registry seed", () => {
  it.skipIf(!existsSync(REGISTRY_SEED))("keeps the bank-owned envelope valid", () => {
    const registry = registrySchema.parse(JSON.parse(readFileSync(REGISTRY_SEED, "utf-8")));
    expect(registry.companies.length).toBeGreaterThan(0);
  });
});
