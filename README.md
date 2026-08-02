# Starq.dev

Starq.dev converts a Turkish **imza sirküleri** (signature circular) into a reviewed authority record and then uses deterministic rules to verify later banking transactions.

The product has two connected acts:

1. **Branch onboarding:** a branch employee sees the original notarized document, scans it, compares the extracted information with the application and the simulated registry, and approves the result.
2. **Mobile authorization:** later transactions are checked in milliseconds against the approved authority record, including the person, transaction scope, amount limit, validity period, registry status, and signature requirements.

The central principle is:

> Agents read. Code decides. Humans approve.

## What the system does

- Reads PDF, PNG, and JPEG signature circulars with a vision-model pipeline.
- Extracts the company, notary information, authorized people, signature modes, limits, validity, and authority rules.
- Preserves page numbers and verbatim Turkish evidence for review.
- Runs nine deterministic checks against the branch application and simulated registry.
- Lets the branch employee correct, approve, request a new document, or escalate the result.
- Creates a versioned authority record only after human approval.
- Authorizes or rejects later mobile transactions with deterministic Python rules.
- Supports single signature, joint signature, amount limits, blocked scopes, co-signing, registry revocation, and audit history.
- Supports live AI, offline fixture, and cached replay modes for development and demo resilience.

Starq.dev does **not** claim that a document is authentic and does not compare handwritten signatures. The first verification remains a branch process where the original document and the customer's identity are physically checked. The registry in this project is clearly marked as simulated.

## Architecture

```text
Browser / Next.js       Bank API / FastAPI          AI service / FastAPI
localhost:3000    --->  localhost:8000       --->  localhost:8001
                         |                            |
                         |                            +-- render pages
                         |                            +-- classify pages
                         |                            +-- build chunks
                         |                            +-- extract sections
                         |                            +-- normalize + validate
                         |                            +-- nine comparisons
                         |
                         +-- SQLite persistence
                         +-- application workflow
                         +-- simulated registry
                         +-- human corrections/approval
                         +-- authority engine
                         +-- transactions + audit
```

The browser only calls the bank API. It never calls the AI service directly.

| Service | Port | Responsibility |
|---|---:|---|
| `web/` | 3000 | Branch, mobile, authority, registry, and demo interfaces |
| `api/` | 8000 | Persistence, orchestration, approval, registry, authority decisions, transactions, and audit |
| `ai/` | 8001 | Document extraction and the deterministic nine-check comparison report |

## End-to-end workflow

### Act 1 — branch onboarding

1. The employee creates an application and confirms that the customer's identity was checked at the branch.
2. The employee uploads the scanned original and confirms that the original document was seen.
3. The bank API stores the upload and sends it to the AI service.
4. The AI pipeline renders the pages at two resolutions, classifies them, creates section-aware chunks, and reads appointments, rules, and signature specimens.
5. Pure Python code normalizes Turkish names, merges repeated evidence, resolves people and groups, validates provenance, and projects the result into the public API schema.
6. The AI service runs nine deterministic comparisons against the application and simulated registry. No model is used to decide the verdict.
7. The bank API persists the extraction and report. The employee reviews the document evidence, corrects fields if necessary, and makes the final decision.
8. Approval creates a versioned authority record for future transactions.

The nine comparison checks cover company name, tax number, MERSIS number, applicant presence, identity, signature mode, registry status, registry representative status, and document validity.

### Act 2 — mobile authorization

1. A customer submits a transaction from the mobile flow.
2. The bank API loads the approved authority record and re-checks the current simulated registry.
3. The deterministic authority engine checks the initiator, scope, amount, validity, blocked rules, and signature requirements.
4. It returns `ALLOWED`, `SECOND_SIGNATURE`, or `DENIED` with template-based reasons and an audit record.
5. If a second signature is required, the co-signer action re-runs the checks before completing the transaction.

The model never participates in this decision path.

## Repository layout

```text
ai/                  AI extraction and comparison service
  prompts/           Turkish extraction prompts
  scripts/           pipeline and diagnostic commands
  tests/             deterministic and golden tests
  cache/             local SHA-256 extraction/replay cache

api/                 bank backend service
  routers/           HTTP endpoints
  services/          workflow and business rules
  tests/             contract and integration tests

web/                 Next.js frontend
  app/               five product routes
  components/        shared interface components
  lib/               API client, contracts, types, and formatting

data/                synthetic demo documents, fixtures, registry, uploads, and replay data
docs/                plans, contracts, evaluation matrix, and implementation tickets
scripts/             safe demo reset scripts
extraction-spike/    frozen internal extraction research; never used as runtime code
```

## Technology

- Python 3.11+
- FastAPI, Pydantic v2, SQLModel, SQLite, and HTTPX
- OpenAI vision models configured only through `ai/.env`
- `pypdfium2`, PyMuPDF, Pillow, and RapidFuzz
- Next.js 15, React 19, TypeScript, Tailwind CSS, Zod, and Vitest
- Node.js 22+

## Setup

Run the following commands from the repository root.

### 1. Create the Python environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt -r ai\requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r api/requirements.txt -r ai/requirements.txt
```

### 2. Install the frontend

```powershell
npm --prefix web install
```

### 3. Create local environment files

PowerShell:

```powershell
Copy-Item ai\.env.example ai\.env
Copy-Item api\.env.example api\.env
Copy-Item web\.env.example web\.env.local
```

macOS/Linux:

```bash
cp ai/.env.example ai/.env
cp api/.env.example api/.env
cp web/.env.example web/.env.local
```

Environment files are local and gitignored. Never commit `OPENAI_API_KEY`.

## Choose an AI mode

There are two mode selectors because the bank API and AI service are separate processes.

| Mode | Bank API behavior | AI service behavior |
|---|---|---|
| `live` | Calls the AI service over HTTP | Calls the configured models and may write its local cache |
| `stub` | Returns committed synthetic fixtures | Returns AI-service test fixtures |
| `replay` | Returns a previously validated backend cache entry | Returns an entry from `ai/cache/` |

### Real document extraction

Set the following values before starting the services.

`ai/.env`:

```dotenv
OPENAI_API_KEY=your_key_here
EXTRACTION_MODEL=your_primary_model
WITNESS_MODEL=your_optional_witness_model
AI_MODE=live
EXTRACTION_CACHE=on
```

`api/.env`:

```dotenv
AI_URL=http://127.0.0.1:8001
AI_MODE=live
AI_EXTRACT_AVAILABLE=true
EXTRACTION_CACHE=on
AI_TIMEOUT_SECONDS=1200
```

`AI_TIMEOUT_SECONDS` is the bank API's wait limit for the complete AI request. Large multi-page documents may take several minutes, so the live configuration should not use the short fixture-mode timeout.

Both `AI_MODE` values matter. Setting only `ai/.env` to `live` is not enough: if `api/.env` remains `stub`, the frontend still receives fixture data.

### Offline development

To develop the frontend and bank workflow without model calls, set `AI_MODE=stub` in `api/.env`. The AI service is not required in this mode, although it can still be started for direct testing.

Use `AI_MODE=replay` when validated cached extractions already exist and the live AI service should not be required during a demo.

## Run all services

### 1. Reset the demo state

PowerShell:

```powershell
.\scripts\reset_demo.ps1
```

macOS/Linux:

```bash
./scripts/reset_demo.sh
```

The reset restores the SQLite demo state, simulated registry, and uploads. It deliberately preserves pre-warmed extraction cache entries.

### 2. Start the AI service — terminal 1

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn ai.main:app --host 127.0.0.1 --port 8001 --reload
```

macOS/Linux:

```bash
.venv/bin/python -m uvicorn ai.main:app --host 127.0.0.1 --port 8001 --reload
```

The service reads `ai/.env` itself; `--env-file` is not required.

### 3. Start the bank API — terminal 2

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

macOS/Linux:

```bash
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Start the frontend — terminal 3

```powershell
npm --prefix web run dev
```

Open <http://localhost:3000>.

## Verify the services

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Expected ports:

- Frontend: <http://localhost:3000>
- Bank API documentation: <http://127.0.0.1:8000/docs>
- AI service documentation: <http://127.0.0.1:8001/docs>

In live mode, `/ready` reports whether the AI service is reachable, whether live extraction is enabled, the configured timeout, and the backend extraction-cache status.

## Product routes

| Route | Purpose |
|---|---|
| `/` | Demo control panel and synthetic test cases |
| `/branch` | Branch application, scan, analysis, review, and approval |
| `/mobile` | Transaction authorization and co-signature flow |
| `/authority/[mersis]` | Approved authority record and history |
| `/registry` | Simulated registry administration |

## Main API endpoints

### AI service — port 8001

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Model configuration and schema health |
| `POST` | `/extract` | Extract a PDF/image into the flat authority schema |
| `POST` | `/analyze` | Run the deterministic nine-check comparison |

### Bank API — port 8000

| Area | Important endpoints |
|---|---|
| Infrastructure | `GET /health`, `GET /ready` |
| Demo | `GET /api/demo/cases`, `POST /api/demo/load-case/{n}`, `POST /api/demo/reset` |
| Applications | `POST /api/applications`, document upload, analysis, correction, and decision endpoints |
| Documents | `GET /api/documents/{id}/page/{n}` |
| Registry | `GET /api/registry`, representative status update |
| Authority | `GET /api/authority/{mersis}`, `GET /api/authority/{mersis}/history` |
| Transactions | authorize, co-sign, and history endpoints under `/api/transactions` |
| Audit | `GET /api/audit` |

The interactive Swagger pages on ports 8000 and 8001 contain the exact current request and response schemas.

## Test and quality commands

Run from the repository root.

```powershell
# AI deterministic, pipeline, and golden tests
.\.venv\Scripts\python.exe -m pytest ai\tests

# Bank API contract and integration tests
.\.venv\Scripts\python.exe -m pytest api\tests

# Frontend checks
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
```

Tests do not call the OpenAI API. Live-document diagnostics are separate commands under `ai/scripts/` and require an explicit live mode.

## Caching and replay

The running system has two independent file caches:

- `ai/cache/` stores AI-pipeline results by document SHA-256 and is used by the AI service's replay mode.
- `data/cache/extractions/` stores bank-validated AI responses using the document hash, schema version, and model engine.

The bank API returns the `X-Extraction-Cache: hit|miss` header from the application analysis endpoint. A repeated result may therefore be a validated cache hit rather than a new model call.

Demo cache entries can be managed through:

- `POST /api/demo/cache/prewarm`
- `POST /api/demo/cache/clear`

These endpoints require `DEMO_MODE=true`.

## Troubleshooting

### The frontend still returns mock data

Check `api/.env`, not only `ai/.env`:

```dotenv
AI_MODE=live
AI_EXTRACT_AVAILABLE=true
AI_URL=http://127.0.0.1:8001
```

Restart the bank API after changing its environment file. Then call `GET http://127.0.0.1:8000/ready` and confirm that `checks.ai.ai_mode` is `live`, `extract_available` is `true`, and `reachable` is `true`.

### A long document times out

Increase `AI_TIMEOUT_SECONDS` in `api/.env` and restart the bank API. This controls how long the full-stack backend waits for the AI service; it is separate from browser or reverse-proxy timeouts.

### A repeated document returns an older result

Inspect the `X-Extraction-Cache` response header. Clear the relevant demo cache entry or temporarily set `EXTRACTION_CACHE=off` in the service whose cache you want to bypass, then restart that service.

### The API is healthy but not ready

`/health` checks the bank process and database. `/ready` also checks required fixtures, runtime directories, and live AI connectivity. Use the `blocking` and `checks` fields in `/ready` to identify the missing dependency.

## Privacy and safety

- Never commit `.env` files or API keys.
- Never log document bytes, raw model responses, or unmasked personal identifiers.
- Use only the synthetic documents under `data/documents/` for screenshots and presentations.
- Documents under `extraction-spike/samples/` are internal evaluation material and must not appear in the demo or deck.
- Provenance warnings annotate uncertain extraction; they never silently grant authority.
- Human approval is required before an authority record is created.
- Transaction decisions are deterministic and auditable.

## Project documentation

- [`docs/PLAN.md`](docs/PLAN.md) — product and execution plan
- [`docs/PLAN_ALIGNMENT.md`](docs/PLAN_ALIGNMENT.md) — AI/full-stack architecture alignment
- [`docs/AI_BACKEND_PLAN.md`](docs/AI_BACKEND_PLAN.md) — extraction rationale and domain model
- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — AI service contract
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — evaluation matrix and benchmark notes
- [`docs/AI_PIPELINE_TICKETS.yaml`](docs/AI_PIPELINE_TICKETS.yaml) — pipeline ticket status and findings
- [`docs/CONTRACT_FREEZE.md`](docs/CONTRACT_FREEZE.md) — cross-service contract rules
