/**
 * Reusable atomic controls — DESIGN_SYSTEM.md sections 8, 9 and 10.
 *
 * Button, Pill, Input, Breadcrumb and IconButton. Panels/cards and the shell
 * composition live in `Layout.tsx`; semantic status treatment lives in
 * `Status.tsx`. Nothing here is business-specific — a case card, a check row,
 * or a verdict banner is composed *from* these, not defined here.
 */

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

import { ChevronRightIcon } from "./Icon";

/* -------------------------------------------------------------------------- */
/* Button                                                                     */
/* -------------------------------------------------------------------------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  // Dark neutral by default; the accent gradient is reserved for a single
  // primary top-bar action per section 8, not every primary button.
  primary: "border border-ink bg-ink text-white hover:opacity-90",
  secondary: "border border-border-strong bg-surface text-ink hover:bg-surface-hover",
  ghost: "border border-transparent text-ink-secondary hover:bg-surface-hover",
  danger: "border border-danger bg-danger text-white hover:opacity-90",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      {...props}
      className={[
        "inline-flex h-9 items-center justify-center gap-1.5 rounded-control px-3.5 text-[13.5px] font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40",
        BUTTON_VARIANT[variant],
        className,
      ].join(" ")}
    />
  );
}

/** Section 8: icon buttons are 32-36px square with a thin border and 9-10px radius. */
export function IconButton({
  label,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={[
        "grid size-9 flex-none place-items-center rounded-control border border-border-strong bg-surface text-ink-secondary transition-colors duration-150 hover:bg-surface-hover",
        className,
      ].join(" ")}
    >
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/* Pill                                                                       */
/* -------------------------------------------------------------------------- */

type PillTone = "neutral" | "cyan" | "pink" | "violet";

const PILL_TONE: Record<PillTone, string> = {
  neutral: "bg-surface-subtle text-ink-secondary",
  cyan: "bg-cyan-soft text-info",
  pink: "bg-pink-soft text-ink-secondary",
  violet: "bg-violet-soft text-ink-secondary",
};

/**
 * A decorative-accent pill. Never used for a GREEN/AMBER/RED outcome — those
 * are `StatusBadge` in `Status.tsx`, which is the only place semantic verdict
 * colors are allowed to originate (DESIGN_SYSTEM.md section 3).
 */
export function Pill({ tone = "neutral", children }: { tone?: PillTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-pill px-2.5 py-0.5 text-[11px] font-medium ${PILL_TONE[tone]}`}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Form controls                                                              */
/* -------------------------------------------------------------------------- */

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1.5 block text-[11.5px] font-medium text-ink-secondary"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1.5 text-[11.5px] text-danger">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-[11.5px] text-ink-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={[
        "h-9 w-full rounded-control border border-border-strong bg-surface px-3 text-[13px] text-ink placeholder:text-ink-muted focus-visible:border-info",
        className,
      ].join(" ")}
    />
  );
}

export function Checkbox({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      {...props}
      className={["mt-0.5 size-4 flex-none rounded-[4px] border-border-strong text-ink", className].join(
        " ",
      )}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Breadcrumb                                                                 */
/* -------------------------------------------------------------------------- */

export type BreadcrumbItem = { label: string; href?: string; icon?: ReactNode };

/**
 * Section 8 + reference PNG: compact breadcrumb, "Ana Sayfa / current
 * section", each crumb with its small outline glyph.
 */
export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Konum" className="flex min-w-0 items-center gap-1.5 text-[13px]">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        const content = (
          <>
            {item.icon ? (
              <span className="flex-none text-ink-secondary" aria-hidden>
                {item.icon}
              </span>
            ) : null}
            <span className="truncate">{item.label}</span>
          </>
        );
        return (
          <span key={`${item.label}-${index}`} className="flex min-w-0 items-center gap-1.5">
            {index > 0 ? <ChevronRightIcon className="flex-none text-ink-muted" /> : null}
            {item.href && !isLast ? (
              <Link
                href={item.href}
                className="flex min-w-0 items-center gap-1.5 text-ink-secondary hover:text-ink"
              >
                {content}
              </Link>
            ) : (
              <span
                className={`flex min-w-0 items-center gap-1.5 ${
                  isLast ? "font-medium text-ink" : "text-ink-secondary"
                }`}
                aria-current={isLast ? "page" : undefined}
              >
                {content}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
