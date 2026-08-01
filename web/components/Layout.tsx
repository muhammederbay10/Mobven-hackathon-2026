/**
 * Application shell composition and shared surface primitives.
 *
 * `AppShell` is the rounded application shell from DESIGN_SYSTEM.md section 6:
 * a pale-gray canvas containing one white shell, split into the persistent
 * sidebar and a workspace column (top bar + route content). It owns the mobile
 * drawer's open state because that state is shared between the trigger (in
 * `SiteHeader`) and the drawer itself (in `Sidebar`) — the shared composition
 * point is the only place that coordination can live without the two
 * components reaching into each other.
 *
 * Route files render inside `{children}` and must not recreate the shell,
 * sidebar, or top bar (DESIGN_SYSTEM.md section 6 and section 14).
 */

"use client";

import type { ReactNode } from "react";
import { useRef, useState } from "react";

import { SiteHeader } from "./SiteHeader";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const openedFromRef = useRef<HTMLElement | null>(null);

  function openMobileNav() {
    openedFromRef.current = document.activeElement as HTMLElement | null;
    setMobileNavOpen(true);
  }

  function closeMobileNav() {
    setMobileNavOpen(false);
    // Section 7: "restored to the trigger on close."
    openedFromRef.current?.focus();
  }

  // Edge-to-edge, like an ordinary SaaS dashboard, per explicit direction:
  // no gray canvas margin around a "floating" shell. This departs from
  // DESIGN_SYSTEM.md section 6's literal "calc(100vw - 56px)" framed-shell
  // numbers; the sidebar, top bar, borders, radii and color tokens elsewhere
  // still follow the frozen system.
  return (
    <div className="flex h-screen bg-shell">
      <Sidebar
        open={mobileNavOpen}
        onClose={closeMobileNav}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <SiteHeader onOpenMobileNav={openMobileNav} />
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-surface px-5 pb-6 pt-[18px]">
          {children}
        </main>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Panels and cards — DESIGN_SYSTEM.md section 9                              */
/* -------------------------------------------------------------------------- */

export function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-panel border border-border bg-surface shadow-panel ${className}`}>
      {title ? (
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </div>
  );
}

const CARD_BASE = "rounded-card border border-border bg-surface p-4";

/** A lighter-weight surface than `Panel`, used for grouping static content. */
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`${CARD_BASE} ${className}`}>{children}</div>;
}

/**
 * The same surface as `Card`, as an interactive `<button>`.
 *
 * DESIGN_SYSTEM.md section 9: "Hover: slightly stronger border and optional
 * translateY(-1px) only when clickable." Kept as a distinct component rather
 * than a polymorphic `Card as="button"` so hover/focus styling only ever
 * applies to something that is actually a button.
 */
export function CardButton({
  children,
  className = "",
  ...rest
}: React.ComponentPropsWithoutRef<"button"> & { children: ReactNode }) {
  return (
    <button
      {...rest}
      className={`${CARD_BASE} text-left transition-[transform,border-color] duration-150 hover:-translate-y-px hover:border-border-strong focus-visible:-translate-y-px disabled:pointer-events-none disabled:opacity-50 ${className}`}
    >
      {children}
    </button>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
      {children}
    </div>
  );
}

export function PageHeading({ title, subtitle }: { title: ReactNode; subtitle?: ReactNode }) {
  return (
    <>
      <h2 className="mb-1 text-[20px] font-semibold leading-7 tracking-[-0.01em] text-ink">
        {title}
      </h2>
      {subtitle ? <p className="mb-5 text-[13px] leading-5 text-ink-secondary">{subtitle}</p> : null}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* YetkiCheck-specific surfaces (index.html-derived, restyled onto tokens)     */
/* -------------------------------------------------------------------------- */

/**
 * The phone shell for the mobile-banking act.
 *
 * A frame, nothing more: the screen inside is driven entirely by backend
 * decisions (plan section 10.4 — "no client-only completion").
 */
export function PhoneFrame({
  company,
  title,
  children,
}: {
  company: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="phone">
      <div className="phone-inner">
        <div className="bg-ink px-4 pb-3.5 pt-3.5 text-white">
          <div className="text-[11px] opacity-75">{company}</div>
          <div className="mt-px text-[15px] font-semibold">{title}</div>
        </div>
        <div className="flex flex-1 flex-col p-4">{children}</div>
      </div>
    </div>
  );
}

/**
 * The notarial document surface.
 *
 * Styling only. The system never claims a document is authentic and never
 * matches handwritten signatures (plan section 3.2) — the seal below is
 * decoration on a synthetic demo document, not a validity indicator.
 */
export function DocumentPaper({
  children,
  seal,
  className = "",
}: {
  children: ReactNode;
  seal?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`paper min-h-[430px] ${className}`}>
      {children}
      {seal ? <div className="paper-seal">{seal}</div> : null}
    </div>
  );
}
