# Contract freeze — Phase 0, shared architecture step 3

**Status:** frozen for the full-stack track, pending the AI engineer's H4 delivery of `ai/schema.py`.
**Authoritative source:** `docs/fbdocs/IMPLEMENTATION_PLAN.md` section 5, plus the closed decision register in section 1.5.
**Machine-checked by:** `api/tests/test_contract_freeze.py` and `web/lib/contracts.test.ts`.

This document records *what* was frozen and *why*. The frozen values themselves live in code, in exactly two mirrors:

| Mirror | File |
|---|---|
| Python | `api/schemas.py` |
| TypeScript (types) | `web/lib/types.ts` |
| TypeScript (runtime validation) | `web/lib/contracts.ts` |

`ai/schema.py` is the source contract and is owned by the AI engineer. The two files above mirror its JSON; they never replace it. A contract change is coordinated with the AI engineer, who updates the AI-owned file **first** (plan sections 5 and 18.11).

---

## How the freeze is enforced

Three independent guards, all runnable offline:

1. **Value guards** — `api/tests/test_contract_freeze.py` spells out every enum member, every check ID, every correction path and every identifier pattern. Section 18 forbids an agent from *silently* renaming an enum value; these tests are what makes "silently" impossible.
2. **Mirror parity** — the same test asserts every Python enum literal, check ID and correction path also appears in `web/lib/types.ts`.
3. **Type-level drift guard** — `web/lib/contracts.ts` asserts each zod schema and its hand-written twin in `types.ts` are *mutually* assignable. If they stop agreeing, `npm run typecheck` fails. (Verified non-vacuous: a deliberately mismatched pair does produce `TS2322`.)

---

## 1. Enums

Every enum below is closed. Members may be **added** to `ErrorCode` only; nothing may be renamed or removed anywhere.

| Enum | Members | Source |
|---|---|---|
| `Confidence` | `HIGH` `MEDIUM` `LOW` | §5.1 |
| `ReviewFlag.severity` | `INFO` `WARNING` `ERROR` | §5.1 |
| `AuthorityMode` | `SOLE` `JOINT` `LIMITED` `UNKNOWN` | §5.2 |
| `TransactionSubject` | `GENERAL` `CREDIT` `REAL_ESTATE` | §5.2 |
| `CheckStatus` | `GREEN` `AMBER` `RED` | §5.3 |
| `OnboardingVerdict` | `READY` `CO_SIGNER_REQUIRED` `MISMATCH` `REGISTRY_CONFLICT` | §5.3 |
| `CheckResult.source_kind` | `APPLICATION` `IDENTITY` `DOCUMENT` `REGISTRY` | §5.3 |
| `TransactionVerdict` | `ALLOWED` `PENDING_COSIGN` `DENIED` | §5.5 |
| `ApplicationStatus` | 9 members | §7.1 |
| `TransactionStatus` | `REQUESTED` `ALLOWED` `PENDING_COSIGN` `DENIED` | §7.3 |
| `AuthorityRecordView.status` | `ACTIVE` `SUSPENDED` | §5.6 |
| `RegistryCompany.status` | `ACTIVE` `INACTIVE` | §5.4 |
| registry representative `status` | `ACTIVE` `REMOVED` | §5.4 |
| decision `action` | `approve` `request_document` `escalate` | §8.7 |

State machines (`APPLICATION_TRANSITIONS`, `TRANSACTION_TRANSITIONS`) and the GAP-07 approval matrix (`APPROVABLE_VERDICTS`, `VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION`) are frozen in the same module and asserted transition by transition.

## 2. The nine checks

`CHECK_IDS` is a nine-element ordered tuple (§6). `CheckReport` **rejects** a report whose `checks` are not exactly those nine IDs in that order, and rejects a `blocking_check_ids` entry that is not one of them.

This is a *structural* guard, not a second comparison engine. GAP-02 puts the comparison engine in `ai/compare.py` and §6 forbids the bank API from re-deriving statuses or the verdict. The one place §6.1 precedence is expressed on this side is `api/tests/test_ai_fixture_contracts.py`, as a defect detector on delivered fixtures — no runtime code path imports it.

## 3. JSON field names

Mirrored verbatim from §5, `snake_case` throughout, including on the wire. No field is renamed, aliased or camel-cased at any boundary. Every contract model sets `extra="forbid"` / zod `.strict()`: on an AI-delivered payload an unknown key is drift, and §8.8 requires drift to be reported as a contract defect rather than silently absorbed. §15 defines the runtime consequence — store no partial extraction/report, return a retryable integration error.

## 4. Evidence format

`EvidenceRef` is `{ page (1-based, ≥1), quote (verbatim, non-empty), bbox? ([x1,y1,x2,y2] normalized) }`.

§5.1 requires every non-null document-derived legal fact to carry at least one evidence item, and unknown content to be `null` plus a review flag. That rule is asserted against delivered fixtures in the contract tests rather than enforced in the schema, deliberately: a thin-evidence payload should surface as a defect report at H4, not as a crash mid-analysis on stage.

## 5. Error format

Every non-2xx response is `{ "error": { code, message, retryable, details, correlation_id } }` (§5.7). `message` is user-facing Turkish. No stack traces, raw model responses, local paths or secrets — ever (§5.7, §14).

`ErrorCode` is frozen by addition only. `DOCUMENT_REQUIRED`, `INVALID_STATE_TRANSITION` and `STALE_CORRECTION` are named directly in the plan; the rest are `[FROZEN-HERE]` to make the failure modes in §8, §14 and §15 individually distinguishable.

## 6. Date format

| Kind | Format | Example |
|---|---|---|
| Calendar date | `YYYY-MM-DD` | `2027-03-15` |
| Instant | ISO-8601 UTC, literal `Z` | `2026-08-01T10:00:00Z` |

All calendar dates (`valid_from`, `valid_until`, `document_valid_until`, `notary.date`, `effective_at`) and all instants (`generated_at`, `verified_at`) match these patterns. Turkish display formatting (`01.08.2026`) happens only at the UI edge.

> **Open with the AI engineer at H4.** Phase 3 backend step 2 names date formats as a known integration seam. The schema is strict here on purpose: if the delivered extraction returns `15.03.2027`, that surfaces as a contract defect at fixture-validation time rather than as a silent mis-parse on stage.

## 7. Identifier formats

| Identifier | Pattern | Source |
|---|---|---|
| `tax_number` | `^\d{10}$` | §8.7 |
| `mersis` | `^\d{16}$` | §8.7 |
| masked TCKN | `^\d{3}\*{6}\d{2}$` | GAP-08 |
| registry representative ID | `^rep_[a-z0-9_]+$` | GAP-09 |
| extraction `source_id` | `^[a-z][a-z0-9_-]{0,63}$` | `[FROZEN-HERE]` |
| document SHA-256 | `^[0-9a-f]{64}$` | §7.1 |
| authorization code | `^YTK-[0-9A-HJ-KMNP-TV-Z]{8}$` | `[FROZEN-HERE]` |
| branch audit actor | `branch_user:kozyatagi01` (constant) | GAP-08, §14 |

Notes on the two `[FROZEN-HERE]` choices:

- **`source_id` must start with a letter.** §8.7 requires a correction path to address a representative by its immutable source ID and "never an array position". With a digit permitted in first position, `representatives[0].name.value` is syntactically indistinguishable from a source-ID reference — the frontend contract test caught exactly this. Requiring a leading letter closes the ambiguity structurally. The pattern stays wider than the agreed `rep-N` convention so that a convention breach is a reportable defect rather than a mid-demo crash; the convention itself is asserted separately.
- **Authorization codes** are bank-API owned, not an AI contract. The alphabet omits `I`, `L`, `O` and `U` so a projected code cannot be misread from the stage.

Masked TCKNs are the **only** accepted form. A plausible unmasked 11-digit value is rejected by the pattern, by the fixture privacy test, and by §14.

## 8. Money

Integer minor units (kuruş) everywhere — code, API and database (GAP-12). Field name `amount_minor`, currency fixed to `TRY`, SQLite `INTEGER`. 500,000 TL is `50000000`. Values are bounded to the JS safe-integer range so the number survives JSON round-trips intact. No floating-point money is permitted anywhere; formatting happens only at the UI edge via `Intl.NumberFormat('tr-TR', {style:'currency', currency:'TRY'})`.

## 9. Correction paths

Exactly six, allowlisted server-side (§8.7 and GAP-06):

```
company.legal_name.value
company.tax_number.value
company.mersis.value
representatives[<source_id>].name.value
representatives[<source_id>].authority_mode.value
document_valid_until.value
```

`<source_id>` resolves against the immutable representative source ID — never an array position, never a display name. Anything else is `CORRECTION_PATH_NOT_ALLOWED`. `expected_old_value` is an optimistic-concurrency guard; a drifted value is `409 STALE_CORRECTION`.

---

## Changing anything here

1. Raise it with the AI engineer if it touches `/extract` or `/analyze`.
2. The AI engineer updates `ai/schema.py` (and fixtures) first.
3. Update `api/schemas.py`, `web/lib/types.ts` and `web/lib/contracts.ts` together.
4. Update this document and the affected phase acceptance criteria.
5. Re-run `python -m pytest api/tests` and `npm run typecheck && npm run test`.

After H4 neither engineer changes contracts or fixtures alone (plan GAP-10).
