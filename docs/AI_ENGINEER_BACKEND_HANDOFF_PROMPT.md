# Copy-paste prompt for the AI engineer

You are integrating the AI service with the completed YetkiCheck bank backend.
Do not use the old `PLAN.md` shapes. Read these files first, in this order:

1. `docs/API_CONTRACT.md` — authoritative AI HTTP/JSON contract.
2. `api/schemas.py` — strict bank-side mirror of that contract.
3. `api/services/ai_client.py` — the only bank-to-AI transport boundary.
4. `docs/BACKEND_PHASE_1_5_REPORT.md` — implemented flow and test coverage.

What changed:

- `ExtractionResult` is the new flat contract: `schema_version`, string
  `document_id`, flat `company`, `notary`, `validUntil`, `representatives`,
  `fieldsNeedingReview`, `evidence`, and `rules`.
- Representative source IDs are stable document-order IDs such as `rep-1`.
- `representatives[].coSigners` contains display names, while
  `rules[].coSigners` contains representative IDs.
- `representatives[].limits` and `rules[].threshold` are integer kuruş, never
  float TL. `null` means unbounded.
- Rule scopes are lowercase contract strings such as `general`, `credit`, and
  `real_estate`.
- A blocked scope uses `blocked: true`, `mode: null`, and `coSigners: []`.
- Masked TCKNs match `^\d{3}\*{6}\d{2}$`; dates are `YYYY-MM-DD`.
- `POST /analyze` must always return exactly the frozen nine checks in order,
  with lowercase `green|amber|red` statuses.
- The AI process must remain stateless: it receives application and registry
  JSON in the request and must not read the bank database, registry files,
  upload paths, or cache.

Backend work now present:

- `POST /api/applications/{id}/analyze` orchestrates stub/live/replay,
  persistence, cache, state transitions, retry and audit.
- Corrections, approval/override, authority records, current-registry
  transaction enforcement and co-signing are implemented through Phase 5.
- Offline fallback extractions are in `data/fixtures/extractions/`; offline
  reports and their declarative selector are in `data/fixtures/reports/`.
- Synthetic UTF-8 text and rendered PDFs are in `data/documents/`.

What I need you to do:

1. Implement and expose `POST /extract` using exactly `docs/API_CONTRACT.md`.
   The prepared bank client sends multipart field `file` plus form field
   `document_id`; confirm those request names or flag the transport difference
   before implementation.
2. Keep `GET /health` returning `{status, engine, schema_version}` and keep
   `POST /analyze` contract-compatible.
3. Validate Turkish filenames/text, null fields, masked IDs, dates, stable IDs,
   integer kuruş, source evidence, and the explicit blocked real-estate rule.
4. Run your golden tests, then compare your four extraction/report fixtures
   with the fallback fixtures listed above. Flag semantic differences; do not
   silently change the shared contract or bank authority rules.
5. Give the full-stack engineer the AI engine name, startup command, required
   environment variables, health output, and one successful `/extract` plus
   `/analyze` contract-test result.

Backend verification command:

```powershell
.\.venv\Scripts\python.exe -m pytest api/tests -q
```

After your live endpoint passes, the full-stack side will set
`AI_MODE=live` and `AI_EXTRACT_AVAILABLE=true` and run the complete four-case
rehearsal. Do not edit bank-owned code under `api/`, `web/`, or `data/cache/`;
report any mismatch with the exact JSON path and expected/actual value.
