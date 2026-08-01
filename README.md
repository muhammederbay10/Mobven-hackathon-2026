# YetkiCheck

Bir imza sirkülerinin aslı yalnızca **bir kez** şubede görülür. Sistem belgeyi okur, başvuru ve sicil ile karşılaştırır, görevli onaylar — ve o andan itibaren her mobil işlem aynı yetki kaydı üzerinden denetlenir.

Two acts:

1. **Şube (Act 1)** — verify identity and the original document, scan it, extract structured authority, run nine deterministic checks, and have a human approve. Approval creates an authority record.
2. **Mobil şube (Act 2)** — every later transaction is authorized against that record: person, limit, subject, validity, and live registry status.

Canonical product source: [`docs/fbdocs/PROJECT.md`](docs/fbdocs/PROJECT.md).
Execution plan: [`docs/fbdocs/IMPLEMENTATION_PLAN.md`](docs/fbdocs/IMPLEMENTATION_PLAN.md).
Frozen contracts: [`docs/CONTRACT_FREEZE.md`](docs/CONTRACT_FREEZE.md).

---

## Ownership

| Area | Owner |
|---|---|
| `web/`, `api/`, `data/`, `scripts/` | full-stack track |
| `ai/` — extraction, prompts, the nine-check comparison engine, the AI service | **AI engineer** |

`ai/` is read-only to this track. Do not scaffold it, edit it, run its tests, start or stop its process, or change its prompts or models. Integration work is limited to `api/services/ai_client.py`, the mirrored schemas, the fixtures consumed by the stub/replay path, and contract verification. A contract defect is **reported**, never patched here (plan sections 8.8 and 18.11).

## Architecture

```
Next.js browser  :3000
        |  JSON / multipart, via web/lib/api.ts only
        v
FastAPI bank API :8000  ----  SQLite + data/registry.json
        |  private server-to-server HTTP
        v
FastAPI AI svc   :8001  (external; operated by the AI engineer)
```

The browser never calls the AI service. The bank API owns persistence, orchestration, approval, authority records, transactions, registry access, audit logs, and the extraction cache. The AI service is stateless and file-system-free.

## Repository layout

```
web/            Next.js frontend (5 routes: / /branch /mobile /authority/[mersis] /registry)
api/            FastAPI bank API
  schemas.py      frozen shared contracts (Python mirror)
  routers/        HTTP surface
  services/       all business rules live here, never in UI components
  tests/          contract + integration tests
ai/             EXTERNAL — AI-engineer-owned, read-only to this track
data/
  fixtures/       committed golden cases, extractions and reports
  documents/      committed synthetic PDFs and page PNGs
  cache/          bank-API-owned validated live responses (pre-warmed for stage)
  registry.seed.json   committed baseline registry
  registry.json        generated at reset; git-ignored
  uploads/             runtime; git-ignored
scripts/        reset_demo.ps1 / reset_demo.sh
docs/           contract freeze + product plan
```

## Setup

Requires Node 22+ and Python 3.13+.

```bash
# frontend
cd web && npm install

# backend (from the repo root)
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r api/requirements.txt    # Windows
# source .venv/bin/activate && pip install -r api/requirements.txt # macOS/Linux

# configuration
cp api/.env.example api/.env
cp web/.env.example web/.env.local
```

Neither example file contains a real key or a machine-specific path. Model credentials are AI-engineer-owned and never live in this repo.

## Developer commands

These names are part of the developer contract (plan section 4.4). Other tasks depend on them; add narrower commands freely, but do not rename these.

| Area | Command |
|---|---|
| web | `npm run dev` · `lint` · `typecheck` · `test` · `build` |
| api | `python -m uvicorn api.main:app --reload --port 8000` |
| api tests | `python -m pytest api/tests` |
| demo reset | `scripts/reset_demo.ps1` (Windows) · `scripts/reset_demo.sh` (macOS/Linux) |

Start order for a demo: reset → API on :8000 → web on :3000. The AI service is started separately by the AI engineer; this track only points `AI_URL` at it and verifies connectivity.

### What runs today

Phase 0 shared architecture, backend, and data/fixture steps are complete. Working now:

```bash
scripts/reset_demo.ps1                                  # or reset_demo.sh
python -m uvicorn api.main:app --reload --port 8000
python -m pytest api/tests
curl -X POST localhost:8000/api/demo/load-case/1        # -> {"application_id": 1}
```

`GET /health`, `GET /ready`, `GET /api/demo/cases`, `POST /api/demo/load-case/{n}` and `POST /api/demo/reset` are live.

Still to come: `npm run dev` / `npm run build` need the Phase 0 **frontend** steps (`app/layout.tsx` and the route files). Document upload, analysis and the review screen are Phase 1.

Two Phase 0 data items are blocked on external input:

- The **notarial Turkish text** is an AI-engineer deliverable (GAP-10, due H2). Drop it in `data/documents/source/` — see the README there — then run `python scripts/render_documents.py` to produce the PDFs and page PNGs.
- One document must be **printed and re-photographed** (data step 6). That is a physical step, not an automatable one.

## AI service modes

`AI_MODE` in `api/.env`:

| Mode | Behavior |
|---|---|
| `stub` | committed golden fixtures, optional short artificial delay |
| `live` | call the AI service at `AI_URL` |
| `replay` | return a cached validated live response, selected by document SHA-256 |

An unknown value must fail application startup with a clear configuration error. Stage policy (GAP-11) is `AI_MODE=live` with `EXTRACTION_CACHE=on`, cases 2–4 pre-warmed during final rehearsal, and case 1's cache cleared so the judged run makes a genuine model call. Cached cases are described on stage as **cached real results** — never as live calls, and stub fixtures are never presented as model output.

## Ground rules

- Business rules live in `api/services/`, never in UI components. The frontend never computes a check, a verdict or a decision.
- `web/lib/api.ts` is the only file allowed to call `fetch` (enforced by an ESLint rule).
- Money is integer minor units (`amount_minor`, kuruş, `TRY`). No floating-point money anywhere; format only at the display edge.
- TCKNs are masked everywhere, in exactly one format. A plausible unmasked 11-digit value is rejected.
- The four onboarding cases and four preset transactions are **fixtures, not workflows**. No `if case_id == …`, no fixture-filename, fictional-name, preset-amount or expected-verdict branching inside application, comparison, authority-building or transaction-enforcement code. Adding a fifth scenario must require only new fixture data (plan sections 1.4 and 18).
- The registry and branch identity service are simulated and must stay visibly labeled. The system never claims a document is authentic and never matches handwritten signatures.
