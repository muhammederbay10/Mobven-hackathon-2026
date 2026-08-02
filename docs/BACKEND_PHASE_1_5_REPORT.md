# YetkiCheck backend Phase 1-5 completion report

Date: 2026-08-01  
Implementation source of truth: `docs/fbdocs/IMPLEMENTATION_PLAN.md`  
AI wire source of truth: `docs/API_CONTRACT.md`

## Outcome

The bank backend now implements the Phase 1-5 application path from branch
intake through document analysis, reviewed approval, authority persistence,
mobile authorization, co-signing, registry revalidation, and history.

| Phase | Backend result |
|---|---|
| 1 | Attested application/document intake, rendering, stub/live/replay clients, cache, idempotent analysis, durable failure recovery, aggregate restore |
| 2 | Immutable raw extraction, ordered optimistic corrections, re-analysis, decision guards, override audit, atomic authority versioning, registry API |
| 3 | Strict live transport boundary, Turkish filename-safe multipart upload, timeout/unavailable/contract errors, replay/cache controls, recoverable retry path |
| 4 | Deterministic case fixture loading, four offline outcomes, case-4 registry patch reset, one-call reset, cache prewarm/clear, controlled conflict tests |
| 5 | Current-registry authority evaluation, integer-kuruş rules, sole/joint/blocked decisions, persisted attempts, unique codes, co-sign revalidation/idempotency, histories |

The bank backend does not recompute the nine onboarding checks. In stub mode it
selects validated `CheckReport` fixtures through a declarative catalog; live
mode sends the same flat extraction/application/registry request to AI
`POST /analyze`.

## Main implementation locations

- AI modes, strict HTTP, cache and offline catalog adapter:
  `api/services/ai_client.py`
- Analysis state/persistence/failure orchestration:
  `api/services/analysis_service.py`
- Effective extraction and append-only corrections:
  `api/services/extraction_service.py`, `api/services/correction_service.py`
- Approval and authority construction:
  `api/services/decision_service.py`, `api/services/authority_service.py`
- Current-registry authorization and co-signing:
  `api/services/transaction_service.py`
- Registry and audit:
  `api/services/registry_service.py`, `api/services/audit_service.py`
- HTTP surface:
  `api/routers/applications.py`, `registry.py`, `authority.py`,
  `transactions.py`, `audit.py`, `demo.py`
- New-contract fallback data:
  `data/fixtures/extractions/`, `data/fixtures/reports/`
- UTF-8 document sources and rendered assets:
  `data/documents/source/`, `data/documents/case1.pdf` through `case3.pdf`,
  `data/documents/pages/`
- Phase acceptance suite: `api/tests/test_backend_phases_1_5.py`

## Added backend endpoints

| Method | Path |
|---|---|
| POST | `/api/applications/{id}/analyze` |
| PATCH | `/api/applications/{id}/extraction` |
| POST | `/api/applications/{id}/decision` |
| GET | `/api/registry` |
| PUT | `/api/registry/{mersis}/reps/{rep_id}` |
| GET | `/api/authority/{mersis}` |
| GET | `/api/authority/{mersis}/history` |
| POST | `/api/transactions/authorize` |
| POST | `/api/transactions/{id}/cosign` |
| GET | `/api/transactions?mersis={mersis}` |
| GET | `/api/audit` |
| POST | `/api/demo/cache/prewarm` |
| POST | `/api/demo/cache/clear` |

Existing application, document, page, case-load and reset endpoints remain in
place.

## Contract and safety guarantees checked

- Raw AI extraction JSON is never mutated; effective values are projected from
  ordered correction rows.
- Correction paths are restricted to the frozen six-field allowlist and use
  optimistic `expected_old_value` checks.
- Approval rechecks branch identity, original-seen attestation, latest report,
  unresolved review fields, document identifiers, and the current registry.
- Red onboarding verdicts cannot be approved. `CO_SIGNER_REQUIRED` needs an
  explicit override justification and audit row.
- Approved persons resolve to stable registry IDs; rules are copied from the
  reviewed extraction without broadening.
- Every authorization with an authority record is persisted and audited.
  Amounts and thresholds are integer kuruş with currency fixed to TRY.
- Registry state is reread on every authorization and co-sign operation. A
  removed initiator or co-signer cannot use a still-active stored authority.
- Authorization codes are unique, generated only for `ALLOWED`, and reused on
  an idempotent repeated co-sign.
- Upload paths remain server-generated and contained under the configured data
  root; raw bytes and unmasked TCKNs do not enter logs or audit details.

## Test result

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest api/tests -q -p no:cacheprovider --basetemp .test-runtime\final
```

Completion result: **188 passed**. The five emitted warnings are third-party
PyMuPDF/SWIG deprecation warnings; there were no test failures or skips.

Frontend contract compatibility was also rechecked after the backend work:
TypeScript typecheck passed, ESLint passed, and all 13 Vitest contract tests
passed.

The Phase 1-5 acceptance tests cover:

- all four expected offline verdicts;
- timeout → `ANALYSIS_FAILED` → successful retry with no partial extraction;
- correction immutability and stale-write rejection;
- normal and override approvals plus authority supersession;
- sole general authorization, high-value joint authorization, credit co-sign,
  explicit real-estate denial, and post-approval registry removal;
- self-sign, wrong-signer, removed-signer, and repeated-cosign behavior;
- demo reset/cache controls and controlled missing-document/wrong-state errors.

## Items to recheck with external/live dependencies

1. AI `POST /extract` is still marked unavailable by the AI-owned contract.
   The backend live transport and failure path are ready, but set
   `AI_EXTRACT_AVAILABLE=true` only after a real response passes the same
   `ExtractionResult` validation.
2. Confirm the AI-owned golden fixtures against the full-stack fallback files
   under `data/fixtures/`; the backend prefers contract correctness and must not
   special-case a verdict if they differ.
3. Run one photographed/printed synthetic document through live extraction.
   Generating that physical capture is a manual rehearsal task.
4. The frozen `TransactionDecision.source` is non-null. When no authority has
   ever existed, the backend still persists a `DENIED` attempt but returns the
   controlled `AUTHORITY_NOT_FOUND` error containing its transaction ID rather
   than inventing a false authority source.
