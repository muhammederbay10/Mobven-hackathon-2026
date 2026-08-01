# `api/` — YetkiCheck bank API

FastAPI + SQLite. Owns persistence, orchestration, application state, approval, authority records, transactions, registry access, audit logs, and the extraction cache (plan section 1.3).

It does **not** own extraction, prompts, or the nine-check comparison engine. Those belong to the AI engineer. `POST /analyze` is delivered; `POST /extract` is still pending in the current AI contract.

## Commands

Run from the **repository root**, with the virtualenv active:

```bash
python -m uvicorn api.main:app --reload --port 8000
python -m pytest api/tests
```

Both run today. Reset first, then start the server:

```bash
scripts/reset_demo.ps1                                  # or scripts/reset_demo.sh
python -m uvicorn api.main:app --reload --port 8000
```

### Endpoints live now

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | process + database; deliberately does not require the AI service |
| GET | `/ready` | 200/503 — database, data dir, and configured AI-mode readiness |
| GET | `/api/demo/cases` | case cards for the control panel |
| POST | `/api/demo/load-case/{n}` | 201 `{application_id}`; `DEMO_MODE` guarded |
| POST | `/api/demo/reset` | 200 `{ok:true}`; `DEMO_MODE` guarded |
| POST | `/api/applications` | create and persist a branch application |
| GET | `/api/applications/{id}` | aggregate branch state for refresh/restore |
| POST | `/api/applications/{id}/document` | attested PDF/PNG/JPEG upload and page rendering |
| GET | `/api/documents/{id}/page/{n}` | validated rendered PNG page |

Analysis, decisions, authority and transactions remain later Phase 1/Phase 2 work. The AI schema
now agrees with the full-stack mirrors, but live document analysis remains gated on delivery of
AI `POST /extract`. Stub/replay integration can proceed independently.

## Configuration

Copy `api/.env.example` to `api/.env`. `AI_MODE` accepts `stub`, `live` or `replay`; any other value must fail startup with a clear configuration error (plan section 4.3). Demo mutation endpoints require `DEMO_MODE=true`.

Uploads are limited by `MAX_UPLOAD_MB` and `MAX_DOCUMENT_PAGES`. MIME is determined from file
bytes rather than trusting the browser's filename or content-type header.

## Layout

| Path | Role |
|---|---|
| `main.py` | app factory, CORS allowlist, correlation IDs, error envelope, `/health`, `/ready` |
| `config.py` | validated settings; unknown `AI_MODE` fails startup; path containment |
| `db.py`, `models.py` | SQLModel tables, enums, UTC timestamps, session lifecycle |
| `schemas.py` | bank contracts plus the strict Python mirror of `docs/API_CONTRACT.md` |
| `errors.py` | `ApiError` and the standard error envelope |
| `routers/` | HTTP surface only: validate, delegate, serialize |
| `services/` | every business rule lives here |
| `tests/` | contract and integration tests |

`services/demo_service.py` is an addition to the section 4.1 layout: the plan asks for a "seed/reset service" but lists no home for it, and business logic must not live in `routers/demo.py`. It is also the **only** module allowed to know a case number exists (section 1.4).

## Rules this service holds to

- **Never recompute an onboarding check or a verdict.** Pass the sources to `/analyze`, validate the response contract, persist the returned `CheckReport` verbatim, serve it (plan section 6).
- **Only the service layer transitions state.** Invalid transitions return `409 INVALID_STATE_TRANSITION` (section 7.2).
- **Raw AI payloads are immutable.** Corrections are append-only rows applied on read to build the *effective* extraction (section 7.1).
- **Money is integer kuruş.** Float money columns are forbidden (GAP-12).
- **Audit is append-only**, and an audit-write failure rolls back the business action it describes (section 15).
- **Fail closed.** A registry read failure blocks approval and authorization rather than allowing them (section 15).
- **No case awareness.** Case numbers belong to demo fixture loaders and tests only — never to `application_service`, `authority_builder` or `authority_engine` (sections 1.4 and 18).
- **Errors carry no stack traces, raw model responses, local paths or secrets**, and logs carry no document bytes or unmasked personal data (sections 5.7 and 14).

## Working with the AI service

Integration is confined to `services/ai_client.py` (typed HTTP boundary, bank-registry projection, timeout translation, backend-owned SHA-256 extraction cache) plus the mirrored schemas and fixtures. The AI extraction payload is flat/camelCase; bank-owned public APIs remain snake_case.

`AI_EXTRACT_AVAILABLE=false` is the default because `/extract` has not been delivered. In live mode, `/ready` reports `ai_extract` as blocking until that flag is explicitly enabled after contract verification.

If a delivered response violates the contract, record the request/response defect and hand it to the AI engineer. Do not patch anything under `ai/`, and do not special-case a verdict in backend code to work around it (plan sections 8.8 and 18.11).
