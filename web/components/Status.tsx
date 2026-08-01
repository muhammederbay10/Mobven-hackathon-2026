/**
 * Status presentation primitives.
 *
 * Plan section 10.1: "Green/amber/red status is communicated by icon and text,
 * not color alone." Every component here pairs the color with a glyph and a
 * word, so the meaning survives a bad projector, a color-blind judge, and a
 * screenshot printed in greyscale.
 *
 * None of these decide a status. They render one the API already returned.
 */

import type { ReactNode } from "react";

import { CHECK_STATUS_LABEL, CHECK_STATUS_SYMBOL } from "@/lib/format";
import type { CheckStatus } from "@/lib/types";

const TONE: Record<CheckStatus, { icon: string; text: string; ring: string }> = {
  GREEN: { icon: "bg-ok-bg text-ok", text: "text-ok", ring: "border-ok" },
  AMBER: { icon: "bg-warn-bg text-warn", text: "text-warn", ring: "border-warn" },
  RED: { icon: "bg-bad-bg text-bad", text: "text-bad", ring: "border-bad" },
};

/** A small round status glyph. Always accompanied by text from its caller. */
export function StatusIcon({ status }: { status: CheckStatus }) {
  return (
    <span
      className={`grid size-[19px] flex-none place-items-center rounded-full text-[11px] font-bold ${TONE[status].icon}`}
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
      className="grid size-[19px] flex-none place-items-center rounded-full bg-line text-[11px] font-bold text-ink-3"
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
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE[status].icon}`}
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
    status === "GREEN" ? "bg-ok-bg text-ok" : status === "AMBER" ? "bg-warn-bg text-warn" : "bg-bad-bg text-bad";
  return (
    <div className={`flex items-center gap-3 border-b border-line px-[18px] py-3.5 text-sm ${tone}`}>
      <span
        className="grid size-[22px] flex-none place-items-center rounded-full bg-black/[0.07] text-[13px] font-bold"
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
    <span className="ml-1.5 whitespace-nowrap rounded-full border border-line-strong px-[7px] text-[11px] font-normal text-ink-3">
      {label}
    </span>
  );
}
