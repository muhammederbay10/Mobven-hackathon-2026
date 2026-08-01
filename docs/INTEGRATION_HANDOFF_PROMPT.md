# Copy-ready implementation handoff prompt

You are continuing YetkiCheck as the full-stack implementation agent.

The AI contract was realigned on 2026-08-01. Read these files in this order before changing code:

1. `docs/API_CONTRACT.md` — authoritative AI HTTP wire contract.
2. `docs/CONTRACT_FREEZE.md` — concise integration decisions and endpoint status.
3. `docs/fbdocs/IMPLEMENTATION_PLAN.md` — bank architecture, production flow, phases, and ownership.
4. `api/schemas.py` — Python mirror and bank-owned schemas.
5. `web/lib/types.ts` and `web/lib/contracts.ts` — frontend mirror/runtime validation.
6. `api/services/ai_client.py` — the only bank-to-AI transport and registry-shape adapter.

Do not use `docs/aischema.py` or `docs/aischema (1).py` as contract sources; they are loose received snapshots. The authoritative description in this checkout is `docs/API_CONTRACT.md`.

What changed:

- The AI `ExtractionResult` is the delivered flat/camelCase shape, not the former rich snake_case shape.
- Money fields `representatives[].limits` and `rules[].threshold` are strict integer kuruş.
- Representatives have stable `rep-*` IDs.
- `representatives[].coSigners` contains display names; `rules[].coSigners` contains representative IDs.
- Rules include `blocked`; real estate is represented by an explicit blocked rule.
- Check status is lowercase `green | amber | red`.
- Ordered check IDs 7 and 8 are `registry_status` and `registry_representative_match`.
- `CheckReport` contains only `{verdict, checks}`; each check is `{id,status,title,reason,evidence}` and evidence is an object.
- `/analyze` receives `{extraction,application,registry,as_of?}`. Its registry is keyed by MERSİS, so the bank registry is projected only at the AI-client boundary.
- The AI application key is `applicant_tckn`; the bank public API/database still uses `applicant_tckn_masked`.
- `/health` and `/analyze` are implemented by AI. `/extract` is not yet implemented.
- `AI_EXTRACT_AVAILABLE=false` is the safe default, and live `/ready` reports `ai_extract` as blocking until delivery.
- `docs/fbdocs/index.html` is a component/presentation reference only. The production workflow comes from `IMPLEMENTATION_PLAN.md`.

What did not change:

- Bank application/document persistence and state transitions.
- Bank registry envelope and its stable `rep_abc_*` IDs.
- Snake_case public bank API payloads.
- Audit/error envelopes, masked identity policy, and integer-kuruş transaction amounts.
- The rule that the bank never recomputes the AI onboarding verdict/checks.

Implementation guidance:

- Do not edit or operate `ai/`; it is externally owned.
- Continue Phase 1 from `IMPLEMENTATION_PLAN.md`.
- P1-02 application/document upload is already implemented.
- P1-01 now has the strict live `/analyze` client, registry projection, cache alias preservation, timeout/error translation foundations, and tests.
- Implement P1-03 first for stub/replay using delivered fixtures. Enable live extraction only after `/extract` is delivered and contract-tested.
- Persist the raw AI payload verbatim. Keep bank-owned `engine`, document SHA-256, timestamps, and schema metadata in database columns/cache metadata because they are not fields in the flat AI payload.
- Do not add a second contract or hide permanent compatibility logic outside `api/services/ai_client.py`.

Run before handoff:

```text
python -m pytest api/tests
cd web
npm run typecheck
npm run test
npm run lint
```

If AI fixtures are absent locally, fixture tests may skip; report that as a missing external delivery in this checkout. Do not manufacture conflicting fixtures under the full-stack track.
