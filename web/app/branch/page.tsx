import { Suspense } from "react";

import { LoadingState } from "@/components/States";

import { BranchClient } from "./BranchClient";

/**
 * `/branch?application={id}` — Act 1: intake, scan, review, decision.
 *
 * The application ID lives in the URL query, never only in component memory
 * (guide section 5) — that is what lets a refresh restore progress from the
 * server instead of dropping the presenter back to step 1. All state below
 * this point is driven by `GET /api/applications/{id}`.
 */

export default function BranchPage() {
  return (
    <Suspense fallback={<LoadingState label="Başvuru yükleniyor…" />}>
      <BranchClient />
    </Suspense>
  );
}
