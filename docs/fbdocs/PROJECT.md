# YetkiCheck — project document and full-stack implementation plan

**Hackathon:** 48 hours · Finance & Enterprise
**Team:** 1 full-stack engineer · 1 AI engineer
**Reference UI:** `index.html` (clickable mock) · **Team plan:** `PLAN.md`
**This document:** the complete project rationale, plus the full-stack engineer's implementation plan for backend and frontend.

---

# Part 1 — The project

## 1.1 Purpose

Turn the imza sirküsü — the notarized signature circular that decides who may legally act for a company — from a stack of paper that a bank employee reads by hand into **structured, machine-checkable authority data**, verified once at the branch and then enforced automatically on every operation the company performs afterwards.

One sentence for the jury:

> The signature circular is verified once, in person, at the branch — and from then on every transaction the company makes on its phone is checked against that stored authority in milliseconds.

## 1.2 The problem

### What the document is

An imza sirküsü is a notarized document that answers one question: **who may sign on behalf of this company, and how?** It states the company's identity, the legal basis of the appointment (board or partners' resolution, its notarization, the trade-registry gazette), the authorized people, and — crucially — the *form* of their authority: alone (münferiden) or jointly (müştereken), sometimes with monetary tiers, degree groups, and subject-based carve-outs (credit, real estate, litigation, HR).

It is written in dense legal Turkish, has no fixed layout, runs from two to ten-plus pages, and often arrives with annexes bound in: the internal directive, a copy of the board resolution, a trade-registry gazette page.

### What happens today

A company representative walks into a branch to open a corporate account, take a loan, or update authority. A branch employee then, by hand:

1. reads the whole document,
2. finds the authorized people and works out whether they sign alone or jointly,
3. cross-checks the company name, tax number, and MERSİS number against the application form,
4. checks that the person standing in front of them is one of the named representatives,
5. decides whether the bank can proceed.

This takes **10–20 minutes per application** and depends entirely on one tired person's attention on a busy afternoon.

### The four failure modes

| # | Failure | Cost |
|---|---|---|
| 1 | **Valid customer delayed or wrongly rejected** — the employee misreads a clause or can't decide, so the application is escalated or the customer is sent away | lost customer, branch time |
| 2 | **Invalid application accepted** — the document doesn't actually cover this person or this company, but it looks fine | legally void transactions, loss, liability |
| 3 | **Joint authority missed** — the document requires two signatures and only one is taken | the bank's transaction is unenforceable |
| 4 | **Stale document** — the paper is genuine, but the person named in it was removed from the company after notarization | the bank acts on authority that no longer exists |

Failure 4 is the important one: **no amount of careful reading can catch it.** The document is correct; it simply is no longer true. Catching it requires comparing the document against the current registry — which is a data problem, not a reading problem.

### And it repeats forever

Onboarding is only the first occurrence. Every later high-value operation — a large transfer, a credit drawdown, a pledge — raises the same question again, and today it is answered by a human re-reading the same document. The company is asked for its papers over and over; the bank pays the same 15 minutes over and over.

### Why nobody has solved it

- The text is legal Turkish with no schema — regex and classic OCR templates fail on it.
- The meaning is in the *language*: "münferiden" versus "müştereken … herhangi ikisinin", "…tarihine kadar", "iç yönergede belirtilen sınırlar dâhilinde".
- The decisive check needs data the document doesn't contain — the application form, the verified identity, the current registry — so a general document-AI tool cannot do it.
- Turkish banking data cannot be shipped to a third-party SaaS (BDDK localization, KVKK), so the solution has to be deployable inside the bank.

## 1.3 The solution

Two acts, one system.

### Act 1 — Verified once, at the branch

The notarized original must be physically seen — that is the law, and it's the reason first contact happens at a branch, not through an app. The employee verifies the customer's identity face to face, scans the document, and the system:

1. **Reads it** — OCR plus a vision-language model extracts structured data: company identity, representatives, authority form, co-signers, validity dates, limits, notary metadata. Every extracted fact carries the verbatim sentence it came from.
2. **Compares it** — deterministic code checks the extraction against three sources:
   - the application form the employee entered,
   - the identity verified in person,
   - the current registry (MERSİS — simulated in the prototype).
3. **Explains it** — the employee sees the document on one side and, on the other, the extracted fields plus nine checks resolving green, amber, or red, each with a reason and the evidence pair behind it. Then one of four verdicts: ready, co-signer required, mismatch, registry conflict.

The employee approves, corrects a field, requests a new document, or escalates. **The system pre-checks; the human decides.**

### Act 2 — Enforced forever, on the phone

Approval converts the reading into an **authority record**: people, degrees, monetary limits, subject scope, validity, and a pointer to the source document. From then on the document is never requested again. Every operation the company starts on mobile banking is checked against that record in milliseconds:

- within the single-signature limit → approved instantly, with a digital authorization code and an audit entry;
- over the limit or subject-restricted (credit) → second signature requested, pushed to the co-signer's phone;
- outside the scope entirely (real estate) → refused, with the reason and the next step;
- and the registry is re-checked on **every** transaction, so authority that lapses stops working immediately rather than living on in a cache.

### Why this is a product and not a demo

Extraction alone is a wrapper — anyone can prompt a model to summarize a PDF. The product is everything around it:

- the **comparison engine**, which uses data the model cannot see;
- the **authority record**, which turns one reading into permanent infrastructure;
- the **enforcement layer**, which makes limits in a notarized document into live banking rules;
- the **audit trail**, which is what a regulated bank actually buys.

Concretely: ask ChatGPT to read the case-4 document and it will tell you Ali may sign. Our system says he may not — and it is right.

## 1.4 What is real and what is simulated

| Real (runs live in the demo) | Simulated (labelled in the UI) |
|---|---|
| Document extraction by a vision model | MERSİS registry — local JSON service with an admin screen |
| The nine-check comparison engine | Identity verification — pre-filled "verified at branch" profile |
| Verdict logic and evidence | The bank's existing customer file |
| Authority record creation and enforcement | The four documents themselves (synthetic, fictional people) |
| Transaction decisions, co-signing, audit log | The mobile banking shell |

Stated plainly to the jury: *the reading, comparing, explaining, and enforcing all ran live; the registry and identity services are stand-ins for integrations the bank already owns.*

## 1.5 Value

| Stakeholder | What changes |
|---|---|
| Branch employee | 15 minutes of legal reading becomes a 30-second confirmation with the reasons shown |
| The bank | fewer void transactions, a stale-authority check that doesn't exist today, and a full audit trail per decision |
| The company | brings its papers once, then transacts digitally |
| Compliance | every authorization is traceable to a document, a clause, and a verified moment |

## 1.6 Out of scope (say this before a judge asks)

- **Signature-image matching** — deciding whether a handwritten signature belongs to a person is a biometric problem with its own legal weight. We read *who has authority*, not *whether this ink matches*.
- **Legal validity of the document itself** — we do not claim a document is authentic or notarized-verified; we extract notary metadata and say so.
- **Autonomous approval** — no path in the system approves a customer without a human.
- **Deep annex parsing** — annex types are classified and flagged, not fully parsed, in the 48-hour build.

---

# Part 2 — Full-stack implementation plan

## 2.1 Scope of this role

The full-stack engineer owns **everything except the AI service**:

```
web/     Next.js  :3000   all four screens
api/     FastAPI  :8000   storage, orchestration, authority, transactions, audit
data/    fixtures, documents, registry seed
```

The AI engineer owns `ai/` (:8001) and exposes exactly two endpoints. You call them; you never edit them.

**Working rule:** you must never be blocked waiting for the AI service. From hour 4 you develop against `AI_MODE=stub`, which returns the same fixtures the AI engineer's golden tests assert against. Switching to `live` in Phase 3 changes nothing in your code.

## 2.2 Architecture you own

```
Browser (Next.js)
   │  fetch, JSON only, all calls via web/lib/api.ts
   ▼
FastAPI :8000  ── SQLite (yetkicheck.db)
   │            └ data/registry.json  (runtime, hand-editable)
   │  HTTP, two endpoints
   ▼
FastAPI :8001  (AI — not yours)
```

Rules that keep this clean:

1. The frontend never calls :8001 directly.
2. All backend calls live in `web/lib/api.ts` — no `fetch` anywhere else.
3. Types live in `web/lib/types.ts`, mirroring `ai/schema.py`. They change in the same commit or not at all.
4. The backend persists everything it receives from the AI service verbatim, then serves it. It never re-derives extraction data.

## 2.3 Data model

```python
Application:      id, company_name, tax_number, mersis, applicant_name, applicant_tckn,
                  branch_code, identity_verified_at_branch: bool, status, created_at
Document:         id, application_id, path, sha256, page_count, original_seen: bool,
                  scanned_by, created_at
Extraction:       id, document_id, schema_version, engine, payload: JSON, created_at
CheckReport:      id, application_id, verdict, payload: JSON, created_at
AuthorityRecord:  id, mersis, source_document_id, source_application_id, verified_at,
                  valid_until, persons: JSON, rules: JSON, status  # ACTIVE | SUSPENDED
Transaction:      id, mersis, subject, amount, initiator, verdict, required_cosigner,
                  cosigned_by, cosigned_at, authorization_code, latency_ms, created_at
AuditLog:         id, ts, actor, action, entity, entity_id, detail: JSON
```

Registry stays outside the database, in `data/registry.json`, because it must be hand-editable live on stage.

### Application state machine

```
DRAFT ─(identity attested)→ IDENTITY_VERIFIED ─(scan + original seen)→ DOCUMENT_SCANNED
      ─(analyze)→ ANALYZED ─┬─(approve)→ APPROVED ──→ creates AuthorityRecord(ACTIVE)
                            ├─(request doc)→ DOC_REQUESTED
                            └─(escalate)→ ESCALATED
```

### Transaction state machine

```
REQUESTED ─┬→ ALLOWED (authorization_code issued)
           ├→ PENDING_COSIGN ─(cosign)→ ALLOWED
           └→ DENIED
```

Enforce the transitions in `api/services/` — never let the frontend decide a status.

## 2.4 API surface

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/demo/load-case/{n}` | — | `{application_id}` |
| POST | `/api/demo/reset` | — | `{ok}` |
| POST | `/api/applications` | company/applicant fields + `identity_verified_at_branch` | `Application` |
| POST | `/api/applications/{id}/document` | multipart + `original_seen` | `Document` |
| POST | `/api/applications/{id}/analyze` | — | `{extraction, report}` |
| GET | `/api/applications/{id}` | — | `{application, document, extraction, report, authority?}` |
| POST | `/api/applications/{id}/decision` | `{action, note?}` | `{status, authority_id?}` |
| GET | `/api/documents/{id}/page/{n}` | — | PNG |
| GET | `/api/registry` | — | full registry JSON |
| PUT | `/api/registry/{mersis}/rep/{name}` | `{status}` | updated company |
| GET | `/api/authority/{mersis}` | — | `AuthorityRecord` or 404 |
| POST | `/api/transactions/authorize` | `{mersis, subject, amount, initiator}` | `TransactionDecision` |
| POST | `/api/transactions/{id}/cosign` | `{cosigner}` | `TransactionDecision` |
| GET | `/api/transactions?mersis=` | — | list (audit table) |

Example — the response that drives the phone screen:

```json
{
  "transaction_id": 7,
  "verdict": "SECOND_SIGNATURE",
  "required_cosigner": "Ayşe Demir",
  "checks": [
    {"status": "green", "title": "Kişi yetki kaydında tanımlı",
     "reason": "Ali Yılmaz · 1. derece · kaynak: İmza sirküleri #IS-2041"},
    {"status": "amber", "title": "Tutar tek imza limitini aşıyor",
     "reason": "1.200.000 TL > 500.000 TL — ikinci imza gerekli."}
  ],
  "authorization_code": null,
  "latency_ms": 42,
  "source": {"document": "İmza sirküleri #IS-2041", "verified_at": "2026-03-15",
             "channel": "Şube — aslı görüldü"}
}
```

## 2.5 Frontend route map

| Route | Purpose | Components |
|---|---|---|
| `/` | demo control panel | `CaseCard`, `FlowStrip`, skip-to-act-2 button |
| `/branch` | act 1 — three-step intake then review | `Stepper`, `IntakeForm`, `AttestationBox`, `ScanPanel`, `ReviewScreen` |
| `/mobile` | act 2 — customer phone | `PhoneFrame`, `PhoneSwitcher`, `TxnList`, `DecisionCard`, `CosignCard`, `AuthStamp` |
| `/authority/[mersis]` | bank-side record + audit | `AuthorityCard`, `RulesTable`, `AuditTable` |
| `/registry` | mock registry admin | `RegistryTable`, `RepToggle` |

Shared: `VerdictBanner`, `CheckRow` (with expandable evidence), `FieldTable`, `StatusPill`, `SimBadge`, `DocumentViewer`.

`ReviewScreen` is the most valuable component in the codebase — it is on stage for most of the demo. Build it once, carefully, and reuse its `CheckRow` on the phone.

---

## Phase 0 — Foundations (H0–H4)

**Goal:** the repo exists, the contracts are frozen, and the four documents are rendered.

### Steps

1. `git init`; create `web/`, `api/`, `data/`; write `.gitignore` (`yetkicheck.db`, `data/registry.json`, `ai/cache/`, `web/.env.local`, `api/.env`, `node_modules/`, `.next/`, `__pycache__/`).
2. `npx create-next-app@latest web` (App Router, TypeScript, Tailwind). Copy the design tokens out of `index.html`: color variables, radii, the serif `.paper` styling, the phone frame.
3. `web/lib/types.ts` — hand-write `ExtractionResult`, `CheckReport`, `TransactionDecision`, `RegistryCompany` from the frozen contracts. Confirm field-by-field against `ai/schema.py` with the AI engineer, out loud.
4. FastAPI skeleton: `api/main.py`, CORS for `localhost:3000`, `/health`.
5. `api/models.py` — the seven SQLModel tables from §2.3. `api/db.py` with `create_all()`.
6. `data/seed_cases.json` (4 applications, which document each uses, the case-4 registry patch) and `data/registry.seed.json`.
7. `api/seed.py` — drop, recreate, load fixtures, copy `registry.seed.json` → `registry.json`. **Must run in under two seconds; you will run it fifty times this weekend.**
8. Render the AI engineer's four drafted circulars to PDF (HTML → print, Georgia/serif, justified, fake round seal), export page PNGs into `data/documents/`. Print and re-photograph case 1.
9. LAN test with the other laptop: `uvicorn main:app --host 0.0.0.0 --port 8000`, `ipconfig`, other machine opens `http://<ip>:8000/health`. If it fails, set up the hotspot or Tailscale fallback **now**.

### Done when
- [ ] `python -m api.seed` rebuilds the DB from scratch on both machines
- [ ] `types.ts` and `schema.py` agree field by field
- [ ] Four PDFs + page PNGs exist; one is a photograph
- [ ] Both machines can reach each other, or the fallback is configured

---

## Phase 1 — Walking skeleton (H4–H10)

**Goal:** the branch intake writes real rows, and analysis returns stub data end to end.

### Backend steps

1. `POST /api/applications` — validate, persist, status `IDENTITY_VERIFIED` when `identity_verified_at_branch` is true, audit row.
2. `POST /api/applications/{id}/document` — save file under `data/uploads/{app}/`, compute sha256, count pages, store `original_seen`, status → `DOCUMENT_SCANNED`.
3. `GET /api/documents/{id}/page/{n}` — serve the page PNG.
4. `services/ai_client.py` with the `AI_MODE` switch: `stub` reads `ai/tests/fixtures/case{n}.json`; `live` posts to `AI_URL`; `replay` reads the cache. One function, three branches, used everywhere.
5. `POST /api/applications/{id}/analyze` — load registry JSON → `ai_client.extract()` → `ai_client.analyze()` → persist `Extraction` + `CheckReport` → status `ANALYZED` → return both. Idempotent: calling twice must not duplicate rows.
6. `GET /api/applications/{id}` — the single aggregate the review screen needs.
7. `POST /api/demo/load-case/{n}` — reset demo rows, seed the application, attach the right document, apply the case-4 registry patch, return the new id.

### Frontend steps

1. `web/lib/api.ts` — typed wrappers for every endpoint; the only file with `fetch`.
2. `/` control panel: four `CaseCard`s → `load-case` → route to `/branch`; the flow strip; the "skip to act 2" rehearsal button.
3. `/branch` step 1 — `IntakeForm` with company/applicant fields and the `AttestationBox` ("Müşteri şubede, kimlik aslı ibraz edildi"). Continue disabled until ticked. Posts to `/api/applications`.
4. `/branch` step 2 — `ScanPanel`: scan button → progress bar → thumbnail → second attestation ("Belgenin aslı görüldü ve tarandı") → posts the file to `/document`, then calls `/analyze`.
5. `Stepper` component reflecting the three states, with a done-check on completed steps.

### Done when
- [ ] Loading case 1 from `/` lands on `/branch` with fields pre-filled
- [ ] Completing both steps writes `Application` + `Document` rows with both attestation flags true
- [ ] `/analyze` (stub) persists an extraction and a report

---

## Phase 2 — The review screen (H10–H16)

**Goal:** the hero screen is complete and correct on all four fixture cases.

### Frontend steps

1. Layout: `Stepper` → `VerdictBanner` slot at the **top** → split view, document left (440px) / results right.
2. `DocumentViewer` — page tabs, PNG display, and the highlight overlay for `evidence.authorityClause` on page 1.
3. `FieldTable` — extracted fields with a 160ms stagger; `fieldsNeedingReview` rendered as amber chips.
4. `CheckRow` — icon (green ✓ / amber ! / red ×), title, reason, and click-to-expand evidence pairs. Registry-sourced checks carry the `SimBadge`.
5. Sequencing: fields stagger first, then checks resolve one at a time at ~520ms, then the verdict banner drops in and the authority clause flashes. Total ≈15–20 seconds — it must feel like watching the system think, not like a page load.
6. `VerdictBanner` — four states (ready / co-signer / mismatch / registry conflict) with the right color and copy.
7. Action bar: **Onayla ve yetki kaydı oluştur** (primary), Alanı düzelt, Yeni belge iste, İncelemeye gönder.
8. Post-approval panel: green "yetki kaydı oluşturuldu" card with the source document and a button through to `/mobile`. This is the hinge between the two acts — it must be visible on stage.

### Backend steps

1. `POST /api/applications/{id}/decision` — status transition, audit row, and on `approve` build the `AuthorityRecord` from the extraction (persons with degrees, the demo rule set, source document, verified_at, valid_until) and return its id.
2. `GET /api/registry` and `PUT /api/registry/{mersis}/rep/{name}` — toggle a representative, write `registry.json` atomically (temp file + rename; a half-written registry at hour 40 is a very bad afternoon).
3. Audit rows for every decision, with actor and detail.

### Frontend steps (registry screen)

4. `/registry` — grouped table by company, status pills, and the "Kayıttan çıkar / Geri al" toggle. Large text: this screen is read from the back of a room.

### Done when
- [ ] All four fixture cases render correctly, including the amber co-signer row naming the missing person
- [ ] Approval creates an authority record and shows the hinge panel
- [ ] Toggling the registry changes case 4's verdict between READY and REGISTRY_CONFLICT

---

## Phase 3 — Real integration (H16–H24)

**Goal:** one real scan → real model → real verdict, then sleep.

### Steps

1. Set `AI_MODE=live`, `AI_URL` to the AI engineer's service. Run case 1 end to end.
2. Fix the seam bugs — they always appear here: Turkish filenames in multipart uploads, date formats (`15.03.2026` vs `2026-03-15`), masked ID strings, nulls in `representatives[].limits`.
3. Verify the frontend renders identically under `stub` and `live`. If it doesn't, the bug is in your rendering, not in the model.
4. Add a 20-second timeout on the AI call returning a clean degraded response — never a hang, never a 500.
5. Confirm the extraction cache works: the second analysis of the same file returns instantly.
6. `git tag h24-working`, push.
7. **Sleep 4–5 hours.**

### Done when
- [ ] Case 1 passes end to end with the real model
- [ ] Cache hit verified; tagged commit exists

---

## Phase 4 — All four cases (H24–H30)

**Goal:** the four onboarding cases are live and reproducible from the control panel.

### Backend steps

1. Pass `fieldsNeedingReview` and any anomaly codes through the aggregate endpoint.
2. `POST /api/demo/reset` — full reset in one call (rows + registry + uploads), so rehearsals start clean.
3. Guard rails: analyzing an application with no document returns a clean 409, not a stack trace.

### Frontend steps

4. Verify each verdict style against the mock, including case 3 where several checks are red at once.
5. Keyboard shortcuts on `/`: keys 1–4 load the corresponding case. You will use these on stage.
6. Loading state during analysis ("Belge okunuyor…") with the page thumbnails visible, so a slow model looks intentional.
7. Error state: if analysis fails, show a calm retry card rather than a broken screen.

### Done when
- [ ] Four cases run live from the control panel, each under 30 seconds
- [ ] Reset returns the system to a clean state in one click

---

## Phase 5 — Act 2 (H30–H34)

**Goal:** the authority record enforces live transactions on the phone.

### Backend steps

1. Seed the demo rule set into the authority record on approval: general ≤ 500.000 TL single signature; above that dual; credit dual at any amount; real estate out of scope.
2. `services/authority_engine.py` — `authorize(mersis, subject, amount, initiator)` in this order:
   1. person exists in the authority record → else `DENIED`
   2. **re-read `registry.json` now** — representative removed ⇒ `DENIED` ("yetki düşmüş")
   3. record still within `valid_until` → else `DENIED`
   4. subject out of scope ⇒ `DENIED`
   5. subject requires dual signature ⇒ `PENDING_COSIGN`
   6. amount over the single limit ⇒ `PENDING_COSIGN`
   7. otherwise `ALLOWED` + authorization code
   Each step appends a check with a human-readable reason — the phone renders exactly these.
3. Measure real elapsed time into `latency_ms`. Do not hardcode it; the honesty is the point and it will genuinely be tens of milliseconds.
4. `POST /api/transactions/{id}/cosign` — re-run the decision with the co-signer present, transition to `ALLOWED`, issue the code.
5. Audit rows for every transaction and every co-sign.
6. `GET /api/transactions?mersis=` for the audit table.

### Frontend steps

7. `/mobile` with `PhoneFrame` and the gate: if `GET /api/authority/{mersis}` returns 404, show "Bu şirket için yetki kaydı yok — önce şubede imza sirküleri doğrulanmalı" with a link to `/branch`. Never bypass this; use the rehearsal shortcut instead.
8. `PhoneSwitcher` (Ali / Ayşe) with a notification dot on the co-signer when a transaction is pending.
9. `TxnList` — four preset transactions → short "yetki sorgulanıyor" state → `DecisionCard`.
10. `DecisionCard` — three states reusing the check-row language from act 1, plus: the `AuthStamp` on approval (authorization code, source document, "Belge yeniden okunmadı; şube doğrulaması 15.03.2026"), the latency pill with the real value, and a plain-language next step on denial.
11. `CosignCard` on Ayşe's phone — push-notification styling, "Onayla ve imzala" → returns to Ali's phone as approved.
12. `/authority/[mersis]` — authority card (source, branch verification, people with live registry status), rules table, and the audit table fed by `/api/transactions`.

### Done when
- [ ] The phone is correctly gated before branch approval
- [ ] Four transactions produce ALLOWED / PENDING / PENDING / DENIED
- [ ] Co-signing on the second phone completes the transaction
- [ ] Removing Ali in `/registry` turns a previously approved transaction into DENIED
- [ ] The audit table shows both states of the co-signed transaction

---

## Phase 6 — Resilience and polish (H34–H40)

**Goal:** make stage failure impossible.

### Backend steps

1. `AI_MODE=replay` — serve cached real extractions through the same code path. Test with the AI service **stopped**.
2. Harden `api/seed.py` to restore the complete demo state including uploads.
3. Atomic writes for `registry.json`; never leave a partial file.

### Frontend steps

4. Visual pass on `/branch` review and `/mobile` only — they are on stage for almost the whole demo.
5. Projector check at 1280×800: font sizes, contrast, and whether `/registry` is legible from the back of the room.
6. Remove every console error. A red console during a demo is a small thing that reads as sloppiness if anyone sees it.
7. Freeze the UI. After H40, only bugs on the demo path get fixed.

### Done when
- [ ] The entire demo runs with the AI service killed
- [ ] One-command reset works; no console errors; projector-legible

---

## Phase 7 — Rehearsal (H40–H46)

1. Run the eleven-beat runbook in `PLAN.md` five times end to end, out loud, on the demo machine.
2. Time each beat; anything that runs long gets cached or cut, never rushed.
3. Record a full screen capture of a perfect run; copy it to the second laptop and a phone.
4. Rehearse the failure path: kill the AI service mid-run and continue in replay mode without visible change.
5. Decide who clicks and who talks, and don't swap on the day.

## Phase 8 — Buffer (H46–H48)

No code. Charge everything, arrive early, test the projector, run `python -m api.seed` once, and leave it loaded on case 1.

---

## 2.6 Risks you own, and the mitigation

| Risk | Mitigation |
|---|---|
| Blocked waiting on the AI service | `AI_MODE=stub` from H4; fixtures are committed |
| Contract drift between `types.ts` and `schema.py` | one commit changes both; announced out loud |
| Turkish text bugs (İ/ı, filenames, encoding) | UTF-8 everywhere; test with "Ayşe Demir" and "İmza Sirküleri" as literal inputs from day one |
| Registry file corrupted mid-demo | atomic write; `seed.py` restores it in two seconds |
| Slow model on stage | extraction cache + replay mode + deliberate loading choreography |
| Feature creep after H40 | the cut list in `PLAN.md` is pre-agreed; no debate at 3 a.m. |
| Venue network isolates the laptops | tested at H4; hotspot/Tailscale fallback; demo runs on one machine anyway |

## 2.7 Definition of done for the full-stack track

- Four screens working against the real backend, with the two acts connected by branch approval.
- The four onboarding cases and the four transactions reproducible from the control panel in any order.
- One command resets everything; one flag survives a dead AI service.
- No screen in the demo path throws, hangs, or shows a console error.
