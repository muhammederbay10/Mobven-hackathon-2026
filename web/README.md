# `web/` — YetkiCheck frontend

Next.js (App Router) + TypeScript. Talks only to the bank API on `NEXT_PUBLIC_API_BASE_URL`; it never calls the AI service directly (plan section 1.3).

## Commands

```bash
npm install
npm run dev        # :3000
npm run lint
npm run typecheck
npm run test
npm run build
```

`lint`, `typecheck` and `test` run today. `dev` and `build` become functional once the Phase 0 frontend steps add `app/layout.tsx` and the route files.

## Routes — frozen at five (GAP-14)

| Route | Purpose |
|---|---|
| `/` | demo control panel: four case cards, flow strip, reset |
| `/branch` | Act 1 — intake, scan, review, decision |
| `/mobile` | Act 2 — transactions, co-signature (the co-signer view is a *state* of this route) |
| `/authority/[mersis]` | authority record + audit trail (audit is a *section* of this route) |
| `/registry` | simulated registry administration |

A sixth route may be added only if it replaces an existing one, and only before H30.

## Contracts

| File | Role |
|---|---|
| `lib/types.ts` | hand-written mirror of the frozen contracts — what the app codes against |
| `lib/contracts.ts` | zod schemas for runtime validation, plus type-level drift guards |
| `lib/contracts.test.ts` | offline contract tests over delivered fixtures |
| `lib/api.ts` | the API layer (Phase 0 frontend step 4) |
| `lib/format.ts` | display formatting, including money (Phase 0 frontend step 4) |

`lib/contracts.ts` asserts each zod schema and its twin in `types.ts` are mutually assignable, so drift between the two fails `npm run typecheck`. See [`../docs/CONTRACT_FREEZE.md`](../docs/CONTRACT_FREEZE.md).

## Rules this app holds to

- **`lib/api.ts` is the only file allowed to call `fetch`** (plan section 10.1). An ESLint rule enforces it.
- **Business verdicts come only from the API.** Components never calculate a check, a verdict or a decision, and never complete a co-signature client-side.
- **Money is formatted only at the display edge**, via `lib/format.ts` and `Intl.NumberFormat('tr-TR', {style:'currency', currency:'TRY'})`. Components never divide or format `amount_minor` ad hoc.
- **Registry-derived content carries a visible simulated badge.**
- **Status is never communicated by color alone** — always icon and text too.
- **Every async view has four states:** loading, retryable error, non-retryable error, and empty.
- **Turkish copy is the user-facing default.**
- **Server state is authoritative.** The application ID lives in the URL, and the stepper follows backend application status rather than local completion guesses — a refresh must not reset progress.
- Animation may delay a *visual* reveal, but never delays or alters the actual API result.

## Design tokens

Presentation primitives are carried over from `docs/fbdocs/index.html` — colors, spacing, radii, document-paper styling, status styles and the phone frame. That file is authoritative for presentation intent only; its client-side hardcoding of verdicts and approvals is mock behavior and must not be copied into this app.
