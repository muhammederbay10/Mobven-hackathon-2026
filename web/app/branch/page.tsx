import { Suspense } from "react";

import { LoadingState } from "@/components/States";

import { BranchClient } from "./BranchClient";

/** Restores an existing branch application from its URL when present. */

export default function BranchPage() {
  return (
    <Suspense fallback={<LoadingState label="Başvuru yükleniyor…" />}>
      <BranchClient />
    </Suspense>
  );
}
