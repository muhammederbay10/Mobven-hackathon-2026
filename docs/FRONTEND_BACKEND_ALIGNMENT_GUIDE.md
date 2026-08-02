# YetkiCheck frontend implementation and backend alignment guide

This file is the handoff for a frontend engineer who has never seen YetkiCheck.
It explains what the product does, what the backend already implements, what is
still missing in `web/`, and the exact frontend work needed to connect them.

Do not use `docs/fbdocs/index.html` as the application workflow. It is only a
visual/component reference. The production workflow described here and in
`docs/fbdocs/IMPLEMENTATION_PLAN.md` is authoritative.

## 1. Product in one minute

YetkiCheck verifies a company's signature circular once at a bank branch and
turns the reviewed document into a persistent authority record. Later mobile
transactions are checked against that authority record and the current
simulated trade registry.

There are two acts:

1. **Branch onboarding:** application → identity attestation → original
   document upload → AI extraction/checks → human review → approval.
2. **Mobile enforcement:** transaction request → current authority/registry
   evaluation → allowed, denied, or pending a second signature.

The frontend displays decisions. It must never calculate an onboarding verdict,
decide whether a transaction is allowed, invent an authority, or complete a
co-signature locally.

## 2. Read these files first

Read in this order:

1. `docs/FRONTEND_BACKEND_ALIGNMENT_GUIDE.md` — this handoff.
2. `docs/BACKEND_PHASE_1_5_REPORT.md` — completed backend and test coverage.
3. `api/schemas.py` — exact bank API request/response models.
4. `web/lib/types.ts` and `web/lib/contracts.ts` — existing frontend contract
   mirrors. They are incomplete for bank resource views and must be extended.
5. `docs/fbdocs/design/DESIGN_SYSTEM.md` and
   `docs/fbdocs/design/nexai-dashboard-reference.png` — visual system only.
6. `docs/fbdocs/IMPLEMENTATION_PLAN.md`, section 10 — detailed screen intent.
7. `docs/API_CONTRACT.md` — AI wire contract. The browser does not call it.

Use `docs/fbdocs/index.html` only for document-paper styling, status treatments,
the phone frame, density, and presentation character. Do not copy its state
machine, hardcoded cases, client-side decisions, or NexAI content.

## 3. Current repository state

The shared shell and route skeletons already exist:

- `/` — demo control panel; substantially wired.
- `/branch` — placeholder after the three-step header.
- `/mobile` — placeholder phone frame.
- `/authority/[mersis]` — skeleton/placeholder.
- `/registry` — placeholder.

Reusable presentation components already exist under `web/components/`, and
design tokens live in `web/app/globals.css`.

The backend is implemented through Phase 5. The frontend must consume it; do
not create mock decisions to replace it.

Important gaps in the current frontend:

- No `getApplication()` API function.
- No `analyzeApplication()` API function.
- No `correctExtraction()` API function.
- Decision calls return `unknown` instead of `ApplicationAggregate`.
- Create/upload calls return partial `{id}` types instead of their real views.
- No authority-history API function.
- No audit-history API function.
- Bank resource models such as `ApplicationView`, `DocumentView`, and
  `ApplicationAggregate` are missing from `web/lib/types.ts` and Zod.
- Successful HTTP responses are currently cast to `T`; strict Zod parsing must
  be added at the API boundary for the new resource responses.
- The main plan's “skip directly to Act 2” control has no backend endpoint or
  committed pre-approved application loader. Do not implement it with local
  state.
- An already `ANALYZED` application cannot currently be force-reanalyzed only
  because registry state changed: `/analyze` is intentionally idempotent and
  returns the existing report. This affects the plan's case-4 “restore registry
  and re-analyze” acceptance item and needs backend coordination.

## 4. Runtime setup

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

Frontend (`web/.env.local`):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Frontend:

```powershell
cd web
npm install
npm run dev
```

The browser talks only to the bank API on port 8000. It must never call the AI
service directly. Stub/live/replay AI modes are entirely backend concerns and
must not create frontend branches.

## 5. Frozen routes and navigation

Keep these product routes:

| Route | Responsibility |
|---|---|
| `/` | Demo cases, reset, and flow explanation |
| `/branch?application={id}` | Persistent branch intake/review state |
| `/mobile?mersis={mersis}` | Authority-gated transaction and co-sign UI |
| `/authority/{mersis}` | Active authority, sources, history, and audit |
| `/registry` | Clearly labeled simulated registry management |

The application ID must remain in the `/branch` query string. The MERSİS number
should remain in the mobile query string and authority path. Do not keep either
only in component state because refresh must restore the screen.

The co-signer experience is a state of `/mobile`, not another route.

## 6. Backend API surface

All non-2xx responses use the error envelope described in section 11 below.

### Infrastructure and demo

| Method | Path | Response/use |
|---|---|---|
| GET | `/health` | Process/database health |
| GET | `/ready` | Dependency readiness; useful on the demo home page |
| GET | `/api/demo/cases` | `{cases: DemoCaseCard[]}` |
| POST | `/api/demo/load-case/{n}` | `201 {application_id}` |
| POST | `/api/demo/reset` | Reset database, registry, and uploads |
| POST | `/api/demo/cache/prewarm` | Optional operator control, not normal product UI |
| POST | `/api/demo/cache/clear` | Optional operator control, not normal product UI |

`load-case` creates a real persistent application. It does not fake a completed
workflow and does not upload the document.

### Branch application

| Method | Path | Response |
|---|---|---|
| POST | `/api/applications` | `201 ApplicationView` |
| GET | `/api/applications/{id}` | `ApplicationAggregate` |
| POST | `/api/applications/{id}/document` | `201 DocumentView` |
| GET | `/api/documents/{document_id}/page/{page}` | Rendered PNG |
| POST | `/api/applications/{id}/analyze` | `ApplicationAggregate` |
| PATCH | `/api/applications/{id}/extraction` | `ApplicationAggregate` |
| POST | `/api/applications/{id}/decision` | `ApplicationAggregate` |

### Registry, authority, history, and mobile

| Method | Path | Response |
|---|---|---|
| GET | `/api/registry` | `Registry` |
| PUT | `/api/registry/{mersis}/reps/{rep_id}` | `RegistryCompany` |
| GET | `/api/authority/{mersis}` | Active `AuthorityRecordView` |
| GET | `/api/authority/{mersis}/history` | `{items: AuthorityRecordView[]}` |
| POST | `/api/transactions/authorize` | `TransactionDecision` |
| POST | `/api/transactions/{id}/cosign` | `TransactionDecision` |
| GET | `/api/transactions?mersis={mersis}` | `TransactionDecision[]` |
| GET | `/api/audit?entity_type=&entity_id=` | `{items: AuditItem[]}` |

Registry mutation and demo controls return `403 DEMO_MODE_DISABLED` when the
backend is not in demo mode.

## 7. Types the frontend must add

Keep JSON names exactly as shown. Bank-owned resources are snake_case. The
embedded AI extraction remains camelCase where defined by `ExtractionResult`.

```ts
export type ApplicationView = {
  id: number;
  company_name: string;
  tax_number: string;
  mersis: string;
  applicant_name: string;
  applicant_tckn_masked: string;
  branch_code: string;
  identity_verified_at_branch: boolean;
  status: ApplicationStatus;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentView = {
  id: number;
  application_id: number;
  original_filename: string;
  mime_type: "application/pdf" | "image/png" | "image/jpeg";
  size_bytes: number;
  document_sha256: string;
  page_count: number;
  original_seen: boolean;
  scanned_by: string;
  created_at: string;
};

export type CorrectionView = {
  id: number;
  field_path: string;
  old_value_json: { value: unknown };
  new_value_json: { value: unknown };
  reviewer: string;
  reason: string;
  created_at: string;
};

export type ApplicationAggregate = {
  application: ApplicationView;
  document: DocumentView | null;
  extraction: ExtractionResult | null; // effective extraction after corrections
  report: CheckReport | null;
  corrections: CorrectionView[];
  authority: AuthorityRecordView | null;
};

export type AuthorityHistoryResponse = {
  items: AuthorityRecordView[];
};

export type AuditItem = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  correlation_id: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type AuditHistoryResponse = { items: AuditItem[] };
```

Add strict Zod schemas for these types and mutual-assignability guards following
the existing patterns in `web/lib/contracts.ts`.

Do not expose the extraction's raw database row. The aggregate's `extraction`
is already the effective, corrected projection. `corrections` is the visible
append-only review history.

## 8. API functions to implement or correct

Keep `web/lib/api.ts` as the only file that calls `fetch`.

Add or change these functions:

```ts
createApplication(payload): Promise<ApplicationView>
getApplication(applicationId): Promise<ApplicationAggregate>
uploadDocument(applicationId, file, fields): Promise<DocumentView>
analyzeApplication(applicationId): Promise<ApplicationAggregate>
correctExtraction(applicationId, payload): Promise<ApplicationAggregate>
decideApplication(applicationId, payload): Promise<ApplicationAggregate>
getAuthority(mersis): Promise<AuthorityRecordView>
getAuthorityHistory(mersis): Promise<AuthorityHistoryResponse>
getAuditHistory(filters?): Promise<AuditHistoryResponse>
getRegistry(): Promise<Registry>
updateRegistryRepresentative(...): Promise<RegistryCompany>
authorizeTransaction(payload): Promise<TransactionDecision>
cosignTransaction(transactionId, payload): Promise<TransactionDecision>
listTransactions(mersis): Promise<TransactionDecision[]>
```

Parse successful JSON with the corresponding Zod schema inside `lib/api.ts`.
Do not defer response validation to page components.

The document upload is multipart form data:

```text
file            File
original_seen   "true" | "false"
scanned_by      string
```

The frontend never sends an audit actor. The backend assigns the fixed branch
actor. Mobile audit actors come from the selected authority-person ID.

## 9. Application state and branch stepper

Backend state is authoritative:

```text
DRAFT
  → IDENTITY_VERIFIED
  → DOCUMENT_SCANNED
  → ANALYZING
  → ANALYZED
  → APPROVED | DOC_REQUESTED | ESCALATED

ANALYZING → ANALYSIS_FAILED → ANALYZING
ANALYZED  → ANALYZING → ANALYZED   (correction re-analysis)
```

Map state to the UI as follows:

| Backend status | Branch UI |
|---|---|
| no application ID | Step 1 create form |
| `DRAFT` | Step 1; explain identity attestation is incomplete |
| `IDENTITY_VERIFIED` | Step 2 document upload |
| `DOCUMENT_SCANNED` | Step 2 with document preview and Analyze action |
| `ANALYZING` | Preserve document/review area and show non-destructive progress |
| `ANALYSIS_FAILED` | Preserve document and show retry using `/analyze` |
| `ANALYZED` | Step 3 review, corrections, checks, and decisions |
| `APPROVED` | Completed hinge card with authority/mobile links |
| `DOC_REQUESTED` | Terminal branch result; offer start-new navigation |
| `ESCALATED` | Terminal branch result; show escalation confirmation |

Never advance the stepper because a local animation ended. After every
mutation, render the aggregate returned by the server or refetch it.

The backend currently has no separate endpoint to attest identity after a
`DRAFT` application is created. Therefore the normal create form must require
`identity_verified_at_branch=true` before submission. If a `DRAFT` record is
encountered, show it honestly and allow starting a corrected application; do
not fake the transition.

## 10. Branch screen implementation

### Demo control panel behavior (`/`)

The existing page already loads cases and calls reset. Complete the remaining
Phase 1/4 behavior as follows:

- Keep all four cards data-driven from `GET /api/demo/cases`.
- While loading a case, disable the cards, preserve their content, and show
  which case is loading.
- After success, navigate to `/branch?application={application_id}`.
- Add keyboard shortcuts `1`–`4` only when focus is not in an input, textarea,
  select, button, or content-editable element. Use the same handler as clicking
  the corresponding card.
- Reset needs pending, success, and error states. After success, clear stale
  application/MERSİS client state and remain on or return to `/`.
- Loading a different case must abort old requests and clear the previous
  branch result visually; server state remains authoritative.
- Do not add the plan's “skip to Act 2” button until a server-side pre-approved
  loader exists. A disabled control with a developer-facing explanation is
  preferable to client-only approval, but it may also be omitted for now.

### Step 1 — application and branch identity

Use `CreateApplicationRequest` exactly:

```json
{
  "company_name": "ABC Teknoloji Ltd. Şti.",
  "tax_number": "1234567890",
  "mersis": "0123456789000017",
  "applicant_name": "Ali Yılmaz",
  "applicant_tckn_masked": "123******01",
  "branch_code": "kozyatagi01",
  "identity_verified_at_branch": true
}
```

Render server field errors beside inputs through the existing `fieldErrors()`
helper. TCKN stays masked everywhere.

Demo case loading already creates this application, so `/branch?application=id`
usually starts from the aggregate returned by `GET /api/applications/{id}`.

### Step 2 — original document upload and analysis

- Require the original-seen checkbox.
- Accept PDF, PNG, and JPEG.
- Show client file name/size before upload, then use `DocumentView` from the
  server for authoritative type, size, hash, page count, and file name.
- While upload is pending, show an honest indeterminate progress treatment and
  “Belge yükleniyor” text. The current fetch transport does not expose byte
  progress, so do not fabricate a percentage. If real byte progress is later
  required, implement the upload transport centrally in `web/lib/api.ts`, not
  inside the page.
- Show a local thumbnail immediately when safe, then replace it with the
  server-rendered first page after upload succeeds.
- Use `documentPageUrl(document.id, page)` for previews. Do not use or request a
  filesystem path.
- Call `/analyze` only after the upload returns `DOCUMENT_SCANNED` state.
- Preserve the document and allow retry after a retryable AI error.

In current stub mode, demo documents must keep these filenames because the
fixture adapter selects by committed filename:

- case 1 → `data/documents/case1.pdf`
- case 2 → `data/documents/case2.pdf`
- case 3 → `data/documents/case3.pdf`
- case 4 → reuse `data/documents/case1.pdf`

Use an ordinary file input for the actual branch workflow. Do not silently
auto-attest or auto-upload a local file. The browser cannot read backend-local
paths. If a future one-click demo upload is desired, coordinate a dedicated
demo endpoint rather than inventing client-only completion.

### Step 3 — extraction, evidence, checks, and decision

Layout:

1. Verdict banner.
2. Document page viewer.
3. Extracted company/notary/validity/representative fields.
4. `fieldsNeedingReview` warnings.
5. Exactly nine checks, in backend order, using reason/evidence verbatim.
6. Correction history.
7. Decision controls.

Do not sort checks. Do not derive a verdict from their colors.

Evidence interaction:

- Build page tabs from `document.page_count`.
- Selecting extraction evidence or a rule evidence item changes the document
  viewer to its 1-based `page`.
- Highlight the selected quote/clause in the evidence panel and flash the
  corresponding document-paper surface.
- The flat contract provides page number and quote but no bounding box for
  these clauses. Do not invent pixel coordinates or pretend to highlight an
  exact rectangle on the PNG.
- Check evidence is a flexible dictionary. Render known safe scalar entries,
  link any valid page reference, and never assume every check has a bounding
  box.
- Mark check IDs `registry_status` and
  `registry_representative_match` with `SimBadge` because those checks use the
  simulated registry.
- The fields → checks → verdict → evidence-flash sequence may be animated, but
  the aggregate must already be persisted and available before animation.

The six correction targets are:

```text
company.name
company.taxNumber
company.mersisNumber
representatives[<source_id>].name
representatives[<source_id>].mode
validUntil
```

Correction request example:

```json
{
  "reason": "Noter belgesiyle tekrar kontrol edildi.",
  "corrections": [
    {
      "field_path": "representatives[rep-1].name",
      "expected_old_value": "Ali Yilmaz",
      "new_value": "Ali Yılmaz"
    }
  ]
}
```

Always send the currently displayed value as `expected_old_value`. On
`409 STALE_CORRECTION`, refetch the aggregate, keep the user's proposed value
available, and ask them to compare against the new server value.

Decision behavior:

- `READY`: normal Approve action.
- `CO_SIGNER_REQUIRED`: normal actions are Request new document or Escalate.
  There is no branch co-signer workflow. An exceptional Approve action may be
  exposed separately and must require typed `override_justification`.
- `MISMATCH` and `REGISTRY_CONFLICT`: no Approve action.
- `fieldsNeedingReview` non-empty: no Approve action.

Requests:

```json
{"action":"approve"}
{"action":"approve","override_justification":"Typed branch justification"}
{"action":"request_document","note":"Readable new copy requested"}
{"action":"escalate","note":"Sent to compliance review"}
```

The frontend may hide obviously invalid actions for usability, but the backend
remains the enforcement authority.

After approval, the returned aggregate contains `authority`. Show a completion
hinge card with links to:

```text
/authority/{application.mersis}
/mobile?mersis={application.mersis}
```

## 11. Standard error handling

Every backend error is:

```json
{
  "error": {
    "code": "STALE_CORRECTION",
    "message": "User-facing Turkish message",
    "retryable": true,
    "details": {},
    "correlation_id": "..."
  }
}
```

Rules:

- Preserve the current screen on network/5xx/retryable errors.
- Show Retry only when `retryable` is true or the error is `NETWORK_ERROR`.
- Show the backend Turkish message; do not expose stack traces or raw response.
- Include the correlation ID in a small support/details area.
- Use field errors from `details.fields` beside inputs.
- Abort stale requests on unmount or application/MERSİS change.
- Never infer that a mutation succeeded after a network error; refetch.

Important codes:

| Code | Frontend response |
|---|---|
| `DOCUMENT_REQUIRED` | Return to/upload in step 2 |
| `INVALID_STATE_TRANSITION` | Refetch aggregate; another state is authoritative |
| `ANALYSIS_IN_PROGRESS` | Keep progress state and poll/refetch conservatively |
| `AI_TIMEOUT`, `AI_UNAVAILABLE` | Preserve document and offer Analyze retry |
| `STALE_CORRECTION` | Refetch and reopen correction comparison |
| `APPROVAL_NOT_ALLOWED` | Preserve review; show backend reason |
| `OVERRIDE_JUSTIFICATION_REQUIRED` | Focus justification input |
| `AUTHORITY_NOT_FOUND` | Gate mobile and link back to branch |
| `COSIGN_NOT_ALLOWED` | Preserve transaction and show backend reason |
| `DEMO_MODE_DISABLED` | Disable/hide demo-only mutation controls |

### Phase 3 live, stub, and replay presentation

The review component must be identical in all AI modes. The frontend does not
select the AI mode.

- Keep the uploaded document thumbnail and application context visible while
  status is `ANALYZING`.
- Use calm, truthful progress text such as “Belge analiz ediliyor” and “Bu işlem
  biraz sürebilir.” Do not display fabricated stages like OCR complete or model
  complete because the backend does not stream those stages.
- On `AI_TIMEOUT` or `AI_UNAVAILABLE`, preserve the document and show the
  backend retry action.
- Calling Analyze again is the only frontend retry operation. Whether that
  retry uses live AI, cache, or replay is controlled by the backend.
- If the UI shows the current mode for demo operators, read it from
  `/ready` (`checks.ai.ai_mode`) and label replay honestly. Never infer mode
  from response speed.
- Null/unknown extraction fields render as “Okunamadı” with their review flags;
  they must not be replaced by guessed values.

## 12. Registry screen

Fetch `GET /api/registry` and group representatives under their company. The
response already contains stable `rep_id`, masked TCKN, mode, status, and
effective date.

Requirements:

- Permanent `SimBadge` and a clear “not real MERSİS” explanation.
- Remove/restore buttons address representatives by stable ID, never name.
- Confirm before mutation.
- Disable only the affected row while saving.
- Replace the returned company in local display state or refetch the registry.
- Keep text/icon labels in addition to color.
- If demo mode is disabled, the mutation returns 403; the page may stay
  read-only.

Request:

```json
{"status":"REMOVED"}
```

or:

```json
{"status":"ACTIVE"}
```

## 13. Authority screen

Fetch in parallel:

- active authority: `/api/authority/{mersis}`;
- authority versions: `/api/authority/{mersis}/history`;
- transactions: `/api/transactions?mersis=...`;
- registry: `/api/registry`;
- relevant audit records: `/api/audit` with filters where useful.

Show:

- authority ID, version, status, validity;
- source application/document IDs;
- branch verifier and verification time;
- people with stable authority ID, source ID, masked TCKN, title, and dates;
- rules with lowercase scope rendered as Turkish labels, integer-kuruş
  thresholds formatted at the display edge, signature mode, required signer
  IDs, blocked status, and evidence;
- version history and transaction/audit timeline.

The frozen `AuthorityRecordView` does not include a current registry-status
field. For display only, join `authority.persons[].id` to
`registry.companies[].representatives[].id` and show the current registry
status. Do not use that client join to approve or deny anything; transaction
enforcement rereads the registry on the backend.

## 14. Mobile screen

Read `mersis` from `/mobile?mersis=...`. First call `getAuthority(mersis)`.
When it returns `AUTHORITY_NOT_FOUND`, show the gated empty state and a link to
the branch flow.

Build the person switcher from `authority.persons`. Do not hardcode Ali/Ayşe as
business logic. Demo preset cards are allowed as input conveniences, but their
results must always come from `/authorize`.

Authorization request:

```json
{
  "mersis": "0123456789000017",
  "subject": "GENERAL",
  "currency": "TRY",
  "amount_minor": 25000000,
  "initiator": "rep_abc_ali"
}
```

Important: `amount_minor` is integer kuruş. Use helpers in `web/lib/format.ts`.
Do not divide or format money ad hoc in components.

Render `TransactionDecision` exactly:

- `ALLOWED`: checks, authorization code, measured latency, authority/document
  source, verification time.
- `PENDING_COSIGN`: checks and `required_cosigner`; show a notification on that
  authority person and offer the co-sign state.
- `DENIED`: checks and a plain-language next step; authorization code remains
  null.

Co-sign request:

```json
{"cosigner":"rep_abc_ayse"}
```

Call the backend and replace the displayed decision with its response. Never
turn pending into allowed in React state without that response. Repeating a
successful co-sign is idempotent and returns the same authorization code.

For the judged presentation, the selected initiator and required co-signer can
be shown as two simulated phone/person states inside the same route. Put the
notification dot on the person whose stable ID equals `required_cosigner`.

Refresh restoration:

- Reload authority and transaction history from `mersis` in the URL.
- The latest `PENDING_COSIGN` history item contains the transaction ID and
  required co-signer, so its co-sign action can be restored after refresh.
- The current transaction-history contract does not include original subject,
  amount, or initiator fields. Keep those details only while the current page
  session exists; after refresh show the persisted decision/check/source data
  without inventing missing request details.

After every authorization or co-sign, refresh transaction history and the
authority/registry display. A representative can be removed after approval,
and the next backend transaction must visibly become denied while the stored
authority record remains unchanged.

## 15. Demo scenarios and expected visible behavior

The cases are fixtures, not separate workflows. Only demo-control routing may
care about the case number.

| Case | Document | Expected onboarding verdict | Branch behavior |
|---|---|---|---|
| 1 | `case1.pdf` | `READY` | Normal approval creates authority |
| 2 | `case2.pdf` | `CO_SIGNER_REQUIRED` | Request/escalate normally; typed override is exceptional |
| 3 | `case3.pdf` | `MISMATCH` | No approval |
| 4 | `case1.pdf` | `REGISTRY_CONFLICT` | No approval; registry shows Ali removed |

Act-2 acceptance after case 1 approval:

| Input | Expected backend result |
|---|---|
| General, 25,000,000 kuruş, Ali | `ALLOWED` |
| General, 120,000,000 kuruş, Ali | `PENDING_COSIGN`, then Ayşe → `ALLOWED` |
| Credit, 75,000,000 kuruş, Ali | `PENDING_COSIGN`, then Ayşe → `ALLOWED` |
| Real estate, 0 kuruş | `DENIED` |
| Remove Ali in registry, retry general | `DENIED` while stored authority remains active |

These amounts may be demo preset inputs. They must never be used to calculate
the displayed result.

## 16. Loading, mutation, and refresh rules

Every async area needs:

- loading state;
- retryable error state;
- terminal error state;
- empty state;
- success state.

For mutations:

- prevent accidental double-clicks while pending;
- keep existing server data visible;
- use returned server state rather than manually patching business fields;
- refetch after an ambiguous network failure;
- do not use fake timers to determine completion;
- animations may delay only the visual reveal.

After demo reset, clear locally remembered application/MERSİS navigation and
return to `/`, because old database IDs no longer exist.

## 17. Visual and accessibility rules

- Use the existing shared shell, Inter font assets, tokens, and components.
- Projector-first: readable at 1280×800 with no horizontal overflow.
- Status always uses icon + label + color.
- Keep semantic green/amber/red stronger than decorative accents.
- Preserve keyboard focus and support keyboard operation.
- Use real buttons for actions and correct labels for inputs.
- Do not introduce another design system inside route pages.
- Keep registry and mobile integrations visibly labeled simulated.
- Turkish is the user-facing language; code/type names remain contract names.

## 18. Recommended implementation order

1. Add missing bank resource types and strict Zod schemas.
2. Complete `web/lib/api.ts` wrappers and response parsing.
3. Add API/contract unit tests for all new wrappers and resource schemas.
4. Implement `/branch` aggregate loading and state-driven stepper.
5. Implement branch create/upload/page preview/analyze.
6. Implement review, evidence, corrections, decisions, and approval hinge.
7. Implement `/registry` and stable-ID mutations.
8. Implement `/authority/[mersis]` with version/transaction/audit data.
9. Implement `/mobile` authorization and backend co-sign flow.
10. Finish demo keyboard/polish and reset navigation behavior.
11. Test refresh restoration and all four cases end to end.

Do not begin with visual polish on placeholder data. First make every screen
render persisted backend state.

## 19. Required tests

At minimum add tests for:

- strict Zod parsing of all bank resource responses;
- `ApplicationStatus` → branch step mapping;
- refresh with `?application=id` restores aggregate state;
- missing/invalid application ID;
- upload validation and original-seen requirement;
- analyze loading, failure, retry, and success;
- exactly nine checks preserved in order;
- correction path construction and stale correction handling;
- approval button matrix for all four onboarding verdicts;
- mandatory amber override justification;
- stable-ID registry remove/restore;
- mobile gate when authority is absent;
- allowed, pending, denied, successful co-sign, and rejected co-sign;
- amount formatting from integer minor units;
- registry removal reflected on the next transaction;
- reset clears stale navigation state;
- retryable versus terminal error UI;
- status accessibility without relying on color.

### Phase-to-guide coverage

| Main-plan frontend phase | Where this guide covers it |
|---|---|
| Phase 1 | Sections 3–11: contracts, API layer, control panel, branch intake, upload, status-driven restore, errors |
| Phase 2 | Sections 10–13: split review, page/evidence interaction, nine checks, corrections, decisions, registry, authority hinge |
| Phase 3 | Section 11: mode-independent review, honest progress, live failure, retry/replay labeling, null fields |
| Phase 4 | Sections 10 and 15–16: shortcuts, reset/loading states, four cases, retry cards, stale-state clearing |
| Phase 5 | Sections 13–15: authority, registry join, presets, backend checks, co-sign, refresh, transaction/audit history |

Two plan acceptance items remain backend-coordination items rather than
frontend implementation tasks:

1. **Skip directly to Act 2:** no endpoint can create/load a pre-approved
   authority. Do not fake it.
2. **Registry-only case-4 re-analysis:** `/analyze` returns the existing report
   for an `ANALYZED` application. The backend needs an explicit re-analysis
   contract before the frontend can offer this action.

Everything else required by the Phase 1–5 frontend steps is specified in this
guide and backed by an implemented endpoint.

Before handoff run:

```powershell
cd web
npm run typecheck
npm run lint
npm run test
npm run build
```

Then run the backend suite from the repository root to confirm the frontend
work did not drift shared fixtures or contracts:

```powershell
.\.venv\Scripts\python.exe -m pytest api/tests -q
```

## 20. Definition of done

The frontend is aligned when:

- all five routes use real backend state;
- refresh restores branch/mobile/authority context from URL + API;
- no page calls `fetch` outside `web/lib/api.ts`;
- no component computes a verdict or transaction decision;
- branch corrections and decisions persist and survive refresh;
- approval creates an authority and the mobile link works;
- mobile co-sign is completed only by the backend;
- registry removal affects the next transaction visibly;
- demo cases 1–4 show the expected server verdicts;
- all async/error/empty states are present;
- simulated integrations are labeled;
- typecheck, lint, tests, build, and backend regression all pass.
