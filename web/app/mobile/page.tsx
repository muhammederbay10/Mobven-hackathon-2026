import { Suspense } from "react";

import { LoadingState } from "@/components/States";

import { MobileClient } from "./MobileClient";

/**
 * `/mobile?mersis={mersis}` — Act 2: transactions and co-signature.
 *
 * The MERSİS lives in the URL query (guide section 5) so a refresh restores
 * the screen from the server. The co-signer experience is a state of this
 * route, not another route.
 */

export default function MobilePage() {
  return (
    <Suspense fallback={<LoadingState label="Mobil şube yükleniyor…" />}>
      <MobileClient />
    </Suspense>
  );
}
