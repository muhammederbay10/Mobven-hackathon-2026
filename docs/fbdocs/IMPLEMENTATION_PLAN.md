# YetkiCheck — implementation-ready delivery plan

**Canonical product source:** `docs/fbdocs/PROJECT.md`

**Authoritative AI HTTP contract:** `docs/API_CONTRACT.md`

**Reference component/presentation experience:** `docs/fbdocs/index.html`

**Reference visual design:** `docs/fbdocs/design/nexai-dashboard-reference.png`

**Frozen visual contract:** `docs/fbdocs/design/DESIGN_SYSTEM.md`

**Implementation ownership:** full-stack track only — `web/`, `api/`, data/demo tooling, and integration with the externally owned AI service.

**Purpose of this document:** turn the full-stack product plan into an executable specification that a coding agent can implement without inventing architecture, contracts, state transitions, or demo behavior.
**Precedence:** when this plan and `PROJECT.md` differ on product intent, `PROJECT.md` wins. `docs/API_CONTRACT.md` wins for every AI-service request/response field, enum, alias, endpoint status, and fixture shape. This plan remains authoritative for bank architecture, persistence, state transitions, production flow, and phases. `DESIGN_SYSTEM.md` and its reference PNG are authoritative for the visual system. `index.html` is a component and presentation reference only; it does not define the production workflow, routing, persistence, security, or business logic.

## Contract alignment note — 2026-08-01

The AI engineer delivered the updated flat `schema_version: "1.0"` contract after initially following the older `PLAN.md`. The full-stack implementation now adapts to that delivered wire format instead of requiring the AI service to adopt this plan's former rich snake_case projection.

The effective changes are:

- flat/camelCase `ExtractionResult` on the AI boundary;
- strict integer-kuruş `limits` and `threshold`;
- stable `representatives[].id` values and ID-based `rules[].coSigners`;
- explicit `blocked` real-estate rules;
- lowercase `green | amber | red` check statuses;
- check IDs `registry_status` and `registry_representative_match`;
- minimal `{verdict, checks}` `CheckReport`;
- MERSİS-keyed registry input and optional top-level `as_of` for `/analyze`;
- `/health` and `/analyze` are implemented; `/extract` remains pending.

The bank-owned registry envelope, public bank API, database metadata (`engine`, document SHA-256, timestamps), state machines, and audit/error formats do not change. The bank API projects its records into the AI wire shape only inside `api/services/ai_client.py`.

---

# 1. Evaluation of the source plan

## 1.1 What is already strong

`PROJECT.md` has a clear product thesis and a stage-friendly two-act story:

1. Verify the signature circular once at a branch.
2. Convert it into structured authority data.
3. Enforce that authority on every later mobile transaction.

It also correctly separates probabilistic document reading from deterministic comparison and transaction enforcement, keeps a human in the approval loop, labels simulated integrations, defines four onboarding cases and four transaction cases, and prioritizes replay/reset behavior for demo resilience.

## 1.2 Gaps that must be resolved before implementation

The source plan is directional rather than contract-complete. An implementation agent would otherwise have to guess about:

- the exact extraction and check-report schemas;
- the nine check identifiers, status rules, and verdict precedence;
- idempotency and concurrent analysis behavior;
- error response formats and expected HTTP status codes;
- how field correction works while preserving raw AI output;
- when approval is allowed and how authority records are versioned;
- how a pending co-signature is securely completed;
- which data is extracted from the document versus added as demo policy;
- fixture contents and the expected result of every case;
- the relationship between case 1 and the two-person Act 2 co-signing demo;
- file ownership and task dependencies for parallel coding agents.

This document resolves those gaps.

## 1.3 Decisions already established by `PROJECT.md`

These are treated as confirmed because they are explicit in the source plan:

1. The runtime is split into `web/`, `api/`, and `ai/`.
2. The browser calls only `api/`; it never calls `ai/` directly.
3. `api/` owns persistence, orchestration, application state, approval, authority records, transactions, registry access, and audit logs.
4. `ai/` exposes two endpoints and must be replaceable by stub/replay behavior.
5. Model output never autonomously approves an application or transaction.
6. The bank API persists AI responses instead of recreating extraction data.
7. The registry and branch identity service are simulated and visibly labeled.
8. Authority is re-checked against the current registry on every transaction.
9. The demo must survive AI or venue-network failure through committed fixtures and replay.
10. This implementation track owns only `web/`, `api/`, `data/`, demo tooling, and integration with the AI service. The AI engineer exclusively owns `ai/`. Full-stack coding agents must not scaffold, edit, start, or test AI-service code.

## 1.4 Demo scenarios are fixtures, not product workflows

The four onboarding cases and four preset transactions in `index.html` are examples of situations the product may encounter. They exist to make the hackathon demo reproducible and to verify that the generalized engines handle important classes of input.

They are **not** separate product workflows and must never be implemented as hardcoded business branches.

The implementation rules are:

1. Case numbers may appear only in demo routing, fixture loading, and test names.
2. `application_service`, the nine-check comparison engine, `authority_builder`, and `authority_engine` must not receive or inspect a case number.
3. Business code must not branch on fixture filenames, fictional company/person names, preset amounts, or expected verdicts.
4. The 500,000 credit r TL limit,ule, real-estate restriction, and Ali/Ayşe signer combination are fixture data. They are not universal product constants.
5. Onboarding checks operate on application, identity, extraction, and registry inputs supplied through the shared schemas.
6. Transaction decisions operate on the approved authority record and transaction request supplied through the shared schemas.
7. Demo case loaders create normal domain records and then call the same services used by non-demo requests.
8. Stub and replay modes return fixture data through the same contracts; the frontend and business services must not know which case produced it.
9. Adding a fifth scenario must require only new fixture/test data, not a new business-code branch.
10. The reference UI's client-side hardcoding is presentation behavior only and must not be copied into production service logic.

For a coherent stage flow, the clean synthetic fixture may include the people and authority rules needed by the Act 2 examples. That content remains document/fixture data processed by the generic extraction, approval, and enforcement path.

## 1.5 Closed decision register

All registered gaps are answered below. These decisions are now part of the implementation contract.

### `GAP-02` — Where does the deterministic nine-check comparison engine live? **Closed**

**Decision:** it lives in the AI service at `ai/compare.py`, behind `POST /analyze`, and is owned by the AI engineer.

The ownership boundary is:

- anything comparing a **document** against application/registry sources lives in `ai/`;
- anything comparing a **stored authority record** against a transaction lives in `api/`.

The bank backend never re-derives or recomputes onboarding checks. It passes the sources to the AI service, validates the response contract, persists the returned `CheckReport` verbatim, and serves it.

### `GAP-03` — What is the current AI endpoint surface? **Closed**

**Decision:**

```text
GET  /health                                               -> health metadata       (implemented)
POST /analyze    JSON: {extraction, application, registry, as_of?} -> CheckReport   (implemented)
POST /extract    multipart: file, document_id              -> ExtractionResult     (pending)
```

The API loads its bank-owned registry envelope and projects it to the MERSİS-keyed AI request inside `api/services/ai_client.py`. The AI service remains stateless and file-system-free: it never reads `registry.json`, application rows, or uploaded files by path. Live readiness remains blocked on `ai_extract` until `/extract` is delivered; stub/replay modes may proceed.

### `GAP-05` — What happens after case 2 reports “second signature required”? **Closed**

**Decision:** `CO_SIGNER_REQUIRED` is a terminal normal state for that branch application. Do not build a second-signer onboarding flow. Normal actions are “İncelemeye gönder” and “Yeni belge iste.” The audited amber override defined under `GAP-07` remains an explicit exceptional path.

Judge explanation: “At the branch, this application waits until the second representative attends. On mobile—where the same rule is enforced every day—we automated it.”

### `GAP-06` — How functional must “Alanı düzelt” be? **Closed**

**Decision:** it is genuinely functional. The extracted-field table becomes inline-editable for exactly six check-driving fields:

1. company name;
2. tax number;
3. MERSİS;
4. representative name;
5. representative authority mode;
6. `validUntil`.

Saving calls the correction `PATCH` endpoint, stores the correction beside the immutable original extraction, writes an audit row with actor/field/old/new values, and calls `/analyze` again so checks visibly re-resolve.

If behind at H38, the permitted degradation is editable + saved + audited without automatic re-analysis. A dead or cosmetic button is never acceptable.

### `GAP-07` — Which verdicts may a human approve? **Closed**

**Decision:**

| Verdict | Approvable? |
|---|---|
| `READY` | Yes, normally |
| `CO_SIGNER_REQUIRED` | Yes only through an audited override with a typed justification |
| `MISMATCH` | No; request document or escalate |
| `REGISTRY_CONFLICT` | No; escalate only |

Remove the mock's `confirm()` behavior. Amber override uses a visible justification textarea and creates a permanent exceptional audit event. Red verdicts remain unapprovable because supervisor roles are outside the MVP.

### `GAP-08` — How are demo actors and identities represented? **Closed**

**Decision:** use this fixed, fictional cast everywhere:

| Person | Masked TCKN | Role | Company |
|---|---|---|---|
| Ali Yılmaz | `123******01` | Müdür · 1. derece | ABC Teknoloji |
| Ayşe Demir | `987******45` | Müdür · 1. derece | ABC Teknoloji |
| Mehmet Kaya | `456******07` | Applicant only in case 3 | — |
| Kemal Öz | `555******22` | Yönetim Kurulu Üyesi | Zeta İnşaat |

Company fixtures:

- ABC Teknoloji Ltd. Şti.: VKN `1234567890`, MERSİS `0123456789000017`;
- Zeta İnşaat A.Ş.: VKN `9876543210`, MERSİS `0987654321000023`.

TCKNs remain masked in this exact format everywhere; never store a plausible unmasked 11-digit value. There is no identity service. Verified identity is `{name, tckn_masked}` plus `identity_verified_at_branch`. The branch audit actor is the constant `branch_user:kozyatagi01`.

The join key across document, application, and registry is Turkish-normalized name. Masked TCKN is corroborating evidence, not the primary join key. `tr_normalize()` is therefore critical shared logic with golden tests.

### `GAP-09` — How should registry representatives be addressed? **Closed**

**Decision:** address representatives by stable ID, never by name.

```json
{"id":"rep_abc_ali","name":"Ali Yılmaz","tckn":"123******01","mode":"SOLE","status":"ACTIVE"}
```

```text
PUT /api/registry/{mersis}/reps/{rep_id}    {"status":"REMOVED"}
```

Stable IDs are for addressing; normalized names are for matching. Do not reuse one mechanism for both jobs.

### `GAP-10` — Who delivers AI fixtures and synthetic documents, and by when? **Closed**

**Decision:**

| Deliverable | Owner | Deadline |
|---|---|---|
| Notarial Turkish text for four documents | AI engineer | H2 |
| `ai/schema.py` Pydantic contracts | AI engineer | H4 |
| Four `ExtractionResult` fixtures at `ai/tests/fixtures/case{1..4}.json` | AI engineer | H4 |
| PDFs and page PNGs under `data/documents/`, including one photographed document | Full-stack engineer | H4 |

The H2 text deadline is a hard dependency for document rendering. The backend stub and AI golden tests read the same extraction fixtures. After H4 neither engineer edits contracts/fixtures alone; changes require a joint commit and explicit coordination.

### `GAP-11` — What is the on-stage AI mode? **Closed**

**Decision:** use `AI_MODE=live` and `EXTRACTION_CACHE=on`. Pre-warm cases 2–4 during final rehearsal. Clear case 1's cache before the judged run so its first extraction genuinely calls the model.

Cached cases must be described as cached real results, never as live calls. Do not present `stub` fixtures as model output. `replay` is the failure fallback, and the backup recording is the third layer.

### `GAP-12` — What monetary representation is required? **Closed**

**Decision:** use integer minor units (kuruş) everywhere in code, APIs, and database. The field name is `amount_minor`, currency is fixed to `TRY`, and SQLite uses `INTEGER`. Example: 500,000 TL is `50000000`.

No floating-point money is permitted. Format only at the UI edge with `Intl.NumberFormat('tr-TR', {style:'currency', currency:'TRY'})`.

When extracting Turkish amounts, dots are thousands separators and commas are decimal separators: `1.200.000,50` becomes `120000050` minor units. If conversion is not confident, return `null` and add the field path to `fieldsNeedingReview`; never guess.

### `GAP-13` — Should registry mutation automatically suspend stored authority records? **Closed**

**Decision:** no write-through. The authority record retains its own status. The registry is consulted live on every authorization, and `/authority` joins current registry state at read time to show “yetki düşmüş.”

The document-derived record and current registry remain separate truths; the transaction decision is where they meet. A production system may subscribe to registry change events for proactive review, but live consultation at decision time remains the protective fallback.

### `GAP-14` — Is the five-route scope final? **Closed**

**Decision:** yes. The frozen routes are `/`, `/branch`, `/mobile`, `/authority/[mersis]`, and `/registry`.

- Audit is a section of `/authority`.
- The control panel replaces an application inbox.
- Login/roles are not built; the branch actor is constant.
- There is no rules-editor route; demo rules are loaded from committed seed/fixture data and consumed by generic engines.
- The co-signer view is a state of `/mobile`.

A sixth route may be added only if it replaces an existing route and only before H30.

---

# 2. Product outcome and success criteria

The implementation is successful when a presenter can demonstrate this uninterrupted sequence:

1. Load case 1 from the control panel.
2. Confirm branch identity and original-document attestations.
3. Scan/upload and analyze the document.
4. Watch extracted fields and nine checks resolve with evidence.
5. Approve the clean case and create an active authority record.
6. Open mobile banking and authorize a 250,000 TL transfer immediately.
7. Start a 1,200,000 TL transfer and complete it from Ayşe's phone as co-signer.
8. Show a credit request requiring two signatures.
9. Show a real-estate transaction being denied with a next step.
10. Remove Ali in the simulated registry.
11. Retry a transaction and show immediate denial.
12. Open the bank authority view and show the audit trail.

Every decision must cite its source and explain its reasoning in plain Turkish.

---

# 3. Scope boundaries

## 3.1 MVP scope

- Branch intake and both attestations.
- PDF/JPG/PNG upload and page rendering.
- Structured extraction with clause-level evidence.
- Nine deterministic onboarding checks.
- Four onboarding verdicts.
- Human correction, approval, document request, and escalation actions.
- Authority-record creation and versioning.
- Four deterministic transaction paths.
- Second-signature workflow.
- Mock registry administration and live re-check.
- Audit logs for material actions.
- Demo fixtures, reset, stub, replay, and live AI modes.
- Responsive, projector-readable screens matching the reference experience.

## 3.2 Explicitly out of scope

- Handwritten signature biometric matching.
- Claims that the uploaded document is authentic.
- Autonomous customer approval.
- Production MERSİS, identity-provider, bank-core, push-notification, or document-management integrations.
- Deep parsing of every annex type.
- General-purpose legal reasoning or free-form legal advice.
- Multi-tenant authorization, production IAM, high availability, and production database migration.

---

# 4. Repository and runtime architecture

## 4.1 Required repository layout

```text
web/
  app/
    page.tsx
    branch/page.tsx
    mobile/page.tsx
    authority/[mersis]/page.tsx
    registry/page.tsx
  components/
  lib/api.ts
  lib/types.ts
  lib/format.ts
  public/
  .env.example

api/
  main.py
  config.py
  db.py
  models.py
  schemas.py
  routers/
    demo.py
    applications.py
    documents.py
    registry.py
    authority.py
    transactions.py
  services/
    ai_client.py
    analysis_service.py
    application_service.py
    authority_builder.py
    authority_engine.py
    document_service.py
    registry_service.py
    audit_service.py
  tests/
  requirements.txt
  .env.example

ai/                           # external AI-engineer-owned service; read-only to this track
  schema.py                   # delivered contract input
  tests/fixtures/             # delivered golden fixture input

data/
  cache/
    extractions/                # backend-owned validated live-response cache
  documents/
  fixtures/
    cases.json
    extractions/
    reports/
  registry.seed.json
  registry.json              # generated at runtime; ignored by Git
  uploads/                   # runtime; ignored by Git

scripts/
  reset_demo.ps1
  reset_demo.sh

docs/fbdocs/
  PROJECT.md
  IMPLEMENTATION_PLAN.md
  index.html
  design/
    DESIGN_SYSTEM.md
    FRONTEND_IMPLEMENTOR_PROMPT.md
    nexai-dashboard-reference.png
```

## 4.2 Runtime flow

```text
Next.js browser :3000
        |
        | JSON/multipart through web/lib/api.ts
        v
FastAPI bank API :8000 ---- SQLite
        |                    data/registry.json
        | HTTP, private server-to-server calls
        v
FastAPI AI service :8001 (external; owned and operated by AI engineer)
```

## 4.3 Configuration

`web/.env.example`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`api/.env.example`:

```dotenv
APP_ENV=development
DEMO_MODE=true
DATABASE_URL=sqlite:///./yetkicheck.db
AI_URL=http://localhost:8001
AI_MODE=stub
EXTRACTION_CACHE=on
AI_TIMEOUT_SECONDS=90
DATA_DIR=../data
ALLOWED_ORIGINS=http://localhost:3000
MAX_UPLOAD_MB=20
```

`AI_MODE` values:

- `stub`: committed golden fixtures, with optional short artificial delay;
- `live`: call the AI service;
- `replay`: return a cached live response selected by document SHA-256.

The bank API owns the extraction cache under `data/cache/extractions/`. The AI service remains stateless and file-system-free. For the judged run, use the closed `GAP-11` policy: live mode, cache enabled, cases 2–4 pre-warmed, and case 1 cache cleared.

Unknown mode values must fail application startup with a clear configuration error.

## 4.4 Required developer commands

The completed scaffold must expose these stable commands and document them in the root README:

```text
web:  npm run dev | lint | typecheck | test | build
api:  python -m uvicorn api.main:app --reload --port 8000
      python -m pytest api/tests
demo: one platform-appropriate reset script followed by the documented web/API start order
```

Command names are part of the developer contract. An agent may add narrower commands but should not rename these after other tasks depend on them. The AI engineer separately documents and operates the AI service; this track only configures `AI_URL` and verifies connectivity/contracts.

---

# 5. Shared contracts

The AI engineer's definitions in `ai/schema.py` are the source contract delivered to this track. `api/schemas.py` and `web/lib/types.ts` must mirror its JSON. Full-stack agents never edit `ai/schema.py`; contract changes are coordinated with the AI engineer, who updates AI-owned files before the backend/frontend mirrors are changed.

## 5.1 Optional bank-canonical primitives (not AI wire)

```ts
type Confidence = "HIGH" | "MEDIUM" | "LOW";

type EvidenceRef = {
  page: number;                 // 1-based
  quote: string;                // verbatim source text
  bbox?: [number, number, number, number]; // normalized x1,y1,x2,y2
};

type Fact<T> = {
  value: T | null;
  confidence: Confidence;
  evidence: EvidenceRef[];
};

type ReviewFlag = {
  code: string;
  severity: "INFO" | "WARNING" | "ERROR";
  field_path: string;
  message: string;
  evidence?: EvidenceRef[];
};
```

These rich primitives remain available for a future internal bank projection, but they are not required from the current AI HTTP service. The public extraction wire below uses flat values, `fieldsNeedingReview: string[]`, a top-level authority-clause evidence object, and per-rule evidence. Unknown or unreadable values are `null` and their field paths appear in `fieldsNeedingReview`; the model must not guess.

## 5.2 Extraction result

```ts
type AuthorityRule = {
  scope: string;                // e.g. general, credit, real_estate
  threshold: number | null;     // strict integer kuruş
  mode: "SOLE" | "JOINT" | null;
  coSigners: string[];          // representative IDs, e.g. rep-1
  blocked: boolean;
  evidence: {page: number; quote: string};
};

type Representative = {
  id: string;                   // stable document-order ID, e.g. rep-1
  name: string;                 // printed value
  nameNormalized: string;       // derived by AI Turkish normalization
  nationalId: string | null;    // masked only
  title: string | null;
  mode: "SOLE" | "JOINT";
  coSigners: string[];          // display names, deliberately not IDs
  limits: number | null;        // strict integer kuruş
};

type ExtractionResult = {
  schema_version: "1.0";
  document_id: string;
  company: {
    name: string;
    taxNumber: string | null;
    mersisNumber: string | null;
    legalNameNormalized: string;
  };
  notary: {
    name: string | null;
    date: string | null;
    yevmiye: string | null;
  };
  validUntil: string | null;
  representatives: Representative[];
  fieldsNeedingReview: string[];
  evidence: {authorityClause: string; page: number};
  rules: AuthorityRule[];
};
```

`representatives[].coSigners` contains human-readable names for reasons. `rules[].coSigners` contains stable representative IDs for machine enforcement. A blocked rule requires `mode: null` and an empty `coSigners` list. Every rule ID reference must resolve in the same extraction.

## 5.3 Onboarding analysis request and result

The analysis service receives four sources: extraction, application, verified branch identity, and current registry record.

```ts
type CheckStatus = "green" | "amber" | "red";
type OnboardingVerdict =
  | "READY"
  | "CO_SIGNER_REQUIRED"
  | "MISMATCH"
  | "REGISTRY_CONFLICT";

type CheckResult = {
  id: string;
  status: CheckStatus;
  title: string;
  reason: string;
  evidence: Record<string, string | number | boolean | null>;
};

type CheckReport = {
  verdict: OnboardingVerdict;
  checks: CheckResult[];         // exactly nine, in the defined order
};
```

The `/analyze` request is `{extraction, application, registry, as_of?}`. The application field sent to AI is `applicant_tckn`; the bank public API/database field remains `applicant_tckn_masked`. The AI registry is keyed by MERSİS and shaped as `{name,status,reps:[{name,tckn,mode,status}]}`. Unknown fields inside application/registry inputs are tolerated; AI responses are strict.

## 5.4 Registry record

```ts
type RegistryCompany = {
  mersis: string;
  legal_name: string;
  tax_number: string;
  status: "ACTIVE" | "INACTIVE";
  representatives: Array<{
    id: string;
    name: string;
    tckn: string;                // always masked, e.g. 123******01
    mode: AuthorityMode;
    status: "ACTIVE" | "REMOVED";
    effective_at: string;
  }>;
};
```

## 5.5 Transaction decision

```ts
type TransactionVerdict = "ALLOWED" | "PENDING_COSIGN" | "DENIED";

type TransactionDecision = {
  transaction_id: number;
  verdict: TransactionVerdict;
  required_cosigner: string | null;
  checks: Array<{
    status: CheckStatus;
    title: string;
    reason: string;
  }>;
  authorization_code: string | null;
  latency_ms: number;
  source: {
    authority_id: number;
    document_id: number;
    verified_at: string;
    channel: "BRANCH_ORIGINAL_SEEN";
  };
};
```

## 5.6 Authority record view

```ts
type AuthorityPerson = {
  id: string;
  source_id: string;
  name: string;
  tckn_masked: string;
  title: string;
  degree: string | null;
  valid_from: string | null;
  valid_until: string | null;
};

type AuthorityRecordView = {
  id: number;
  mersis: string;
  version: number;
  status: "ACTIVE" | "SUSPENDED";
  source_application_id: number;
  source_document_id: number;
  verified_at: string;
  verified_by: string;
  valid_until: string | null;
  persons: AuthorityPerson[];
  rules: AuthorityRule[];
};
```

## 5.7 Standard error body

All non-2xx API responses return:

```json
{
  "error": {
    "code": "DOCUMENT_REQUIRED",
    "message": "Bu başvuru için analiz edilecek belge yok.",
    "retryable": false,
    "details": {},
    "correlation_id": "..."
  }
}
```

Do not return stack traces, raw model responses, local paths, or secrets.

---

# 6. The nine onboarding checks

`ai/compare.py` owns and executes these checks behind `POST /analyze`. The bank API must not implement a second copy or alter the returned statuses/verdict.

Checks are returned in this exact order:

| # | ID | Rule |
|---|---|---|
| 1 | `company_name_match` | Turkish-aware normalized application name equals extracted name. Legal suffix differences may normalize; unrelated words may not. |
| 2 | `tax_number_match` | Ten normalized digits match exactly. Missing or malformed values are red. |
| 3 | `mersis_number_match` | Sixteen normalized digits match exactly. Missing or malformed values are red. |
| 4 | `applicant_in_document` | Applicant name resolves to exactly one extracted representative. Zero or multiple matches are red. |
| 5 | `identity_match` | Branch-verified masked TCKN and normalized name match the selected representative. Missing or contradictory identity evidence is red. |
| 6 | `authority_mode` | Green when the applicant can act alone for the onboarding action; amber when an active co-signer is required; red when authority is absent or out of scope. |
| 7 | `registry_status` | Registry company exists, matches the MERSİS number, and is active. Missing or inactive is red. |
| 8 | `registry_representative_match` | Applicant exists as an active current registry representative. Removed or missing is red. |
| 9 | `document_validity` | Document is valid on `as_of` (or the AI service's current date when omitted). Unknown or expired is red. |

`ai/normalize.py::tr_normalize()` is the primary join mechanism for names across document, application, and registry. Masked TCKN corroborates the selected normalized-name match but is not itself a join key. Normalization may handle Turkish casing, whitespace, punctuation, and known legal suffixes. It must never use broad fuzzy matching for VKN, MERSİS, masked TCKN, or monetary values. Golden normalization fixtures must also be used by any backend-side registry-name join so behavior cannot drift.

## 6.1 Verdict precedence

Apply precedence in this order:

1. `MISMATCH` when checks 1–5 contain a red result.
2. `REGISTRY_CONFLICT` when checks 7 or 8 are red and checks 1–5 are not red.
3. `MISMATCH` when check 6 or 9 is red for a document-side reason.
4. `CO_SIGNER_REQUIRED` when check 6 is amber and there are no red checks.
5. `READY` when there are no red checks and no authority-mode amber.

An amber validity result does not silently become approval. The UI enables correction or escalation, and the approval endpoint rejects it unless the reviewer has supplied a correction resolving the unknown date.

---

# 7. Persistence and state rules

## 7.1 Tables

Use SQLModel with explicit enums and UTC timestamps.

### `Application`

Fields from `PROJECT.md`, plus `updated_at` and `version`. Index `mersis` and `status`.

Statuses:

```text
DRAFT
IDENTITY_VERIFIED
DOCUMENT_SCANNED
ANALYZING
ANALYZED
APPROVED
DOC_REQUESTED
ESCALATED
ANALYSIS_FAILED
```

### `Document`

Add `mime_type`, `size_bytes`, and unique `sha256`. Store a workspace-relative path, never an arbitrary client path.

### `Extraction`

Store the raw AI payload verbatim. Unique key: `(document_id, schema_version, engine)`.

### `ExtractionCorrection`

Required because the UI offers field correction. Fields: `id`, `extraction_id`, `field_path`, `old_value_json`, `new_value_json`, `reviewer`, `reason`, `created_at`. Corrections are append-only.

### `CheckReport`

Store report payload verbatim and link it to both `application_id` and `extraction_id`. Re-analysis creates a new report only if inputs or effective extraction changed.

### `AuthorityRecord`

Add `version` and `superseded_by_id`. At most one document-derived active record may exist for a MERSİS number. Creating a new approved version suspends the old version in the same transaction. A mock-registry representative removal does not write through to this status; current registry state is joined at read/authorization time.

### `Transaction`

Persist request data including `amount_minor: INTEGER` and fixed `currency: TRY`, every verdict transition, required co-signer, authorization code, and measured latency. Authorization codes are unique and generated only for `ALLOWED` transactions. Float money columns are forbidden.

### `AuditLog`

Append-only. Record actor, action, entity, entity ID, correlation ID, and structured detail. Never update or delete audit rows during normal operation.

## 7.2 Application transitions

Only the service layer may transition state:

```text
DRAFT -> IDENTITY_VERIFIED
IDENTITY_VERIFIED -> DOCUMENT_SCANNED
DOCUMENT_SCANNED -> ANALYZING
ANALYZING -> ANALYZED | ANALYSIS_FAILED
ANALYSIS_FAILED -> ANALYZING
ANALYZED -> APPROVED | DOC_REQUESTED | ESCALATED | ANALYZING
```

Invalid transitions return `409 INVALID_STATE_TRANSITION`.

## 7.3 Transaction transitions

```text
REQUESTED -> ALLOWED | PENDING_COSIGN | DENIED
PENDING_COSIGN -> ALLOWED | DENIED
```

The co-sign endpoint is idempotent. Repeating the same accepted co-sign returns the existing `ALLOWED` decision and does not issue a second authorization code.

---

# 8. API specification

## 8.1 Infrastructure

| Method | Path | Success | Notes |
|---|---|---|---|
| GET | `/health` | 200 | Process and database health; do not require AI availability. |
| GET | `/ready` | 200/503 | Includes DB, data directory, and configured AI mode readiness. |

## 8.2 Demo control

| Method | Path | Success | Errors |
|---|---|---|---|
| POST | `/api/demo/load-case/{n}` | 201 `{application_id}` | 404 unknown case; 403 when demo mode disabled. |
| POST | `/api/demo/reset` | 200 `{ok:true}` | 403 when demo mode disabled. |

Reset restores database demo rows, runtime registry, and demo uploads. It must not delete files outside configured runtime directories.

## 8.3 Applications and documents

| Method | Path | Success | Important rules |
|---|---|---|---|
| POST | `/api/applications` | 201 `Application` | Validate identifiers; identity attestation is required to reach `IDENTITY_VERIFIED`. |
| POST | `/api/applications/{id}/document` | 201 `Document` | Multipart `file` and boolean `original_seen`; reject missing attestation, unsupported MIME, and oversized files. |
| POST | `/api/applications/{id}/analyze` | 200 `{extraction,report}` | Idempotent; concurrent calls share or reject the active run, never duplicate rows. |
| GET | `/api/applications/{id}` | 200 aggregate | Returns application, document, effective extraction, report, corrections, and authority if present. |
| PATCH | `/api/applications/{id}/extraction` | 200 aggregate | Inline edits are limited to the six closed-decision fields; preserve raw extraction, audit old/new values, and re-run `/analyze`. |
| POST | `/api/applications/{id}/decision` | 200 result | Actions: `approve`, `request_document`, `escalate`; actor is the fixed branch user. Amber approval requires typed `override_justification`. |
| GET | `/api/documents/{id}/page/{n}` | 200 PNG | Validate ownership and page range; no path passthrough. |

Approval preconditions:

- application is `ANALYZED`;
- `READY` is normally approvable;
- `CO_SIGNER_REQUIRED` is approvable only as an audited override with a non-empty typed justification;
- `MISMATCH` and `REGISTRY_CONFLICT` are never approvable in the MVP;
- all `ERROR` review flags are resolved;
- identity and original-document attestations are true;
- document and registry are re-checked inside the approval transaction;
- no active authority record has been created from the same application already.

## 8.4 Registry

| Method | Path | Success |
|---|---|---|
| GET | `/api/registry` | 200 full registry |
| PUT | `/api/registry/{mersis}/reps/{rep_id}` | 200 updated company |

The update body is `{status:"ACTIVE"|"REMOVED"}`. Writes use temp-file plus atomic rename. A process-level lock protects concurrent writes. The audit actor is `branch_user:kozyatagi01`.

## 8.5 Authority and transactions

| Method | Path | Success | Important rules |
|---|---|---|---|
| GET | `/api/authority/{mersis}` | 200 active record | 404 when none exists. |
| POST | `/api/transactions/authorize` | 200 `TransactionDecision` | Always persists the attempt and audit entry. |
| POST | `/api/transactions/{id}/cosign` | 200 `TransactionDecision` | Body identifies the co-signer; re-runs all current checks. |
| GET | `/api/transactions?mersis=` | 200 list | Newest first; demo-sized response is unpaginated. |

## 8.6 AI service contract

The AI engineer owns the service. `ai/compare.py` implements the nine checks behind `/analyze`; the extraction endpoint remains an external delivery dependency.

The private AI endpoints are:

| Method | Path | Input | Output |
|---|---|---|---|
| GET | `/health` | none | `{status,engine,schema_version}` — implemented |
| POST | `/analyze` | JSON `{extraction,application,registry,as_of?}` | `CheckReport` — implemented |
| POST | `/extract` | Multipart `file` and `document_id` | `ExtractionResult` — pending |

`/analyze` is deterministic code. It must not ask a language model to choose the verdict. The API projects the current bank registry into the AI's keyed request. The AI service never reads registry/application files or database rows and never writes a cache. A malformed `/analyze` body deliberately returns HTTP 200 with `MISMATCH` and all nine checks red; consumers must inspect `verdict`, not treat every 200 as a successful business result. `GET /health` is infrastructure only.

## 8.7 Exact mutation request bodies

```ts
type CreateApplicationRequest = {
  company_name: string;
  tax_number: string;
  mersis: string;
  applicant_name: string;
  applicant_tckn_masked: string;
  branch_code: string;
  identity_verified_at_branch: boolean;
};

// POST /api/applications/{id}/document is multipart/form-data:
// file: File
// original_seen: "true" | "false"
// scanned_by: string

type ExtractionCorrectionRequest = {
  reason: string;
  corrections: Array<{
    field_path: string;          // exact six-field server-side allowlist
    expected_old_value: unknown; // optimistic concurrency guard
    new_value: unknown;
  }>;
};

type ApplicationDecisionRequest = {
  action: "approve" | "request_document" | "escalate";
  note?: string;
  override_justification?: string; // required only for CO_SIGNER_REQUIRED approval
};

type RegistryRepresentativeUpdateRequest = {
  status: "ACTIVE" | "REMOVED";
};

type AuthorizeTransactionRequest = {
  mersis: string;
  subject: TransactionSubject;
  currency: "TRY";
  amount_minor: number;          // non-negative integer kuruş
  initiator: string;             // authority person ID, not a display name
};

type CosignTransactionRequest = {
  cosigner: string;              // authority person ID
};
```

Mutation validation rules:

- reject unknown object keys in API request models;
- trim display strings but never silently rewrite identifiers;
- validate `tax_number` as exactly 10 digits and `mersis` as exactly 16 digits;
- validate masked TCKN format without attempting to recover hidden digits;
- reject negative, non-integer, unsafe-integer, or out-of-range `amount_minor` values;
- restrict correction paths and validate the new value against the extraction schema;
- compare `expected_old_value` before applying a correction and return `409 STALE_CORRECTION` if it changed.

The only accepted correction paths are:

```text
company.name
company.taxNumber
company.mersisNumber
representatives[<source_id>].name
representatives[<source_id>].mode
validUntil
```

`<source_id>` resolves against the immutable representative source ID, never an array position or display name.

## 8.8 External AI delivery and integration acceptance

This track does not implement the extractor, prompts, comparison engine, or AI service. The AI engineer delivers and operates them. The following behavior is an external contract that backend/frontend integration must validate:

1. `/extract` is still pending; live readiness must remain blocked until it accepts the agreed multipart fields and returns `ExtractionResult`.
2. The delivered response uses verbatim evidence, `null` for unreadable values, distinct sole/joint modes, integer-kuruş limits, and stable representative source IDs.
3. Every representative reference resolves or remains visibly flagged; it is never silently dropped.
4. Top-level authority-clause and per-rule evidence carry positive page numbers and non-empty verbatim quotes.
5. Turkish monetary text such as `1.200.000,50` is returned as `120000050` minor units; uncertain conversion is `null` plus a review flag.
6. `/analyze` accepts extraction, application, and registry JSON and returns the deterministic nine-check `CheckReport`.
7. The service reads no backend file/database/cache; malformed `/analyze` input degrades to a visible all-red report.

The bank API caches validated `/extract` responses by `(document_sha256, schema_version, engine)`. The deterministic `/analyze` endpoint applies section 6 to the extraction, application, and registry payloads supplied by the API. Extraction confidence may create review flags but may not directly change verdict precedence outside the defined check rules.

Integration assertions against the AI engineer's delivered service and fixtures:

- case 1 returns both representatives and all four source-backed rules;
- case 2 preserves joint authority and names the required co-signer;
- case 3 preserves the Zeta company identity rather than adapting it to the application;
- missing or unreadable values become `null` with review flags;
- the API cache returns schema-identical validated data for repeated extraction of the same hash while the AI service remains stateless.

If an assertion fails, the full-stack agent records the request/response contract defect and hands it to the AI engineer. It must not patch files under `ai/`.

---

# 9. Authority-record construction and transaction engine

## 9.1 Authority construction

On approval, within one database transaction:

1. Load raw extraction and ordered corrections.
2. Build the effective extraction.
3. Revalidate references between representatives and rules.
4. Reject unresolved signer references.
5. Map representative source IDs to stored authority-person IDs.
6. Copy reviewed rules without broadening scope or limits.
7. Save source application, source document, reviewer, verification timestamp, and validity.
8. Supersede any older active record for the same MERSİS number.
9. Append an audit event.
10. Commit all changes atomically.

## 9.2 Authorization algorithm

For every transaction, in this order:

1. Load the active authority record for MERSİS; otherwise deny.
2. Resolve the initiator as exactly one authority person; otherwise deny.
3. Re-read the runtime registry and confirm the company and initiator are active; otherwise deny.
4. Confirm the authority record, representative, and applicable rule are not expired; otherwise deny.
5. Select rules matching the transaction subject, fixed `TRY` currency, and integer `amount_minor` range.
6. If no allowed rule matches, deny as out of scope.
7. If the rule is satisfied by the initiator alone, allow and issue an authorization code.
8. If exactly one additional active signer can satisfy it, create `PENDING_COSIGN` naming that signer.
9. Otherwise deny and explain which required authority is missing.

Every step appends a human-readable check. Latency is measured with a monotonic timer around the full authorization service call; it is never hardcoded.

## 9.3 Co-signing

The co-sign endpoint must:

- require the transaction to be `PENDING_COSIGN`;
- reject the initiator as their own co-signer;
- require the named co-signer to match the pending requirement;
- re-read registry state and rule validity;
- deny if the transaction or authority changed since request time;
- issue one authorization code only after all checks pass;
- record both the pending and completed states in the audit trail.

---

# 10. Frontend specification

## 10.1 Shared rules

- `web/lib/api.ts` is the only file allowed to call `fetch`.
- `web/lib/types.ts` mirrors the frozen contracts.
- Business verdicts come only from the API. Components never calculate them.
- `web/lib/format.ts` formats `amount_minor` only at the display edge with `Intl.NumberFormat('tr-TR', {style:'currency', currency:'TRY'})`; components never divide/format money ad hoc.
- Registry-derived content carries a visible `SimBadge`.
- All async views have loading, retryable error, non-retryable error, and empty states.
- Green/amber/red status is communicated by icon and text, not color alone.
- Turkish copy is the user-facing default.

### Visual design authority

- `docs/fbdocs/design/DESIGN_SYSTEM.md` and `docs/fbdocs/design/nexai-dashboard-reference.png` define the shared application shell and visual language for every route.
- The PNG is a style reference, not a product template. Do not copy its NexAI branding, navigation names, charts, metrics, hypotheses, or product copy.
- Apply its pale-gray canvas, rounded white shell, grouped left sidebar, compact top bar, restrained borders/shadows, typography, cards, controls, cyan/pink/violet accents, and whitespace to YetkiCheck.
- Preserve the route scope and product-specific workflow surfaces defined in this plan and `index.html`.
- Semantic green/amber/red outcomes always take precedence over decorative accent colors.
- Global colors, typography, radii, spacing, shadows, shell anatomy, and responsive navigation are centralized; route components must not create independent visual systems.
- The shared shell must work across `/`, `/branch`, `/mobile`, `/authority/[mersis]`, and `/registry`, with the active navigation state derived from the current route.
- A screenshot cannot prove an original font file, so Inter is the frozen closest-match UI family unless an original CSS/Figma source is deliberately accepted later. Use an offline-safe local font asset for the judged build.

## 10.2 `/` — demo control

- Four case cards with expected outcome labels.
- Flow strip matching `index.html`.
- Keys 1–4 load cases when focus is not inside an input.
- Skip-to-Act-2 invokes a backend demo endpoint or loads a committed pre-approved fixture; it must not set client-only approval state.
- Reset button returns the entire demo to baseline.

## 10.3 `/branch`

The application ID is encoded in the URL query, not kept only in component memory.

Step 1:

- Prefilled application fields for demo cases.
- Required identity attestation.
- Server validation errors rendered by field.

Step 2:

- File selection/scan simulation.
- Visible file name, size, page count, and thumbnail.
- Required original-seen attestation.
- Upload progress and retry.

Step 3:

- Verdict banner at the top.
- Split document/results view.
- Extracted fields first, then nine checks, then verdict.
- Expandable evidence and page navigation.
- Highlight source evidence when a field or check is selected.
- Normal approval button enabled only for `READY`; `CO_SIGNER_REQUIRED` shows a separate audited-override action with mandatory typed justification.
- The six allowed fields become inline-editable; save sends typed corrections with reason, while the backend assigns the fixed branch reviewer.
- Successful approval shows the authority-record hinge card and mobile link.

Animation may delay visual reveal, but it must not delay or alter the actual API result.

## 10.4 `/mobile`

- Gate access when no authority record exists.
- Person switcher for Ali and Ayşe.
- Four preset transaction cards.
- Short authorization-in-progress state.
- Decision card uses backend checks verbatim.
- Pending transaction displays a notification dot on the required co-signer.
- Co-signer action calls the backend; no client-only completion.
- Allowed decision shows authorization code, source, verification date, and measured latency.
- Denied decision shows a plain-language next step.

## 10.5 `/authority/[mersis]`

- Source document and branch verification metadata.
- Authority version and status.
- People with current registry status.
- Rules table with subject, range, required signers, and validity.
- Transaction/audit history.

## 10.6 `/registry`

- Clear simulated-service notice.
- Company-grouped representative table.
- Remove/restore action with confirmation.
- Large type and contrast suitable for projection.
- Raw JSON panel only in demo mode.

---

# 11. Golden fixture specification

All fixture names, IDs, documents, extraction payloads, reports, and expected decisions are committed. Stub and replay modes use these same files.

## 11.1 Onboarding cases

### Case 1 — clean and Act-2 capable

- ABC Teknoloji Ltd. Şti.
- Ali Yılmaz and Ayşe Demir both appear in the document and registry.
- Registry IDs are `rep_abc_ali` and `rep_abc_ayse`; matching still uses normalized names plus masked-TCKN corroboration.
- Rules in the source document:
  - general transactions up to and including 500,000 TL (`50000000` minor): Ali may sign alone;
  - general transactions above `50000000` minor: Ali and Ayşe jointly;
  - credit at any amount: Ali and Ayşe jointly;
  - real estate: not authorized.
- Expected verdict: `READY`.

This synthetic fixture is deliberately Act-2 capable so the stage can connect branch approval to mobile enforcement. Its people, limits, subjects, and expected results are fixture data processed by the generic engines; none of them may be embedded as product constants.

### Case 2 — always joint

- ABC company and identity fields match.
- Application has only Ali present.
- Applicable onboarding authority requires Ali and Ayşe jointly.
- Expected verdict: `CO_SIGNER_REQUIRED`.
- Normal actions are request document or escalate. No branch second-signer flow is built. Approval exists only as a typed, audited amber override.

### Case 3 — application mismatch

- Application is for ABC Teknoloji and Mehmet Kaya.
- Document belongs to Zeta İnşaat and names Kemal Öz.
- Expected verdict: `MISMATCH` with multiple red checks.

### Case 4 — stale authority

- Same clean document as case 1.
- Runtime registry marks Ali `REMOVED`.
- Expected verdict: `REGISTRY_CONFLICT`.

## 11.2 Transaction cases

Using the authority record created from case 1:

| Transaction | API amount | Expected initial result | Expected completion |
|---|---|---|---|
| General, 250,000 TL, Ali | `amount_minor=25000000` | `ALLOWED` | authorization code issued |
| General, 1,200,000 TL, Ali | `amount_minor=120000000` | `PENDING_COSIGN` | Ayşe co-signs -> `ALLOWED` |
| Credit, 750,000 TL, Ali | `amount_minor=75000000` | `PENDING_COSIGN` | Ayşe co-signs -> `ALLOWED` |
| Real estate, 0 TL, Ali | `amount_minor=0` | `DENIED` | new authority/document required |

Additional mandatory fixture assertion: after Ali is removed from the registry, the first transaction returns `DENIED` even though the stored authority record remains active.

---

# 12. Phase-by-phase implementation plan

This section is the primary execution plan. It follows the same Phase 0–8 timeline and step-based structure as `PROJECT.md`. Detailed contracts elsewhere in this document define what each step must implement.

The decision register is closed. Every phase below implements those decisions directly. Any later change must update the affected contract, fixture, phase, and acceptance criteria before coding continues.

---

## Phase 0 — Foundations and contract freeze (H0–H4)

**Goal:** create the full-stack repository skeleton, freeze integration contracts, and commit reproducible golden fixtures so backend/frontend work can proceed without editing or waiting on AI-service implementation.

### Contract confirmation

Before the end of H1, both engineers confirm the closed decisions in section 1.5, especially AI ownership/endpoints, amber override behavior, fixed identities, stable registry IDs, minor-unit money, and fixture deadlines. These are confirmations, not open design work.

### Shared architecture steps

1. Create `web/`, `api/`, `data/`, `scripts/`, and required ignore rules. Do not scaffold or modify `ai/`.
2. Create root and service-level README instructions with stable developer commands from section 4.4.
3. Freeze enum values, JSON field names, evidence format, error format, date format, and identifier format.
4. Receive the AI engineer's `ai/schema.py`, then mirror its JSON contract in `api/schemas.py` and `web/lib/types.ts` without editing the AI-owned file.
5. Add backend/frontend contract tests that load the AI engineer's delivered fixtures without network access.
6. Define environment examples without real keys or machine-specific paths.

### Backend steps

1. Create the FastAPI application factory, configuration validation, CORS allowlist, `/health`, and `/ready`.
2. Create SQLModel tables, enums, UTC timestamp helpers, and the SQLite session lifecycle.
3. Implement safe database initialization and seed/reset services.
4. Implement the audit-service interface even if only foundation events use it initially.
5. Add `DEMO_MODE` guards around demo-only endpoints.
6. Confirm reset targets resolve only inside the configured runtime data directories.
7. Define `AI_MODE=stub|live|replay`, `EXTRACTION_CACHE=on|off`, and the backend-owned cache-key format in `api/services/ai_client.py`.

### External AI delivery gates — not implemented by this track

1. AI engineer delivers the two endpoint contracts and `/health` behavior.
2. AI engineer delivers `ai/schema.py`, extraction fixtures, deterministic report fixtures, and synthetic notarial text by the agreed deadlines.
3. Full-stack agents validate those deliveries as inputs and report contract defects; they do not implement or patch AI code/prompts.

### Data and fixture steps

1. Full-stack engineer writes `data/fixtures/cases.json` with the four applications and expected verdicts.
2. Write `data/registry.seed.json` with stable company and representative IDs.
3. AI engineer delivers final notarial Turkish text for all four synthetic documents by H2.
4. Full-stack engineer renders that text to PDFs and page PNGs by H4.
5. Ensure the clean synthetic fixture contains the source-backed people/rules needed by the Act 2 examples, without adding any case-aware branch to business code.
6. Full-stack engineer prints and re-photographs at least one synthetic document by H4.
7. AI engineer commits `ai/schema.py` and `ai/tests/fixtures/case{1..4}.json` by H4.
8. As part of `ai/compare.py` golden tests, AI engineer exports the deterministic `CheckReport` outputs used by the backend's offline stub/replay path.
9. Backend stub and AI golden tests read the same committed extraction/report fixtures; neither engineer changes them alone after H4.
10. Confirm all people and identifiers use the fixed fictional cast and masked values from section 1.5.

### Frontend steps

1. Scaffold Next.js with TypeScript and Tailwind.
2. Commit the supplied visual reference and freeze `docs/fbdocs/design/DESIGN_SYSTEM.md`; use it for the global shell, typography, colors, sidebar, top bar, cards, controls, spacing, and responsive behavior.
3. Preserve only the YetkiCheck-specific presentation primitives from `index.html`: document-paper styling, semantic status treatments, branch workflow, evidence/check presentation, and phone frame.
4. Add the route skeleton for control, branch, mobile, authority, and registry.
5. Create `web/lib/api.ts`, `web/lib/types.ts`, and formatting helpers.
6. Add empty/loading/error primitives and shared status components.

### Integration steps

1. Confirm ports 3000, 8000, and 8001 are configurable and non-conflicting.
2. Verify both demo machines can reach the API or document the hotspot/single-machine fallback.
3. Record the web/API start order and how to point `AI_URL` at the AI engineer-operated service; do not add AI startup ownership to full-stack scripts.

### Done when

- [ ] All closed decisions are reflected in contracts, fixtures, and task ownership.
- [ ] Shared fixtures validate against Python and TypeScript contracts.
- [ ] The database can be created and reset in under two seconds.
- [ ] Four documents, page images, extraction fixtures, and report fixtures exist.
- [ ] The committed visual reference and `DESIGN_SYSTEM.md` are readable and frozen for frontend agents.
- [ ] Web and API skeletons expose controlled health/readiness behavior, and API readiness reports external AI reachability without owning its process.
- [ ] No secrets, runtime uploads, database files, or mutable registry files are tracked.
- [ ] Both machines can reach the chosen runtime layout, or the fallback is proven.

---

## Phase 1 — Walking skeleton (H4–H10)

**Goal:** make the branch intake persist real server state and return a complete stub extraction/report through the final API contracts.

### Dependencies

- Phase 0 contracts and fixtures are frozen.
- Stub extraction and report JSON validate successfully.
- The post-Phase-0 visual handoff is frozen in `docs/fbdocs/design/DESIGN_SYSTEM.md`, and the reference PNG is committed beside it.

### Backend steps

1. Implement `POST /api/applications` with identifier validation and identity-attestation handling.
2. Implement application transition `DRAFT -> IDENTITY_VERIFIED` and audit it.
3. Implement multipart document upload with MIME/size checks, SHA-256, safe filenames, page count, and original-seen attestation.
4. Render and store document page PNGs; implement the validated page-serving endpoint.
5. Implement the typed AI client with stub/live/replay branches and backend-owned extraction cache behind one interface.
6. Implement analysis orchestration:
   - verify state and document presence;
   - transition to `ANALYZING`;
   - obtain a validated extraction through the configured mode: committed fixture in stub/replay, AI `POST /extract` in live mode only after that endpoint is delivered;
   - load the current registry snapshot and call AI `POST /analyze` with extraction, application, and registry;
   - validate and persist raw payloads;
   - transition to `ANALYZED` or `ANALYSIS_FAILED`;
   - write audit events.
7. Make analysis idempotent and guard against concurrent duplicate runs.
8. Implement the application aggregate endpoint.
9. Implement demo case load and reset endpoints.

### External AI contract checks — not implementation steps

1. Validate the delivered extraction/report fixtures against backend schemas.
2. Confirm `/health` and `/analyze` against the documented examples; keep `/extract` marked pending and live readiness blocked until delivery.
3. Record any mismatch for the AI engineer; do not modify `ai/compare.py`, AI schemas, prompts, or endpoint code.

### Frontend steps

1. Implement the shared visual foundation from `DESIGN_SYSTEM.md`: centralized tokens, Inter typography, rounded application shell, grouped persistent sidebar, compact top bar/breadcrumbs, panels, cards, controls, and responsive navigation.
2. Build the control panel with four case cards and the flow strip inside that shared shell; adapt YetkiCheck content rather than copying the reference dashboard's product content.
3. Load a case through the backend and route using the persistent application ID.
4. Build branch step 1 with company/applicant fields and required identity attestation.
5. Build branch step 2 with file/scan presentation, upload progress, thumbnail, and required original-seen attestation.
6. Drive the stepper from backend application status, not local completion guesses.
7. Show recoverable API errors without losing the current application ID.

### Review and verification steps

1. Verify invalid identifiers, missing attestations, missing document, unsupported MIME, oversized upload, and invalid page number.
2. Call analyze twice and confirm only one extraction/report pair exists.
3. Refresh the browser at each branch step and confirm progress restores from the server.

### Done when

- [ ] Loading case 1 creates a persistent application and opens `/branch` with prefilled fields.
- [ ] Both attestations are enforced by the backend.
- [ ] Upload creates a document row with hash, page count, and safe stored path.
- [ ] Analyze in stub mode persists one extraction and one nine-check report.
- [ ] Refresh does not reset branch progress.
- [ ] All errors use the standard error contract and expose no stack trace.
- [ ] All five route skeletons render inside the shared design-system shell, and `/` plus `/branch` match the reference's visual character without copying its content.

---

## Phase 2 — Review screen, decisions, and registry (H10–H16)

**Goal:** complete the hero review experience, make human actions real, and create an authority record only through the agreed approval rules.

### Dependencies

- Phase 1 aggregate endpoint returns application, document, extraction, report, and correction state.
- The fixed branch actor, correction allowlist, verdict approval matrix, and stable registry IDs are present in the shared contract.

### Backend steps

1. Implement the effective-extraction builder that applies ordered corrections without changing raw AI payloads.
2. Implement the typed correction endpoint for exactly company name, tax number, MERSİS, representative name, representative mode, and `validUntil`, with reason, schema validation, and optimistic concurrency.
3. Audit each correction as `branch_user:kozyatagi01` with field, old value, and new value.
4. Send effective extraction, application, and current registry to AI `POST /analyze` after every accepted correction so checks visibly re-resolve.
5. Implement decision actions: approve, request document, and escalate.
6. Allow normal approval for `READY`; allow `CO_SIGNER_REQUIRED` only with a typed audited override justification; reject approval of `MISMATCH` and `REGISTRY_CONFLICT`.
7. Implement authority-record construction:
   - use the reviewed effective extraction;
   - resolve all signer references;
   - copy rules without broadening them;
   - link source application/document/reviewer;
   - create or supersede atomically;
   - audit the action.
8. Implement registry read and `PUT /api/registry/{mersis}/reps/{rep_id}` using stable fixture IDs.
9. Write runtime registry changes using a lock, temp file, and atomic rename.
10. Re-read registry and validity inside the approval operation.

### Frontend steps

1. Build the review header and top verdict banner.
2. Build the responsive split layout: document at left, extracted results at right.
3. Build document page tabs and source-clause highlighting.
4. Render extracted fields with review flags.
5. Render exactly nine check rows in API order with icon, title, reason, and expandable evidence; never recompute their result in the frontend or bank API.
6. Mark registry-derived checks as simulated.
7. Implement the visual sequence: fields, checks, verdict, evidence flash.
8. Make the six allowed extracted fields inline-editable and show checks resolving again after save.
9. Wire new-document and escalation actions; do not add a branch second-signer flow.
10. Enable ordinary approval only for `READY`.
11. For `CO_SIGNER_REQUIRED`, replace the mock `confirm()` with a required typed-justification textarea and visibly label the action as an audited override.
12. Show the authority-created hinge panel and link to mobile.
13. Build the registry screen with stable-ID remove/restore controls and simulated-service notice.

### Integration and data validation steps

1. Confirm only the six closed-decision correction fields are accepted by the schema/API allowlist.
2. Validate that delivered AI reports contain useful evidence labels and document references; report defects to the AI engineer rather than patching AI code.
3. Confirm case 4 changes result after registry mutation and re-analysis.

### Review and verification steps

1. Verify raw extraction does not change after correction.
2. Verify correction actor/reason and all decisions appear in audit logs.
3. Verify repeated approval does not create duplicate authority records.
4. Verify amber override is impossible without typed justification and creates an exceptional audit event.
5. Verify `MISMATCH` and `REGISTRY_CONFLICT` remain unapprovable even if a client crafts the request.
5. Test the layout at 1280x800 before adding further polish.

### Done when

- [ ] All four fixture reports render with correct checks, evidence, and verdict style.
- [ ] Evidence interaction selects the correct document page/clause.
- [ ] Human actions call real backend endpoints.
- [ ] Raw AI payload remains immutable.
- [ ] Six-field correction is saved, audited, and re-analyzed by AI `/analyze`.
- [ ] Case 2 has no branch co-signer workflow; its normal actions are request document or escalation.
- [ ] Amber override uses a typed justification and permanent audit entry rather than `confirm()`.
- [ ] Approval creates one source-backed authority record atomically.
- [ ] Registry removal and restoration survive refresh and do not corrupt JSON.
- [ ] The branch-to-mobile hinge is visible and functional.

---

## Phase 3 — Real AI integration (H16–H24)

**Goal:** process at least case 1 through the live extraction path without changing any frontend or bank-API contract, then prove replay fallback.

### Dependencies

- Phase 2 works entirely in stub mode.
- The AI engineer has deployed/started the delivered service and provided a reachable `AI_URL`; model credentials remain AI-owned.
- Backend-owned extraction cache is enabled and can be cleared/pre-warmed per document hash.

### External AI delivery gate — not implemented by this track

1. Confirm `/health` and `/analyze`, then separately verify that `/extract` has been delivered before setting `AI_EXTRACT_AVAILABLE=true`.
2. Validate delivered live responses against backend schemas and golden fixtures.
3. File contract/output defects with the AI engineer. Full-stack agents do not edit AI preprocessing, model calls, prompts, retries, normalization, comparison, or service code.

### Backend integration steps

1. Set `AI_MODE=live`, `EXTRACTION_CACHE=on`, and run case 1 through the existing orchestration path.
2. Resolve seam issues for Turkish filenames, masked identifiers, date formats, null fields, page numbering, and authority-rule references.
3. Enforce the configured timeout and translate AI errors into retryable application errors.
4. Confirm failed live analysis leaves the application recoverable.
5. Confirm the second analysis of the same document uses cache/replay as intended.

### Frontend steps

1. Render the same review UI for live and stub payloads.
2. Keep document thumbnails visible during slow analysis.
3. Show deliberate stage progress text without fabricating completed AI stages.
4. Show a calm retry/replay option after a live failure; replay is fallback only and must be labeled honestly.

### Review and verification steps

1. Compare live case-1 extraction field-by-field with the golden truth.
2. Confirm every non-null legal fact has document evidence.
3. Confirm no unknown name, date, or amount is silently guessed.
4. Pre-warm cases 2–4, clear case 1, and verify case 1 makes a genuine live extraction call.
5. Simulate AI unavailability from the API side, or coordinate a temporary stop with the AI engineer, and confirm replay still reaches the same review UI; the full-stack track does not manage the AI process.

### Done when

- [ ] Case 1 completes end to end through the live model within the agreed demo limit.
- [ ] The live response validates against the frozen schema.
- [ ] Stub, live, and replay require no frontend branch.
- [ ] Cache hit and AI-down replay are proven.
- [ ] The AI service remains stateless and restartable; cache state belongs to the bank API.
- [ ] Integration state is saved before the planned rest period.

---

## Phase 4 — All four onboarding cases and demo controls (H24–H30)

**Goal:** make every onboarding scenario reproducible, resettable, and understandable from the control panel.

### Dependencies

- Case 1 works in live and replay modes.
- All golden fixtures and registry patches are finalized.

### Backend steps

1. Validate and persist `fieldsNeedingReview` paths for all cases.
2. Finish one-call demo reset for rows, runtime registry, and demo uploads.
3. Make case loading deterministic in any order.
4. Return controlled conflicts for analyze-without-document, analyze-in-wrong-state, and stale correction.
5. Ensure loading case 4 applies its registry patch without affecting later reset baseline.

### AI integration and fixture validation steps

1. Run or replay all four source documents.
2. Compare results with golden extraction and report JSON.
3. Report prompt/schema defects to the AI engineer with reproducible inputs and expected contract behavior; do not edit AI code or special-case a verdict in backend/frontend code.
4. Confirm case 3 produces multiple specific mismatch checks rather than one generic failure.

### Frontend steps

1. Add case keyboard shortcuts 1–4 outside text inputs.
2. Add visible reset and case-loading states.
3. Verify all four verdict banners, check rows, and action availability.
4. Add analysis failure and retry/replay cards.
5. Ensure loading a new case clears prior visual state while server reset remains authoritative.

### Review and verification steps

1. Run cases in order 1-2-3-4, then 4-1-3-2.
2. Reset between runs and compare database row counts and registry hash.
3. Time every case and record live versus replay duration.

### Done when

- [ ] Case 1 returns `READY`.
- [ ] Case 2 returns `CO_SIGNER_REQUIRED`, offers request-document/escalation as normal actions, and exposes only the typed audited override as an exceptional approval path.
- [ ] Case 3 returns `MISMATCH` with company/person evidence.
- [ ] Case 4 returns `REGISTRY_CONFLICT` and can be restored to clean by registry change plus re-analysis.
- [ ] Reset returns the exact baseline in one action.
- [ ] Every case completes within the agreed stage time or transparently uses replay.

---

## Phase 5 — Act 2 authority enforcement (H30–H34)

**Goal:** enforce the approved authority record on mobile transactions, complete a real server-side co-signature, and show the bank-side audit record.

### Dependencies

- The clean demo fixture creates a source-backed authority through the same generic approval path used for any valid extraction.
- Fixed fictional mobile identities, integer-minor-unit money, and live registry join behavior are present in the contracts.
- Registry mutations and audit logs are stable.

### Backend steps

1. Implement the authority engine in the exact order defined in section 9.2.
2. Load the active authority record and resolve the selected fixed-cast initiator by stable authority-person ID.
3. Re-read the registry for every authorization request.
4. Check authority, person, rule, and document validity.
5. Select subject/`amount_minor` rules using SQLite/Python integers only; currency is fixed to `TRY` and no float conversion is allowed.
6. Return `ALLOWED`, `PENDING_COSIGN`, or `DENIED` with human-readable checks.
7. Measure real latency around the full service call.
8. Generate a unique authorization code only for `ALLOWED`.
9. Persist every attempt and audit event.
10. Implement the co-sign endpoint:
    - validate pending state;
    - reject self/wrong/removed co-signers;
    - re-run current registry and validity checks;
    - transition idempotently;
    - issue only one authorization code.
11. Implement authority and transaction-history endpoints.

### Frontend steps

1. Gate mobile when no authority record exists.
2. Build Ali/Ayşe simulated identity switcher from the fixed cast and clearly label it as simulated.
3. Build four preset transaction cards.
4. Render authorization progress and backend decision checks verbatim.
5. Show authorization code, source document, branch verification, and measured latency for allowed transactions.
6. Show a notification dot and co-sign card on Ayşe's phone for pending transactions.
7. Complete co-sign through the backend and restore final state after refresh.
8. Show plain-language next steps for denial.
9. Build the authority view with source, version, people, current registry status, rules, and audit history.

### Review and verification steps

1. Test the demo fixture's exact 500,000 TL boundary while confirming the engine reads that boundary from the authority rule rather than a code constant.
2. Test wrong, duplicate, self, and removed co-signers.
3. Remove Ali after an earlier approval and confirm a new transaction is denied by the live registry check while the document-derived authority record itself remains unchanged.
4. Confirm both pending and completed states appear in the audit trail.
5. Confirm no decision is calculated in React.

### Done when

- [ ] Mobile is inaccessible before a server-side authority record exists.
- [ ] General 250,000 TL is allowed with a real authorization code.
- [ ] General 1,200,000 TL requires Ayşe and completes after one valid co-sign.
- [ ] Credit 750,000 TL requires the configured joint rule.
- [ ] Real estate is denied from source-backed scope rules.
- [ ] Registry removal blocks later transactions immediately.
- [ ] Authority and audit screens show the entire decision chain.

---

## Phase 6 — Resilience, security, and polish (H34–H40)

**Goal:** make the demonstrated path safe, repeatable, offline-capable, and projector-ready.

### Backend integration and resilience steps

1. Complete replay mode using cached validated outputs through the normal code path.
2. Run the full demo with `AI_URL` unavailable or a stop coordinated by the AI engineer; do not manage or modify the AI service from this track.
3. Harden reset so it restores database, registry, uploads, and pre-approved rehearsal state safely.
4. Verify registry writes are atomic under concurrent requests.
5. Verify upload path containment, MIME/size limits, CORS, demo-route guards, and secret handling.
6. Redact identifiers and document content from logs and errors.
7. Ensure audit-write failure rolls back the associated business action.
8. Add correlation IDs and structured duration logs.

### Frontend steps

1. Focus polish on branch review, mobile, authority, and registry demo states.
2. Compare all five routes against `DESIGN_SYSTEM.md` and the committed reference image; confirm one consistent sidebar, top bar, typography, palette, card language, spacing, and responsive shell.
3. Verify 1280x800 projector layout, font size, contrast, and no horizontal overflow.
4. Verify status meaning is available without color.
5. Verify Turkish characters, dates, numbers, and filenames display correctly.
6. Remove console errors and unhandled promise rejections.
7. Confirm every async state has loading, empty, retryable error, and terminal error UI.
8. Freeze nonessential visual work at H40.

### End-to-end verification steps

1. Run the required unit, API integration, and frontend smoke coverage from section 13.
2. Perform five reset-and-demo runs using replay.
3. Perform at least one complete live run.
4. Test AI timeout, AI shutdown, registry read failure, and browser refresh during pending co-sign.

### Done when

- [ ] The full demo works with AI and external network unavailable.
- [ ] Reset is safe, deterministic, and under two seconds.
- [ ] No sensitive data or stack traces appear in logs/UI.
- [ ] No demonstrated route produces a console error or unhandled failure.
- [ ] Projector and accessibility checks pass.
- [ ] Every route uses the same frozen shell/tokens and reproduces the reference's visual character without NexAI branding or unrelated product content.
- [ ] Only demo-path defects remain eligible for changes.

---

## Phase 7 — Rehearsal and evidence (H40–H46)

**Goal:** prove the story, timing, recovery behavior, and speaker handoff under presentation conditions.

### Rehearsal steps

1. Use the runbook in section 16 and rehearse all eleven beats five times.
2. Assign one person to click and one person to speak; do not swap during the judged run.
3. Time every beat using the fixed stage policy: case 1 live with cleared cache, cases 2–4 cached real results, replay only on failure.
4. Remove or cache anything that exceeds its time budget; do not rush the explanation.
5. Rehearse case 4 and the final registry-removal transaction denial.
6. Rehearse AI timeout and complete the flow using replay without contract/UI changes.
7. Record a complete backup screen video and copy it to both machines and a phone.
8. Print or save the exact truthful statement describing real versus simulated components.
9. Verify the clean reset/start sequence can be followed by someone who did not write it.

### Done when

- [ ] Five consecutive rehearsals complete successfully within the presentation limit.
- [ ] Live and fallback paths have both been rehearsed.
- [ ] Backup video and second-machine copy are available offline.
- [ ] Speaker/clicker responsibilities and recovery cues are fixed.
- [ ] No new features are accepted.

---

## Phase 8 — Buffer and presentation readiness (H46–H48)

**Goal:** preserve a known-good build and remove operational risk.

### Steps

1. Make no code changes unless the current build cannot complete the demo.
2. Charge both laptops and phones; pack chargers and adapters.
3. Test the actual projector resolution and browser zoom.
4. Confirm system time/timezone and disable disruptive notifications or updates.
5. Run the safe reset once and verify baseline registry state.
6. Start services in the documented order and preload case 1.
7. Keep replay fixtures, backup video, and a copy of the repository available offline.
8. Do not update dependencies, model names, or operating-system packages.

### Done when

- [ ] The known-good build is loaded and untouched.
- [ ] Health/readiness checks pass.
- [ ] Case 1 and registry baseline are ready.
- [ ] Offline recovery assets are locally available.

---

# 12A. Agent-sized task reference

The following task cards refine the phases above. Each task is small enough for one coding agent. An agent must not start a task until all dependencies are complete.

## Task group 0 — contracts and foundations

### `P0-01` Scaffold repository

- **Dependencies:** none
- **Deliverables:** `web/`, `api/`, `data/`, ignore rules, environment examples, health endpoints.
- **Acceptance:** both apps import/start with documented commands; no feature code; no secrets committed.

### `P0-02` Implement shared schemas

- **Dependencies:** P0-01
- **External input:** AI engineer-delivered `ai/schema.py` and fixtures.
- **Deliverables:** `api/schemas.py`, `web/lib/types.ts`, and contract-validation tests. Do not edit `ai/schema.py`.
- **Acceptance:** delivered JSON fixtures validate against backend schemas and TypeScript compilation.

### `P0-03` Create golden data

- **Dependencies:** P0-02
- **Deliverables:** AI-owned notarial text by H2; AI-owned schema and four extraction fixtures by H4; full-stack-owned PDFs/page PNGs, cases JSON, and registry seed by H4.
- **Acceptance:** backend stub and AI golden tests load the same committed fixtures; every expected result in section 11 is machine-asserted; all names/TCKNs use the fixed fictional cast.

### `P0-04` Database and seed/reset

- **Dependencies:** P0-01, P0-02
- **Deliverables:** models, DB session, create/seed routine, demo load/reset endpoints, safe reset scripts.
- **Acceptance:** a reset from a clean checkout completes under two seconds and produces identical row counts and registry JSON; loading each case returns a persistent application ID.

## Task group 1 — walking skeleton

### `P1-01` AI client modes

- **Dependencies:** P0-02, P0-03
- **Deliverables:** typed stub/live/replay client, timeout/error translation, and backend-owned SHA extraction cache.
- **Acceptance:** the same caller receives schema-identical results in all modes; timeout becomes retryable; restarting the AI service does not affect cache state.

### `P1-02` Application and document API

- **Dependencies:** P0-04
- **Deliverables:** create application, upload, hash, validate, render pages, aggregate GET.
- **Acceptance:** attestations and state transitions are enforced; invalid MIME/size/page requests return controlled errors.

### `P1-03` Analysis orchestration

- **Dependencies:** P1-01, P1-02
- **Deliverables:** mode-selected extraction (fixture/replay now, live `/extract` after delivery), current-registry projection, `/analyze` call, verbatim persistence, audit, idempotency, and concurrency guard.
- **Acceptance:** the API never recomputes checks; two identical sequential calls create one extraction/report; concurrent calls cannot duplicate data.

### `P1-04` Frontend shell and control panel

- **Dependencies:** P0-02, demo load endpoint from P0-04, committed `DESIGN_SYSTEM.md`, and committed visual-reference PNG.
- **Deliverables:** centralized visual tokens; offline-safe Inter typography; shared rounded application shell; grouped persistent/responsive sidebar; compact top bar and breadcrumbs; reusable panel/card/control primitives; YetkiCheck navigation; case cards; flow strip; API layer.
- **Acceptance:** all five route skeletons render inside the same responsive shell; the shell matches the frozen reference character at `1280x800`; NexAI branding/content is absent; sidebar active/focus/mobile behavior works; semantic statuses remain correct; selecting a case creates server state and routes to its branch URL.

### `P1-05` Branch intake and scan

- **Dependencies:** P1-02, P1-04
- **Deliverables:** stepper, forms, attestations, upload UI, loading/error states.
- **Acceptance:** a user cannot advance without both attestations; refresh restores server-backed progress.

## Task group 2 — hero review and approval

### `P2-01` Review UI

- **Dependencies:** P1-03, P1-05
- **Deliverables:** document viewer, field table, nine check rows, evidence expansion, verdict banner, choreography.
- **Acceptance:** all four reports render correctly; evidence selection navigates to the right page.

### `P2-02` Correction flow

- **Dependencies:** P1-03, P2-01
- **Deliverables:** six-field inline editor, correction API, effective-extraction builder, audit, and AI `/analyze` re-run.
- **Acceptance:** raw extraction stays unchanged; `branch_user:kozyatagi01`, old value, and new value are auditable; updated report visibly reflects the correction.

### `P2-03` Decision and authority creation

- **Dependencies:** P2-02
- **Deliverables:** decision endpoint, approval guards, atomic authority builder, hinge panel.
- **Acceptance:** `READY` approves normally; `CO_SIGNER_REQUIRED` requires typed audited override justification; red verdicts cannot approve; repeat approval is idempotent; case 1 creates the exact section-11 authority.

### `P2-04` Registry service and screen

- **Dependencies:** P0-03, P0-04, P1-04
- **Deliverables:** atomic registry service, stable-ID `/reps/{rep_id}` API, admin screen, simulated labels.
- **Acceptance:** toggling Ali and re-analyzing changes case 4 between clean and registry-conflict results without corrupting the file.

## Task group 3 — live AI seam

### External AI delivery gate — not a coding task for this track

- AI engineer has provided `/health`, `/analyze`, and the frozen schema/fixtures; `/extract` remains the explicit gate for live Phase 3 extraction.
- Full-stack agents validate the contract and report defects without editing or operating `ai/`.

### `P3-01` Live AI integration hardening

- **Dependencies:** P1-01, P1-03, P2-01, and the external AI delivery gate
- **Deliverables:** Turkish filename/date/null handling, timeout behavior, backend cache verification, pre-warm/clear tooling.
- **Acceptance:** live and stub results render through the same frontend path; cases 2–4 are pre-warmed; cleared case 1 makes a live call; second analysis is a backend cache hit.

## Task group 4 — transaction enforcement

### `P4-01` Authority engine

- **Dependencies:** P2-03, P2-04
- **Deliverables:** integer-`amount_minor` authorization algorithm, latency measurement, live registry join, and transaction/audit persistence.
- **Acceptance:** all transaction outcomes and registry-removal assertion in section 11 pass.

### `P4-02` Co-sign endpoint

- **Dependencies:** P4-01
- **Deliverables:** secure transition, revalidation, idempotent authorization-code issuance.
- **Acceptance:** wrong, removed, duplicate, or self co-signers are rejected; valid Ayşe co-sign completes once.

### `P4-03` Mobile UI

- **Dependencies:** P4-01, P4-02, P1-04
- **Deliverables:** authority gate, transaction list, decision cards, person switcher, notification, co-sign card.
- **Acceptance:** no client-only decisions; refresh restores pending/completed server state.

### `P4-04` Authority and audit UI

- **Dependencies:** P4-01, P1-04
- **Deliverables:** authority card, rule table, registry status, transaction history.
- **Acceptance:** source document, version, people, rules, and both stages of a co-signed transaction are visible.

## Task group 5 — resilience and demo completion

### `P5-01` Failure states and replay

- **Dependencies:** all Phase 3 and 4 tasks
- **Deliverables:** replay mode, calm retry UI, failed-analysis recovery, offline rehearsal configuration.
- **Acceptance:** with AI stopped and network disconnected, reset plus full demo works from replay fixtures.

### `P5-02` Security and data-handling pass

- **Dependencies:** all API tasks
- **Deliverables:** upload validation, path containment, CORS restriction, redacted logs, secret checks, demo-route guard.
- **Acceptance:** no raw TCKN, document bytes, secrets, or stack traces appear in logs or errors.

### `P5-03` UI and projector pass

- **Dependencies:** all frontend tasks
- **Deliverables:** design-system consistency pass, reference comparison, responsive fixes, accessibility, 1280x800 layout, Turkish text/encoding pass.
- **Acceptance:** all five routes share the frozen sidebar/top bar/typography/palette/card language; no horizontal overflow on demo screens; statuses work without color; registry is readable from distance; no NexAI branding or unrelated reference content appears.

### `P5-04` Reset and rehearsal tooling

- **Dependencies:** P0-04, P5-01
- **Deliverables:** one-command reset, demo-state verification, documented start order.
- **Acceptance:** five consecutive reset-and-demo runs produce the same outcomes.

## Task group 6 — rehearsal and freeze

- Run the complete stage script five times.
- Capture a successful backup video.
- Rehearse AI timeout, AI shutdown, and venue-network loss.
- After H40, change only code on the demonstrated path.
- After H46, make no code changes unless the current build cannot complete the demo.

---

# 13. Verification strategy

Tests are part of implementation tasks, not a separate end-of-project activity.

## 13.1 Required unit coverage

- `tr_normalize()` coverage for `İ/I/ı/i`, diacritics, whitespace, punctuation, and the fixed cast; identical golden cases wherever backend registry-name joins are needed.
- Exact identifier comparison.
- Date validity boundaries.
- Validation and verbatim persistence of delivered nine-check reports; no backend verdict recomputation.
- Application and transaction state transitions.
- Effective extraction with ordered corrections.
- Authority-record construction without scope broadening.
- Turkish amount parsing (`1.200.000,50` -> `120000050`) and uncertain-value-to-null behavior.
- The demo fixture's `50000000` minor-unit boundary, supplied from authority-rule data rather than a product constant.
- Co-signer eligibility and idempotency.
- Registry atomic-read/write behavior.

## 13.2 Required API integration coverage

- Happy-path application through approval.
- Missing document, missing attestation, invalid state, and oversized upload.
- Analyze idempotency and concurrent request behavior.
- Six allowed corrections followed by AI `/analyze`; rejection of every other correction path.
- Normal `READY` approval, justified amber override, missing-justification rejection, and absolute red-verdict rejection.
- Verification that the API persists `CheckReport` verbatim and contains no onboarding-check recomputation.
- Four transaction fixtures.
- Registry removal between pending request and co-sign.
- Reset restoring all baseline state.

## 13.3 Required frontend smoke coverage

- Four cases load and show expected verdict banners.
- Evidence expansion and document-page navigation.
- Approval gating.
- Inline editing of the six fields and visible check re-resolution.
- Typed amber-override justification replacing browser `confirm()`.
- Mobile authority gate.
- Pending co-signature notification and completion.
- Registry removal reflected after a new authorization request.
- Retry UI for a simulated AI timeout.

---

# 14. Security, privacy, and audit requirements

- Accept only PDF, PNG, and JPEG after server-side MIME inspection.
- Enforce upload-size and page-count limits.
- Generate server-side filenames; never trust the client filename as a path.
- Verify every resolved upload/page path remains under the configured data directory.
- Store only the exact masked TCKN fixture values; reject plausible unmasked 11-digit TCKNs from demo application/registry inputs.
- Do not log document bytes, extracted raw personal data, authorization headers, or environment variables.
- CORS allows only configured frontend origins.
- Demo mutation endpoints require `DEMO_MODE=true`.
- Demo branch actions use the fixed actor `branch_user:kozyatagi01`; mobile actions use the selected fixed-cast authority-person ID and are visibly simulated. Clients cannot supply an arbitrary audit actor.
- Audit events cover application creation, attestations, upload, analysis, correction, decision, registry mutation, authority creation/suspension, authorization, and co-signing.
- Never present the system as validating document authenticity or handwritten signatures.

---

# 15. Observability and failure behavior

Every request receives a correlation ID. Structured logs include correlation ID, route, status, duration, and entity IDs, but exclude sensitive payloads.

The analyze flow records durations for:

- document preparation;
- extraction;
- comparison;
- persistence;
- total request.

Expected failure behavior:

- AI timeout: return a retryable error and keep the application recoverable.
- Invalid AI schema: store no partial extraction/report; return a retryable integration error.
- One failed page render: fail analysis clearly; do not pretend a partial document was complete.
- Registry read failure: fail closed for approval and transaction authorization.
- Audit-write failure: roll back the material business action.
- Frontend network failure: preserve current screen and offer retry; do not infer success.

---

# 16. Demo runbook

Before presentation:

1. Run the safe reset command.
2. Confirm `/health` and `/ready`.
3. Confirm `AI_MODE=live` and `EXTRACTION_CACHE=on`.
4. Confirm cases 2–4 contain cached real extraction results from final rehearsal.
5. Clear case 1's extraction cache and verify replay fallback plus backup recording are locally available.
6. Load case 1 and keep the control panel ready.
7. Verify registry baseline has Ali and Ayşe active.

Stage beats:

1. Explain the paper problem.
2. Complete branch identity and original-document attestations.
3. Run analysis and expand one evidence row.
   State truthfully that case 1 is making a live model call; describe later cached cases as cached real results.
4. Approve and show the authority-record hinge.
5. Approve the small mobile transaction.
6. Request the large transaction and switch to Ayşe.
7. Co-sign and show the authorization code.
8. Deny the real-estate transaction.
9. Remove Ali in registry.
10. Retry and show immediate denial.
11. Show the audit trail and distinguish real versus simulated integrations.

---

# 17. Cut strategy

Never cut:

- case 1 branch-to-authority flow;
- explainable checks and evidence;
- deterministic authority engine;
- one successful transaction, one co-signed transaction, and one denied transaction;
- registry-removal denial;
- audit trail;
- reset/replay path.

Cut first if behind:

1. Field-editing UI polish; retain API-level corrections or escalation.
2. Page bounding-box overlay; retain page number and quote evidence.
3. Keyboard shortcuts and decorative animation.
4. Raw registry JSON panel.
5. Non-demo transaction history pagination and filtering.

Do not solve schedule pressure by hardcoding verdicts in React or allowing the client to create approval/transaction state.

---

# 18. Coding-agent execution protocol

Every coding agent must:

1. Read `PROJECT.md`, this file, and only the references required for its task.
2. State the task ID it is implementing.
3. Verify dependencies are present before editing.
4. Treat shared schemas, check IDs, verdict values, and API paths as frozen.
5. Avoid unrelated refactors and preserve other agents' changes.
6. Put business rules in backend services, never UI components.
7. Add or update the tests named in the task acceptance criteria.
8. Run only the smallest relevant verification during implementation, then report exactly what ran.
9. Report changed files, behavior, limitations, and remaining dependencies.
10. Stop and request a plan update if a required behavior contradicts a frozen contract.
11. Treat `ai/` as AI-engineer-owned and read-only: do not scaffold it, edit it, run its tests, start/stop its process, or change its prompts/models. Integration work is limited to `api/services/ai_client.py`, mirrored backend/frontend schemas, fixtures consumed by the stub/replay path, and contract verification.

An agent may not silently rename enum values, change response shapes, add an authorized person, broaden an authority rule, bypass attestations, or turn a simulated integration into an unlabeled fake.

An agent must also reject any implementation that adds `if case_id == ...`, fixture-filename checks, fictional-name checks, preset-amount checks, or expected-verdict lookup inside application, comparison, authority-building, or transaction-enforcement services. Those identifiers belong only to demo fixture loaders and tests.

---

# 19. Final definition of done

- The two acts are connected by a real server-side approval and authority record.
- Four onboarding cases produce their specified verdicts and evidence.
- Four transaction cases produce their specified decisions.
- Those cases are processed as ordinary inputs by generic engines; adding another scenario requires fixture/test data rather than a business-code branch.
- Co-signing is server-side, revalidated, audited, and idempotent.
- Registry removal blocks both new approval and later transactions.
- Raw extraction is preserved and corrections are traceable.
- Business decisions never originate in frontend code.
- The demo runs in stub, live, and replay modes through the same contracts.
- One command safely resets database, registry, and demo files.
- The full path works offline from committed synthetic fixtures.
- No demo screen hangs, exposes a stack trace, or shows an unexplained failure.
- Simulated identity, registry, bank shell, and documents are visibly labeled.
- The presentation can be completed repeatedly within the allotted time.
