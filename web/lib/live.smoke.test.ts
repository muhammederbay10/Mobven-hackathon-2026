/**
 * Live end-to-end smoke of the bank API through the web app's own API layer.
 *
 * Skipped unless LIVE_API=1 and a backend is running on
 * NEXT_PUBLIC_API_BASE_URL (default http://localhost:8000) with DEMO_MODE on.
 * Every response passes through the same strict Zod parsing the screens use,
 * so this is the contract-drift detector for the real wire, not a substitute
 * for the offline tests.
 *
 *   LIVE_API=1 npx vitest run lib/live.smoke.test.ts
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  ApiError,
  analyzeApplication,
  authorizeTransaction,
  correctExtraction,
  cosignTransaction,
  createApplication,
  decideApplication,
  getApplication,
  getAuditHistory,
  getAuthority,
  getAuthorityHistory,
  getRegistry,
  listTransactions,
  loadDemoCase,
  resetDemo,
  uploadDocument,
} from "./api";

const live = process.env.LIVE_API === "1";
const REPO_ROOT = resolve(__dirname, "..", "..");

function caseFile(name: string): File {
  // Node 20+ exposes the WHATWG File globally, matching the DOM typing the
  // API layer expects.
  const bytes = readFileSync(join(REPO_ROOT, "data", "documents", name));
  return new File([new Uint8Array(bytes)], name, { type: "application/pdf" });
}

describe.skipIf(!live)("live backend smoke (case 1 end to end)", () => {
  it(
    "runs onboarding, corrections, approval, transactions, co-sign and registry revocation",
    { timeout: 120_000 },
    async () => {
      await resetDemo();

      // --- Act 1: onboarding -------------------------------------------------
      const { application_id } = await loadDemoCase(1);
      let aggregate = await getApplication(application_id);
      expect(aggregate.application.status).toBe("IDENTITY_VERIFIED");
      expect(aggregate.document).toBeNull();

      const document = await uploadDocument(application_id, caseFile("case1.pdf"), {
        original_seen: true,
        scanned_by: "Şube görevlisi",
      });
      expect(document.page_count).toBeGreaterThanOrEqual(1);

      aggregate = await getApplication(application_id);
      expect(aggregate.application.status).toBe("DOCUMENT_SCANNED");

      aggregate = await analyzeApplication(application_id);
      expect(aggregate.application.status).toBe("ANALYZED");
      expect(aggregate.report?.verdict).toBe("READY");
      expect(aggregate.report?.checks).toHaveLength(9);
      const extraction = aggregate.extraction;
      expect(extraction).not.toBeNull();
      if (!extraction) throw new Error("unreachable");

      // --- corrections: stale guard then a real write ------------------------
      const rep = extraction.representatives[0];
      if (!rep) throw new Error("fixture has no representatives");

      const stale = await correctExtraction(application_id, {
        reason: "Bilinçli eski değerle deneme.",
        corrections: [
          {
            field_path: `representatives[${rep.id}].name`,
            expected_old_value: "kesinlikle-eski-olmayan-değer",
            new_value: rep.name,
          },
        ],
      }).catch((error: unknown) => error);
      expect(stale).toBeInstanceOf(ApiError);
      expect((stale as ApiError).code).toBe("STALE_CORRECTION");

      aggregate = await correctExtraction(application_id, {
        reason: "Noter belgesiyle tekrar kontrol edildi.",
        corrections: [
          {
            field_path: `representatives[${rep.id}].name`,
            expected_old_value: rep.name,
            new_value: rep.name,
          },
        ],
      });
      expect(aggregate.corrections.length).toBeGreaterThanOrEqual(1);
      expect(["ANALYZED", "ANALYZING"]).toContain(aggregate.application.status);
      if (aggregate.application.status === "ANALYZING") {
        // conservative refetch, mirroring the screen's poll
        for (let i = 0; i < 20 && aggregate.application.status === "ANALYZING"; i += 1) {
          await new Promise((resolveSleep) => setTimeout(resolveSleep, 500));
          aggregate = await getApplication(application_id);
        }
      }
      expect(aggregate.application.status).toBe("ANALYZED");

      // --- approval hinge ----------------------------------------------------
      aggregate = await decideApplication(application_id, { action: "approve" });
      expect(aggregate.application.status).toBe("APPROVED");
      expect(aggregate.authority).not.toBeNull();
      const authorityFromAggregate = aggregate.authority;
      if (!authorityFromAggregate) throw new Error("unreachable");
      const mersis = aggregate.application.mersis;

      const authority = await getAuthority(mersis);
      expect(authority.id).toBe(authorityFromAggregate.id);
      expect(authority.persons.length).toBeGreaterThanOrEqual(1);

      const history = await getAuthorityHistory(mersis);
      expect(history.items.map((item) => item.id)).toContain(authority.id);

      const audit = await getAuditHistory({
        entity_type: "AUTHORITY_RECORD",
        entity_id: String(authority.id),
      });
      expect(audit.items.length).toBeGreaterThanOrEqual(1);

      // --- Act 2: transactions ----------------------------------------------
      const initiator = authority.persons[0];
      if (!initiator) throw new Error("authority has no persons");

      const allowed = await authorizeTransaction({
        mersis,
        subject: "GENERAL",
        currency: "TRY",
        amount_minor: 25_000_000,
        initiator: initiator.id,
      });
      expect(allowed.verdict).toBe("ALLOWED");
      expect(allowed.authorization_code).toMatch(/^YTK-/);

      const pending = await authorizeTransaction({
        mersis,
        subject: "GENERAL",
        currency: "TRY",
        amount_minor: 120_000_000,
        initiator: initiator.id,
      });
      expect(pending.verdict).toBe("PENDING_COSIGN");
      expect(pending.required_cosigner).toBeTruthy();
      const cosigner = pending.required_cosigner;
      if (!cosigner) throw new Error("unreachable");

      const wrongCosigner = await cosignTransaction(pending.transaction_id, {
        cosigner: initiator.id,
      }).catch((error: unknown) => error);
      expect(wrongCosigner).toBeInstanceOf(ApiError);
      expect((wrongCosigner as ApiError).code).toBe("COSIGN_NOT_ALLOWED");

      const cosigned = await cosignTransaction(pending.transaction_id, { cosigner });
      expect(cosigned.verdict).toBe("ALLOWED");
      expect(cosigned.authorization_code).toMatch(/^YTK-/);

      const cosignedAgain = await cosignTransaction(pending.transaction_id, { cosigner });
      expect(cosignedAgain.authorization_code).toBe(cosigned.authorization_code);

      const denied = await authorizeTransaction({
        mersis,
        subject: "REAL_ESTATE",
        currency: "TRY",
        amount_minor: 0,
        initiator: initiator.id,
      });
      expect(denied.verdict).toBe("DENIED");
      expect(denied.authorization_code).toBeNull();

      // --- registry revocation flips the next backend decision ---------------
      const registry = await getRegistry();
      const company = registry.companies.find((entry) => entry.mersis === mersis);
      expect(company).toBeDefined();
      const registryRep = company?.representatives.find((entry) => entry.id === initiator.id);
      expect(registryRep).toBeDefined();
      if (!registryRep) throw new Error("unreachable");

      const updated = await updateRep(mersis, registryRep.id, "REMOVED");
      expect(
        updated.representatives.find((entry) => entry.id === registryRep.id)?.status,
      ).toBe("REMOVED");

      const deniedAfterRemoval = await authorizeTransaction({
        mersis,
        subject: "GENERAL",
        currency: "TRY",
        amount_minor: 25_000_000,
        initiator: initiator.id,
      });
      expect(deniedAfterRemoval.verdict).toBe("DENIED");

      // stored authority record remains unchanged
      const authorityAfter = await getAuthority(mersis);
      expect(authorityAfter.status).toBe("ACTIVE");
      expect(authorityAfter.version).toBe(authority.version);

      await updateRep(mersis, registryRep.id, "ACTIVE");

      const transactions = await listTransactions(mersis);
      expect(transactions.length).toBeGreaterThanOrEqual(4);

      // --- validation error carries field details ----------------------------
      const invalid = await createApplication({
        company_name: "X",
        tax_number: "123",
        mersis: "0123456789000017",
        applicant_name: "Ali",
        applicant_tckn_masked: "123******01",
        branch_code: "kozyatagi01",
        identity_verified_at_branch: true,
      }).catch((error: unknown) => error);
      expect(invalid).toBeInstanceOf(ApiError);
      expect((invalid as ApiError).code).toBe("VALIDATION_ERROR");

      await resetDemo();
    },
  );
});

async function updateRep(mersis: string, repId: string, status: "ACTIVE" | "REMOVED") {
  const { updateRegistryRepresentative } = await import("./api");
  return updateRegistryRepresentative(mersis, repId, { status });
}
