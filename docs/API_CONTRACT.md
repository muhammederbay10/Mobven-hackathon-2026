# API Contract — AI Service (`ai/`, port 8001)

This is the authoritative reference for what the AI service accepts and returns. It is derived
directly from `ai/schema.py` and `ai/main.py` — if this document and the code ever disagree,
**the code wins**; open a PR against this file to fix the drift.

Governing documents, in conflict order: `docs/PLAN.md` §1.1 (the original frozen shape) >
`docs/PLAN_ALIGNMENT.md` (conflict resolutions) > this file (the implemented, current detail) >
`AI_BACKEND_PLAN.md` (background reasoning).

Status legend: **implemented** = exists in `ai/main.py` today. **planned** = shape is frozen in
`ai/schema.py` but no endpoint serves it yet (tracked as an AI-pipeline ticket).

---

## 1. `GET /health` — implemented

No request body.

```json
{
  "status": "ok",
  "engine": "gpt-5.6-luna",
  "schema_version": "1.0"
}
```

`engine` echoes `EXTRACTION_MODEL` from `ai/.env`; `"unconfigured"` if the variable is unset.
Never exposes `OPENAI_API_KEY` or any other credential.

---

## 2. `POST /analyze` — implemented

Deterministic comparison of an extracted circular against a branch application and the mock
registry. **No model call anywhere in this path** — `ai/compare.py` is pure Python.

### Request body — `AnalyzeRequest`

```json
{
  "extraction": { "...": "an ExtractionResult, see section 3" },
  "application": {
    "company_name": "ABC Teknoloji Ltd. Şti.",
    "tax_number": "1234567890",
    "mersis": "0123456789000017",
    "applicant_name": "Ali Yılmaz",
    "applicant_tckn": "123******01",
    "branch_code": "0341",
    "identity_verified_at_branch": true
  },
  "registry": {
    "0123456789000017": {
      "name": "ABC Teknoloji Ltd. Şti.",
      "status": "ACTIVE",
      "reps": [
        {"name": "Ali Yılmaz", "tckn": "123******01", "mode": "SOLE", "status": "ACTIVE"}
      ]
    }
  },
  "as_of": "2026-08-01"
}
```

- `registry` is keyed by MERSİS number, exactly as `data/registry.json` is shaped — the backend
  can pass that file's contents straight through.
- `application` and every entry under `registry` are **inbound-tolerant**: unknown fields are
  ignored, everything defaults to `None`/`"ACTIVE"`. This is deliberate — `api/` sends whole
  database rows, and the registry file gets hand-edited live on stage. A typo in a field nobody
  reads must never produce an HTTP error; it can only ever produce a **red check**, never a green
  one, because missing data is treated as unverified.
- `as_of` is optional; omit it to compare against today's date (used for `document_validity`).

### Response — `CheckReport`

```json
{
  "verdict": "READY",
  "checks": [
    {
      "id": "company_name_match",
      "status": "green",
      "title": "Şirket unvanı",
      "reason": "Başvurudaki unvan ile belgedeki unvan aynı şirketi gösteriyor.",
      "evidence": {"Başvuru": "ABC Teknoloji Ltd. Şti.", "Belge": "ABC Teknoloji Limited Şirketi"}
    }
  ]
}
```

`checks` always contains **all nine** IDs, always in this exact order (the frontend animates
them in this order, so the order is contract, not convention):

```
company_name_match → tax_number_match → mersis_number_match → applicant_in_document →
identity_match → authority_mode → registry_status → registry_representative_match →
document_validity
```

**`status`** is `green | amber | red`. Amber is reserved for `authority_mode` — it is the only
check whose amber maps to the `CO_SIGNER_REQUIRED` verdict. Every other check is green or red;
unreadable or unverifiable input goes red, never a soft amber. See coordination item
`CHECK-TITLES`: `title` is a stable noun-phrase label ("Şirket unvanı"), never a sentence — the
sentence lives in `reason`, because a sentence like "Şirket unvanı başvuruyla eşleşiyor" becomes
false the moment the row is red.

**`verdict`** priority, highest wins: `MISMATCH` > `REGISTRY_CONFLICT` > `CO_SIGNER_REQUIRED` >
`READY`.

**Degraded response, not an error.** A malformed body (bad date, wrong type, missing required
field) still returns **HTTP 200** with `verdict: "MISMATCH"` and all nine checks red, naming the
offending field path in the reason (e.g. `"Sorunlu alanlar: extraction.evidence, extraction.validUntil"`).
The review screen never loses its checklist to a 422, and the integration bug stays visible on
screen instead of being swallowed.

---

## 3. `ExtractionResult` — the flat contract

**Status: partially implemented.** The shape below is fully implemented in `ai/schema.py` and is
exactly what every `ai/tests/fixtures/case*.json` file is today. `AnalyzeRequest.extraction` above
is exactly this shape. **`POST /extract` itself — the endpoint that produces this from a real
uploaded document — is not yet implemented** (see §7 status table).

```json
{
  "schema_version": "1.0",
  "document_id": "doc_01",
  "company": {
    "name": "ABC Teknoloji Limited Şirketi",
    "taxNumber": "1234567890",
    "mersisNumber": "0123456789000017",
    "legalNameNormalized": "abc teknoloji"
  },
  "notary": {"name": "İstanbul 18. Noterliği", "date": "2026-03-15", "yevmiye": "08912"},
  "validUntil": "2028-03-15",
  "representatives": [
    {
      "id": "rep-1",
      "name": "Ali Yılmaz",
      "nameNormalized": "ali yilmaz",
      "nationalId": "123******01",
      "title": "Müdür",
      "mode": "SOLE",
      "coSigners": [],
      "limits": 50000000
    },
    {
      "id": "rep-2",
      "name": "Ayşe Demir",
      "nameNormalized": "ayse demir",
      "nationalId": "456******23",
      "title": "Müdür",
      "mode": "JOINT",
      "coSigners": ["Ali Yılmaz"],
      "limits": null
    }
  ],
  "fieldsNeedingReview": [],
  "evidence": {"authorityClause": "verbatim Turkish quote", "page": 1},
  "rules": [
    {
      "scope": "general",
      "threshold": 50000000,
      "mode": "SOLE",
      "coSigners": [],
      "blocked": false,
      "evidence": {"page": 1, "quote": "verbatim Turkish quote"}
    },
    {
      "scope": "general",
      "threshold": null,
      "mode": "JOINT",
      "coSigners": ["rep-1", "rep-2"],
      "blocked": false,
      "evidence": {"page": 1, "quote": "verbatim Turkish quote for the joint-signature clause"}
    },
    {
      "scope": "real_estate",
      "threshold": null,
      "mode": null,
      "coSigners": [],
      "blocked": true,
      "evidence": {"page": 1, "quote": "verbatim Turkish quote excluding real estate from this circular"}
    }
  ]
}
```

### Field notes

| Field | Notes |
|---|---|
| `company.name` / `representatives[].name` | **Printed value.** Authoritative for display, evidence, and audit. Exactly as the document says. |
| `company.legalNameNormalized` / `representatives[].nameNormalized` | **Derived, non-authoritative, recomputable.** Populated automatically by a Pydantic validator from `ai/turkish.py` at model-construction time — they cannot drift from the printed value because they're computed from it, not supplied separately. **Consumers must compare people and companies on the normalized field, never the printed one** — `'ALİ YILMAZ' != 'Ali Yılmaz'` under plain Python string equality (İ lowercases to `i` + a combining mark). |
| `notary.yevmiye` | The notary's journal number for the notarization. |
| `representatives[].id` | **Implemented.** Stable source identifier (`rep-1`, `rep-2`, ...) assigned by document order — a join key that survives a name correction. Required, non-empty. |
| `representatives[].mode` | `SOLE` (münferiden) or `JOINT` (müştereken). |
| `representatives[].coSigners` | **Names**, not IDs — this field is read by `ai/compare.py` to print a human-readable Turkish check reason ("Ali tek başına imzalayamaz; Ayşe Demir ile…"), so it stays display text. May include a person not otherwise listed (an external reference). Never drop an unresolved name. |
| `representatives[].limits` | **Integer kuruş** (1 TL = 100 kuruş), e.g. `50000000` for ₺500,000.00. `null` = unlimited or not applicable. Never a float. |
| `fieldsNeedingReview` | Field paths the extractor could not read confidently. A downstream check whose evidence touches one of these paths should surface uncertainty, not accuse the customer of a mismatch. |
| `evidence.authorityClause` | Verbatim Turkish, never paraphrased or translated. The review screen's highlight layer searches the page text for this exact string — if it doesn't match character-for-character, nothing highlights. |
| `rules[]` | **Implemented.** Flat per-rule projection so the demo's claim "the limits in the circular are live banking rules" is literally true. |
| `rules[].threshold` | **Integer kuruş**, same unit as `limits`. `null` = unbounded within this scope. |
| `rules[].coSigners` | **Representative `id`s** (e.g. `"rep-2"`), NOT names — the opposite convention from `representatives[].coSigners` above, and deliberately so: a rule is machine-consumed by the authority engine, which must resolve signers by stable ID, not by a Turkish-casing-sensitive name string. Every ID must resolve to a representative in the same `ExtractionResult`, or the whole result fails validation. |
| `rules[].blocked` / `rules[].mode` | **Implemented.** `blocked: true` represents a scope the circular explicitly excludes (e.g. real estate, which by law requires a separate board decision) — no one may act on it under this document at all. A blocked rule always carries `mode: null` and empty `coSigners`; a non-blocked rule always requires a `mode`. The exclusion clause is still real evidence and must not be silently dropped. |
| `nationalId` | Masked format only: `^\d{3}\*{6}\d{2}$`, e.g. `123******01`. Six hidden digits — a match corroborates a name match and must never substitute for one. |

---

## 4. `CircularExtraction` — internal only, never sent over HTTP

The rich model the pipeline builds internally before projecting down to `ExtractionResult`
(`ai/schema.py`, not part of any wire contract). Listed here only so a consumer understands what
information exists but is intentionally not exposed flat: per-signatory `valid_from`/`valid_until`
and `group_code`, `AuthorityRule` with `amount_min`/`amount_max` ranges and a `confidence` level,
`DocumentReference` (the cross-document chain — board resolution, iç yönerge, gazette),
`ProvenanceFlag` (checksum failures, unresolved references, model disagreement — annotation only,
never gates or blocks anything), and `PageMap` (the Sorter's per-page classification).

---

## 5. Enumerations (all closed sets — reject anything else)

```
SignatureMode        SOLE | JOINT
CheckStatus           green | amber | red
CheckVerdict          READY | CO_SIGNER_REQUIRED | MISMATCH | REGISTRY_CONFLICT
CheckId (ordered)     company_name_match, tax_number_match, mersis_number_match,
                      applicant_in_document, identity_match, authority_mode,
                      registry_status, registry_representative_match, document_validity
PageLabel             identity_header, dayanak, appointments, rules, specimens, notary_block,
                      ic_yonerge_annex, board_resolution_annex, gazette_annex,
                      imza_beyannamesi, cover_or_blank, other_unknown
```

---

## 6. Consumer checklist

- Compare people and companies on the `*Normalized` fields, never the printed ones
  (`NAME-NORMALIZATION`).
- Render `title` as a static label; put the verdict-dependent sentence in `reason`
  (`CHECK-TITLES`).
- Treat a 200 response with all-red checks as a real signal (bad input), not success —
  check `verdict` before treating a response as "done."
- Case 4's registry patch must produce exactly: MERSİS `0123456789000017` stays `ACTIVE`,
  representative `Ali Yılmaz` (`123******01`) flips to `REMOVED`, nothing else changes
  (`CASE4-REGISTRY`).
- Real people's data (names, TCKN, signatures) from `extraction-spike/` internal test documents
  must never reach this API in a demo context — only the four synthetic cases in `data/documents/`.

See `docs/AI_PIPELINE_TICKETS.yaml` → `known_coordination_items` for the live status of each item
referenced above.

---

## 7. Status of the six requested contract items

| # | Item | Status |
|---|---|---|
| 1 | Money as integer kuruş (`representatives[].limits`, `rules[].threshold`, internal `AuthorityRule.amount_min/max`) | ✅ **Done.** Schema fields are `int`, tested to reject floats. All four fixtures use kuruş. |
| 2 | Representatives get stable IDs (`rep-1`, `rep-2`) | ✅ **Done.** `Representative.id`, required, assigned by document order. All four fixtures updated. |
| 3 | Rules reference those IDs | ✅ **Done.** `ExtractionRule.coSigners` now holds representative IDs, not names; a cross-field validator on `ExtractionResult` rejects any ID that doesn't resolve to a representative in the same result. All four fixtures updated. |
| 4 | Explicit blocked real-estate rule | ✅ **Done.** `ExtractionRule.blocked: bool` + a validator enforcing `blocked ⇒ mode: null, coSigners: []`. Added to all four fixtures (every demo document's own text explicitly excludes real estate — case1/2/3/4 all quote it). |
| 5 | Implement `POST /extract` | ❌ **Not implemented.** Only `GET /health` and `POST /analyze` exist in `ai/main.py`. The extraction pipeline (render → sort → chunk → extract → normalize → validate → project) has a Sorter (`ai/sorter.py`) but no chunker, extraction agents, normalizer, validator, or orchestrator wiring it to an endpoint. This is a substantially larger task than the other five items — treat as its own piece of work. |
| 6 | Deliver extraction and report fixtures | ✅ **Done, mechanically** — four `case{n}.json` (`ExtractionResult`) + four `case{n}-report.json` (`CheckReport`, generated by running `analyze()`, never hand-typed) exist, pass schema validation, and are cross-checked against a live `analyze()` run by `ai/scripts/check_fixtures.py` on every run. **Caveat:** these fixtures still use our own placeholder identities/case-3 scenario, not the corrected fixed-cast TCKNs or the "applicant claims to be ABC Teknoloji" case-3 scenario from his fuller spec — that content question is still open (see prior turn) and would require regenerating the fixtures again if confirmed. |

Everything above is verified by `pytest ai/tests` (199 passing) and `python ai/scripts/check_fixtures.py`
(all four fixtures valid, report fixtures match a live `analyze()` run).
