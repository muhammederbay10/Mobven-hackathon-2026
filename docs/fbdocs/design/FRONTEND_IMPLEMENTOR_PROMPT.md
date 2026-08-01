# Frontend implementor kickoff prompt

Copy the prompt below into the frontend implementation task.

---

You are implementing YetkiCheck task `P1-04` — the shared frontend shell and control panel design foundation.

Before editing, read these files completely:

1. `docs/fbdocs/PROJECT.md`
2. `docs/fbdocs/IMPLEMENTATION_PLAN.md`, especially sections 10 and 12 and task `P1-04`
3. `docs/fbdocs/design/DESIGN_SYSTEM.md`
4. Inspect `docs/fbdocs/design/nexai-dashboard-reference.png` at full resolution
5. Read `docs/fbdocs/index.html` only for YetkiCheck-specific workflow presentation, document/phone treatments, and semantic status behavior
6. Inspect the existing `web/` structure and preserve compatible Phase 0 work

Reference precedence:

- `PROJECT.md` controls product intent and scope.
- `IMPLEMENTATION_PLAN.md` controls behavior, routes, architecture, and acceptance.
- `DESIGN_SYSTEM.md` plus the PNG control the global visual language: typography, colors, shell, sidebar, top bar, cards, controls, spacing, and responsiveness.
- `index.html` controls YetkiCheck-specific workflow presentation.

Implement the screenshot’s design language, not its product. Do not copy the NexAI logo, text, charts, metrics, hypotheses, or navigation. Adapt the shell to these fixed YetkiCheck routes only: `/`, `/branch`, `/mobile`, `/authority/[mersis]`, and `/registry`. Do not add routes.

Scope:

1. Centralize the frozen tokens from `DESIGN_SYSTEM.md` in `web/app/globals.css`.
2. Load the frozen Inter typography with an offline-safe local approach if the font asset is available; otherwise use the documented fallback without adding a network runtime dependency.
3. Adapt the existing `Layout.tsx` and `SiteHeader.tsx` into the shared rounded application shell and compact top bar.
4. Add one reusable grouped sidebar with pathname-driven active state and the exact YetkiCheck navigation map from `DESIGN_SYSTEM.md`.
5. Implement responsive behavior: full sidebar on desktop, compact behavior where needed, and an accessible drawer on mobile.
6. Create or refine reusable panel, card, button, badge, input, breadcrumb, and icon-button treatments. Keep business-specific components outside this task.
7. Restyle the `/` control panel and its four case cards inside the shell without hardcoding verdict logic or business decisions in React.
8. Preserve `web/lib/api.ts` as the only file that calls `fetch`.
9. Preserve all existing API contracts, route scope, Turkish copy, loading/error patterns, and semantic green/amber/red meanings.

Constraints:

- Do not edit `api/`, `ai/`, fixtures, backend schemas, or business rules.
- Do not install a component framework unless the repository already depends on it and the plan explicitly permits it.
- Do not introduce dead search, notification, settings, or action controls just to match the screenshot.
- Do not duplicate the shell or sidebar inside route files.
- Do not use one-off global hex colors, shadows, fonts, or radii outside the centralized tokens.
- Do not turn the reference dashboard’s sample scenarios into YetkiCheck workflows.
- Preserve unrelated user changes in the worktree.

Acceptance:

- All five route skeletons render inside the same shell.
- At `1280x800`, the shell has no horizontal overflow and visually matches the reference’s canvas, rounded frame, sidebar, top bar, border, card, spacing, and typography character.
- Sidebar groups, active item, responsive drawer, and keyboard focus work correctly.
- NexAI branding/content is absent.
- YetkiCheck semantic statuses still use icon plus text and correct semantic colors.
- Selecting a case uses the existing typed API path and routes using the persistent application ID; no client-only business decision is added.
- Existing frontend contract tests still pass, and the smallest relevant lint/type/build checks are reported exactly.

Start by inspecting the existing frontend and state the files you intend to change. Then implement the task, verify it proportionally, and report changed files, checks run, and any remaining dependency such as a missing local Inter font asset.

---
