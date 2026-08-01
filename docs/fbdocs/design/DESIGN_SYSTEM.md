# YetkiCheck visual design system

**Status:** frozen visual contract for the full-stack frontend track  
**Reference image:** [`nexai-dashboard-reference.png`](./nexai-dashboard-reference.png)  
**Applies from:** Phase 1 task `P1-04` and every later frontend task  

This document translates the supplied dashboard screenshot into implementation rules that a coding agent can follow consistently. The screenshot is the visual reference; this document is the executable interpretation of it for YetkiCheck.

## 1. Authority and adaptation rules

Use references in this order:

1. `docs/fbdocs/PROJECT.md` defines product intent and scope.
2. `docs/fbdocs/IMPLEMENTATION_PLAN.md` defines behavior, architecture, routes, and task acceptance.
3. This file and `nexai-dashboard-reference.png` define the global visual language: typography, palette, shell, sidebar, top bar, cards, controls, spacing, and responsive behavior.
4. `docs/fbdocs/index.html` defines YetkiCheck-specific workflow presentation: the branch stepper, document paper, evidence/check states, verdicts, phone frame, authority view, and registry interactions.

When references appear to conflict, preserve YetkiCheck behavior and data from the project plan while applying the visual language from the screenshot. Do not copy the NexAI logo, navigation names, dashboard metrics, charts, hypotheses, or product copy. Do not add routes or features merely because they appear in the screenshot.

## 2. Design character

The interface should feel like a calm, modern banking operations workspace:

- a pale gray canvas containing one large white application shell;
- a persistent, quiet left navigation rail;
- a compact top bar with breadcrumbs and page actions;
- thin borders, soft shadows, and generous whitespace;
- rounded rectangular controls and cards;
- dark neutral text with cyan, pink, and violet used as controlled accents;
- semantic green, amber, and red reserved for actual YetkiCheck outcomes;
- dense enough for operational work, but readable from a projector at `1280x800`.

Avoid heavy gradients across whole pages, glassmorphism, dark mode, oversized headings, thick shadows, saturated card backgrounds, and decorative charts that do not serve the YetkiCheck workflow.

## 3. Design tokens

Define these once in `web/app/globals.css` as CSS custom properties. Components must consume tokens rather than introduce one-off hex colors, shadows, or radii.

```css
:root {
  /* Canvas and surfaces */
  --yc-canvas: #f0f0f2;
  --yc-shell: #fbfbfc;
  --yc-surface: #ffffff;
  --yc-surface-subtle: #fafafb;
  --yc-surface-hover: #f7f8fa;

  /* Borders */
  --yc-border: #e8e8ec;
  --yc-border-strong: #dcdee4;

  /* Text */
  --yc-text: #25262b;
  --yc-text-secondary: #666970;
  --yc-text-muted: #9a9da5;

  /* Reference accents */
  --yc-cyan: #2abde2;
  --yc-cyan-soft: #eaf8fc;
  --yc-pink: #ff78b7;
  --yc-pink-soft: #fff0f7;
  --yc-violet: #a78bfa;
  --yc-violet-soft: #f3efff;

  /* Semantic outcomes */
  --yc-success: #16875b;
  --yc-success-soft: #eaf7f1;
  --yc-warning: #a66a13;
  --yc-warning-soft: #fff5e5;
  --yc-danger: #c54a55;
  --yc-danger-soft: #fdeef0;
  --yc-info: #187fa0;
  --yc-info-soft: #eaf8fc;

  /* Shape */
  --yc-radius-shell: 22px;
  --yc-radius-panel: 14px;
  --yc-radius-card: 12px;
  --yc-radius-control: 10px;
  --yc-radius-pill: 999px;

  /* Elevation */
  --yc-shadow-shell: 0 18px 45px rgb(28 30 38 / 8%);
  --yc-shadow-panel: 0 1px 2px rgb(28 30 38 / 4%);
  --yc-shadow-raised: 0 8px 24px rgb(28 30 38 / 8%);

  /* Layout */
  --yc-sidebar-width: 216px;
  --yc-topbar-height: 54px;
  --yc-page-gap: 20px;
  --yc-panel-padding: 16px;
}
```

The screenshot is a raster reference, so these values are the frozen implementation palette chosen to reproduce it consistently. Do not repeatedly resample or reinterpret the image per component.

### Accent gradient

Use the accent gradient sparingly for the primary top-bar action, a small brand mark, or a subtle divider wash:

```css
--yc-gradient-action: linear-gradient(135deg, #b99cff 0%, #66cce8 52%, #23b9dd 100%);
--yc-gradient-wash: linear-gradient(
  90deg,
  rgb(255 120 183 / 10%) 0%,
  rgb(255 255 255 / 0%) 34%,
  rgb(42 189 226 / 18%) 70%,
  rgb(167 139 250 / 20%) 100%
);
```

Never use the accent colors to override semantic verdict colors. `READY`, `CO_SIGNER_REQUIRED`, `MISMATCH`, and `REGISTRY_CONFLICT` retain their green/amber/red meaning from the product plan.

## 4. Typography

The closest reproducible match to the screenshot is **Inter**.

- Primary UI family: `Inter`, then `ui-sans-serif`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `sans-serif`.
- Document-paper family: `Georgia`, `"Times New Roman"`, `serif`.
- Evidence identifiers, MERSİS values, hashes, authorization codes, and measured amounts may use `ui-monospace`, `SFMono-Regular`, `Menlo`, `Consolas`, `monospace`.
- Prefer a self-hosted Inter variable WOFF2 asset so the demo works offline. Do not depend on a runtime font CDN.

The reference image alone cannot prove its original font file. Inter is therefore the frozen project choice unless an original Figma/CSS source is later supplied and the design contract is deliberately updated.

| Role | Size | Weight | Line height | Notes |
|---|---:|---:|---:|---|
| Page title | 20px | 600 | 28px | Compact; never a marketing hero |
| Section title | 14px | 600 | 20px | Panel/card headings |
| Body | 13px | 400 | 20px | Default operational copy |
| Navigation item | 13px | 500 | 18px | Active item may use 600 |
| Small/meta | 11px | 400 | 16px | Timestamps and supporting text |
| Group label | 10px | 600 | 14px | Uppercase, `0.08em` tracking |
| Metric/value | 26px | 400 | 32px | Use only where a prominent value is useful |

Avoid font weights above 700. Muted text must remain readable on a projector.

## 5. Spacing

Use a 4px base grid:

```text
4, 8, 12, 16, 20, 24, 32, 40
```

- Desktop canvas padding: `28px`.
- Main page padding: `18px 20px 24px`.
- Major section gap: `20px`.
- Card gap: `12px`.
- Card padding: `12px` to `16px`.
- Form/control height: `36px` normally; `40px` for the primary form action.
- Dense table rows: minimum `42px`.
- Minimum touch target on mobile: `44px`.

## 6. Application shell

At desktop width, render the product as one large rounded shell inside the gray viewport:

```text
viewport / pale gray canvas
└── application shell / white / rounded / soft shadow
    ├── sidebar / fixed visual column
    └── workspace
        ├── top bar
        └── route content
```

- Shell width: `calc(100vw - 56px)` with a sensible maximum of `1440px`.
- Shell minimum height: `calc(100vh - 56px)`.
- Shell radius: `22px`; overflow is clipped.
- Sidebar and workspace share the same shell; do not render the sidebar as a detached floating card.
- Workspace remains white or subtle white-gray; individual panels provide grouping.

Prefer adapting the existing `web/components/Layout.tsx` and `SiteHeader.tsx`. Add a dedicated sidebar component rather than duplicating navigation inside routes.

## 7. Sidebar

The sidebar is the strongest identifying element of the reference and must be shared by all five routes.

### Desktop anatomy

- Width: `216px`.
- Background: `--yc-shell`.
- Right boundary: one subtle `--yc-border` line.
- Top brand row: 52–56px high with a small rounded gradient mark and `YetkiCheck` wordmark.
- Navigation padding: `14px` horizontally.
- Section groups have uppercase muted labels and `18–24px` separation.
- Navigation rows are 36px high, use 16px line icons, and have a 10–11px radius.
- Default rows have no visible container.
- Active row uses white background, a subtle border, slightly darker text, and medium weight. Do not fill it with the brand color.
- Optional counters/status pills sit at the far edge and remain compact.
- Utility/help content may anchor to the bottom, but no fake settings route should be added.

### YetkiCheck navigation map

| Group | Label | Route |
|---|---|---|
| İş Akışı | Kontrol Paneli | `/` |
| İş Akışı | Şube İnceleme | `/branch` |
| Yetki ve İşlem | Mobil İşlemler | `/mobile` |
| Yetki ve İşlem | Yetki Kaydı | `/authority/[mersis]` when an active MERSİS is known; otherwise `/authority` |
| Simülasyon | Ticaret Sicili | `/registry` |

The active state comes from the current pathname. The sidebar does not create business state or guess the active application.

### Responsive behavior

- `>= 1100px`: full 216px sidebar.
- `768–1099px`: compact icon rail is allowed if content would otherwise overflow; labels remain accessible through tooltips and screen-reader text.
- `< 768px`: sidebar becomes a modal drawer opened from the top bar. It must not consume permanent horizontal space.
- Keyboard focus is trapped inside the open mobile drawer and restored to the trigger on close.

## 8. Top bar

- Height: `54px` with a bottom border.
- Left: compact breadcrumb (`Ana Sayfa / current section`) and optional mobile menu trigger.
- Right: route-relevant actions only.
- A search field may appear only when there is real searchable content. Do not add a dead search box merely to copy the screenshot.
- Primary action may use `--yc-gradient-action`; destructive or semantic actions use their semantic style instead.
- Icon buttons are 32–36px square with a thin border and 9–10px radius.
- The top bar stays visually quiet and never duplicates the route’s main form.

## 9. Panels, cards, and data surfaces

### Panels

- White surface, `1px` border, 14px radius, minimal shadow.
- Title row is compact, with secondary actions aligned right.
- Use whitespace and borders for hierarchy; avoid large colored headers.

### Cards

- Radius: 12px.
- Border: `--yc-border`.
- Padding: 12–16px.
- Hover: slightly stronger border and optional `translateY(-1px)` only when clickable.
- Selected/active cards use a tinted border or subtle accent surface, not a heavy glow.

### Tables and lists

- Column headers use the group-label typography.
- Rows use 12–13px text and thin separators.
- Numeric, date, identifier, and status columns align consistently.
- Avoid zebra striping unless a table becomes difficult to scan.

### Forms

- Inputs use white background, 1px border, 10px radius, and a clear focus ring.
- Labels sit above fields and use 11–12px secondary text.
- Validation text is placed directly below the relevant field.
- Disabled actions remain readable and explain why they are unavailable when needed.

## 10. Buttons, pills, and icons

- Primary: dark neutral or the controlled cyan-violet gradient, depending on context.
- Secondary: white surface with border.
- Ghost: no default container; subtle surface on hover.
- Danger: semantic red, never pink accent.
- Pills use a fully rounded shape, 10–11px type, and soft tinted backgrounds.
- Use one outline icon family consistently, preferably Lucide-style icons at 16px with `1.5px` stroke.
- Do not use emoji as interface icons.

## 11. YetkiCheck-specific surfaces

The reference dashboard supplies the shell, but these surfaces retain their product-specific design from `index.html` and the implementation plan:

- branch stepper and attestations;
- document viewer and serif paper styling;
- extracted-field table and review chips;
- exactly nine check rows and evidence expansion;
- verdict banners and approval/override actions;
- mobile phone frame, transaction cards, and co-sign state;
- authority record and audit table;
- simulated registry notice and representative controls.

Place these inside the shared shell and restyle their borders, spacing, typography, and card containers with this design system. Do not turn the branch review into a generic dashboard chart.

## 12. Motion

- Standard hover/focus transitions: `120–180ms ease`.
- Panel/card entry: no more than `220ms`.
- The planned field/check reveal choreography may be longer because it communicates analysis progress, but it must not delay the API result or block interaction after completion.
- Respect `prefers-reduced-motion` and render final states without choreography when requested.
- Avoid looping decoration, parallax, and large page transitions.

## 13. Accessibility and projector rules

- Body text must remain at least 13px on desktop demo screens.
- Interactive controls require visible keyboard focus.
- Status always includes icon and text; color is supplementary.
- Keep WCAG AA contrast for operational text and controls.
- Sidebar items and icon-only buttons require accessible names.
- The full five-route shell must work without horizontal scrolling at `1280x800`.
- At projector size, the active navigation item, verdict, primary action, company name, amount, and next step must be legible from the back of the room.

## 14. Component ownership

Implement the system centrally. Suggested ownership using the current repository:

```text
web/app/globals.css             design tokens and global canvas
web/app/layout.tsx              font loading and global document metadata
web/components/Layout.tsx       application shell composition
web/components/SiteHeader.tsx   compact top bar and breadcrumbs
web/components/Sidebar.tsx      grouped persistent navigation
web/components/Status.tsx       semantic status treatment
web/components/States.tsx       loading/empty/error presentation
```

Route files supply content and route actions. They must not recreate the sidebar, top bar, palette, or token set.

## 15. Acceptance checklist

The shared shell is accepted only when:

- the committed reference image is viewable from the repo;
- all five routes render inside one consistent application shell;
- desktop sidebar width, grouping, active treatment, icons, and spacing match the reference character;
- the top bar, cards, borders, shadows, and radii use the frozen tokens;
- Inter is loaded locally or the documented temporary fallback is visible during development;
- NexAI branding, navigation, metrics, and copy are absent;
- semantic verdict/status colors remain correct;
- mobile navigation is usable and keyboard accessible;
- no route introduces ad-hoc global colors, fonts, radii, or duplicated shell markup;
- the shell and demonstrated states fit at `1280x800` without horizontal overflow.

