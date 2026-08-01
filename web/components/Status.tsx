/**
 * Status presentation primitives.
 *
 * Plan section 10.1: "Green/amber/red status is communicated by icon and text,
 * not color alone." DESIGN_SYSTEM.md section 3: semantic success/warning/danger
 * are reserved for actual YetkiCheck outcomes and are never substituted by the
 * decorative cyan/pink/violet accents. Every component here pairs the color
 * with a glyph and a word, so the meaning survives a bad projector, a
 * color-blind judge, and a screenshot printed in greyscale.
 *
 * None of these decide a status. They render one the API already returned.
 */

import type { ReactNode } from "react";

import { CHECK_STATUS_LABEL, CHECK_STATUS_SYMBOL } from "@/lib/format";
import type { CheckStatus } from "@/lib/types";

const TONE: Record<CheckStatus, { icon: string; text: string }> = {
  GREEN: { icon: "bg-success-soft text-success", text: "text-success" },
  AMBER: { icon: "bg-warning-soft text-warning", text: "text-warning" },
  RED: { icon: "bg-danger-soft text-danger", text: "text-danger" },
};

/** A small round status glyph. Always accompanied by text from its caller. */
export function StatusIcon({ status }: { status: CheckStatus }) {
  return (
    <span
      className={`grid size-4.75 flex-none place-items-center rounded-full text-[11px] font-bold ${TONE[status].icon}`}
      aria-hidden
    >
      {CHECK_STATUS_SYMBOL[status]}
    </span>
  );
}

/** Pending state for a check that has not resolved yet. */
export function PendingIcon() {
  return (
    <span
      className="grid size-4.75 flex-none place-items-center rounded-full bg-surface-subtle text-[11px] font-bold text-ink-muted"
      aria-hidden
    >
      ·
    </span>
  );
}

/** Icon + word, for compact places like a table cell. */
export function StatusBadge({ status, label }: { status: CheckStatus; label?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-0.5 text-xs font-medium ${TONE[status].icon}`}
    >
      <span aria-hidden>{CHECK_STATUS_SYMBOL[status]}</span>
      {label ?? CHECK_STATUS_LABEL[status]}
    </span>
  );
}

/** The full-width verdict banner at the top of the review screen (§10.3). */
export function VerdictBanner({
  status,
  title,
  detail,
}: {
  status: CheckStatus;
  title: string;
  detail?: ReactNode;
}) {
  const tone =
    status === "GREEN"
      ? "bg-success-soft text-success"
      : status === "AMBER"
        ? "bg-warning-soft text-warning"
        : "bg-danger-soft text-danger";
  return (
    <div
      className={`flex items-center gap-3 rounded-panel border border-border px-4 py-3.5 text-[13px] ${tone}`}
    >
      <span
        className="grid size-5.5 flex-none place-items-center rounded-full bg-black/[0.07] text-[13px] font-bold"
        aria-hidden
      >
        {CHECK_STATUS_SYMBOL[status]}
      </span>
      <span>
        <b className="font-semibold">{title}</b>
        {detail ? <span className="ml-1.5">{detail}</span> : null}
      </span>
    </div>
  );
}

/**
 * Marks content that came from a simulated integration.
 *
 * Plan section 10.1 and section 14: registry-derived content carries a visible
 * badge, and a simulated integration is never presented as an unlabeled fake.
 */
export function SimBadge({ label = "simüle edilmiş" }: { label?: string }) {
  return (
    <span className="ml-1.5 whitespace-nowrap rounded-pill border border-border-strong px-2 py-0.5 text-[11px] font-normal text-ink-muted">
      {label}
    </span>
  );
}
