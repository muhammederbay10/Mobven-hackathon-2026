# Contract alignment — 2026-08-01

**Status:** aligned to the AI engineer's current `schema_version: "1.0"` delivery.

## Authority order

1. `docs/API_CONTRACT.md` — AI service HTTP requests and responses.
2. `docs/fbdocs/IMPLEMENTATION_PLAN.md` — bank API, persistence, product flow, and phases.
3. `api/schemas.py` — Python consumer mirror.
4. `web/lib/types.ts` and `web/lib/contracts.ts` — TypeScript and runtime-validation mirrors.

If the mirrors disagree with `docs/API_CONTRACT.md`, the contract document wins and all mirrors/tests must be updated together. The bank-owned registry and public bank API remain snake_case; only the AI extraction projection uses its documented camelCase aliases.

The loose `docs/aischema.py` and `docs/aischema (1).py` files are received snapshots, not executable or authoritative sources. The real AI-owned `ai/schema.py` is not present in this checkout.

## AI wire shape

`ExtractionResult` is the flat projection:

- `schema_version`, `document_id`
- `company.{name,taxNumber,mersisNumber,legalNameNormalized}`
- `notary.{name,date,yevmiye}`
- `validUntil`
- `representatives[].{id,name,nameNormalized,nationalId,title,mode,coSigners,limits}`
- `fieldsNeedingReview`
- `evidence.{authorityClause,page}`
- `rules[].{scope,threshold,mode,coSigners,blocked,evidence}`

Important distinctions:

- `representatives[].coSigners` contains display names.
- `rules[].coSigners` contains stable extraction IDs such as `rep-1`.
- `limits` and `threshold` are strict integer kuruş; floats are rejected.
- A blocked rule requires `mode: null` and `coSigners: []`.
- Every rule signer ID must resolve inside the same extraction.
- TCKNs are masked only: `^\d{3}\*{6}\d{2}$`.

`CheckReport` contains only `verdict` and the ordered `checks`. A check is `{id,status,title,reason,evidence}`; `status` is lowercase `green | amber | red`, and `evidence` is a key/value object.

The ordered IDs are:

```text
company_name_match
tax_number_match
mersis_number_match
applicant_in_document
identity_match
authority_mode
registry_status
registry_representative_match
document_validity
```

The previous `schema_version`, `blocking_check_ids`, `generated_at`, `source_kind`, and evidence-array fields are not part of `CheckReport`.

## `/analyze` request adapter

The bank keeps its stable-ID registry envelope internally. `api/services/ai_client.py::build_analyze_request()` projects it at the boundary into the AI shape:

```text
registry[mersis] = { name, status, reps: [{name,tckn,mode,status}] }
```

The application sends `applicant_tckn` to AI even though the bank's public API and database call the field `applicant_tckn_masked`. `as_of` is optional. Unknown application and registry fields are tolerated by the AI endpoint; AI responses remain strict.

## Endpoint availability

| Endpoint | Current state |
|---|---|
| `GET /health` | Implemented |
| `POST /analyze` | Implemented |
| `POST /extract` | Not implemented by the AI service yet |

`AI_EXTRACT_AVAILABLE=false` is therefore the safe default. Live bank readiness reports `ai_extract` as blocking until the endpoint is delivered and contract-tested. Stub/replay modes remain usable.

## Bank-owned contracts that did not change

- application/document persistence and state transitions;
- the bank registry envelope and stable `rep_abc_*` IDs;
- snake_case public bank API requests;
- masked identity policy;
- integer-kuruş transaction amounts;
- audit/error envelopes;
- the production flow in `IMPLEMENTATION_PLAN.md` (the HTML prototype is presentation reference only).

## Verification

- Python: `python -m pytest api/tests`
- Frontend: `npm run typecheck && npm run test`
- Mirrors: `api/tests/test_contract_freeze.py`, `api/tests/test_ai_fixture_contracts.py`, and `web/lib/contracts.test.ts`

Fixture tests read `ai/tests/fixtures/case{1..4}.json` and `case{1..4}-report.json` when those files are present in the shared repository. A missing fixture is a delivery signal, not permission to create a conflicting full-stack copy.
