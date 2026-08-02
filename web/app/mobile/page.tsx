import { Suspense } from "react";

import { LoadingState } from "@/components/States";

import { MobileClient } from "./MobileClient";

/** Restores the selected company when the mobile transaction page is refreshed. */

export default function MobilePage() {
  return (
    <Suspense fallback={<LoadingState label="Mobil şube yükleniyor…" />}>
      <MobileClient />
    </Suspense>
  );
}
