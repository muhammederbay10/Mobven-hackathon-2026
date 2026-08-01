/**
 * Shared layout primitives, carried over from docs/fbdocs/index.html.
 *
 * Presentation only (plan Phase 0 frontend step 2 and section 1.4.10). None of
 * these components fetch, decide, or hold demo state.
 */

import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-[12px] border border-line bg-surface ${className}`}>{children}</div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2.5 text-[11.5px] uppercase tracking-[0.06em] text-ink-3">{children}</div>
  );
}

export function PageHeading({ title, subtitle }: { title: ReactNode; subtitle?: ReactNode }) {
  return (
    <>
      <h2 className="mb-1 text-[19px] font-semibold tracking-[-0.01em]">{title}</h2>
      {subtitle ? <p className="mb-5 text-sm text-ink-2">{subtitle}</p> : null}
    </>
  );
}

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
        <div className="bg-brand px-4.5 pb-3.75 pt-3.5 text-white">
          <div className="text-[11px] opacity-75">{company}</div>
          <div className="mt-px text-[15px] font-semibold">{title}</div>
        </div>
        <div className="flex flex-1 flex-col p-4.5">{children}</div>
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
    <div className={`paper min-h-107.5 ${className}`}>
      {children}
      {seal ? <div className="paper-seal">{seal}</div> : null}
    </div>
  );
}
